# Ossie AI Ref — System Spec

Last updated: 2026-05-11

---

## Overview
AI-powered automated referee system for Ossie Indoor Beach Volleyball.
Replaces human refs on 8 courts. Tracks ball, scores points, detects faults.
Human supervisor with tablet can review and overrule any call.

---

## Hardware (per court)

### Camera Layout — 4 cameras, all on umpire stand
The umpire stand sits at the centre net, already elevated above net height. All 4 cameras mount as a compact cluster on the stand — one cable bundle down the pole to the Jetson at the base.

```
        BACK NET (Side A)
              ↑
    [Cam A1]     [Cam A2]      ← Upper pair (~3m): angled down toward each half
       \           /               Sees: ball landing, player position overhead
        \         /
    [Cam B1]     [Cam B2]      ← Lower pair (~2m): pointing along court length
       →           ←               Sees: ball trajectory, net crossing, carry/spin
            |
        [STAND]
        [SCREEN]               ← Virtual umpire display (see below)
            |
        [JETSON]               ← Edge compute at base of stand
              ↓
        BACK NET (Side B)
```

- **Upper pair (Cam A1 + A2):** Elevated, wide angle, angled downward toward each half of court. Primary for ball landing detection, player body position, overhead view of sand floor.
- **Lower pair (Cam B1 + B2):** At net height, pointing along court length in each direction. Primary for ball trajectory, net crossing, spin tracking, carry detection.
- **Stereo baseline:** Even 30-50cm separation between pairs is sufficient for 3D triangulation.
- **Camera spec:** 4K 60fps, PoE, wide angle (120°+), IP65 dust/sandproof. e.g. Hikvision or Reolink 4K PoE ~$80-150 AUD each.

### Virtual Umpire Display
- Screen mounted on stand facing the court
- Displays animated avatar that signals calls like a human ref:
  - Arm raised = point awarded
  - Arms crossed = fault
  - Score displayed numerically below avatar
- Audio: buzzer/whistle sound fires simultaneously with visual
- Players look at the stand as they would a human ref — familiar UX, builds trust fast
- Makes the system feel like a ref, not a computer

### Processing
- 1x NVIDIA Jetson Orin NX (16GB, ~$600) — handles all 4 camera streams comfortably
- 1x local SSD (1-2TB) — 4K archive for review
- 1x PoE switch (8-port, ~$80) — powers all 4 cameras + Jetson
- 1x display (tablet or monitor, ~$150) — virtual umpire output
- 1x speaker/buzzer (~$30)
- Calibration markers on net posts (coloured tape/reflective dots)

### Network & Power
- All self-contained per court — single power feed to PoE switch
- Jetson runs local WiFi hotspot — tablet connects directly, no venue internet needed
- 8 courts optionally connected via venue LAN for central supervisor dashboard
- Completely offline — no internet dependency, no cloud costs, no data leaving venue
- Internet only for: software updates (scheduled off-hours, optional)

**Cost per court:** ~$1,500-2,000 AUD
**Total 8 courts:** ~$12K-16K AUD
**Current ref cost:** ~$200,000/year
**Payback period:** 3-4 weeks of operation
**Year 2+ savings:** ~$180K-190K/year
**Licensing potential:** Other venues, other sports (netball, basketball) — significant IP value

---

## Court Details (Ossie-specific)
- Nets: blue
- Sand: white
- Ball: red/black/white panels
- Fully enclosed by nets (no out-of-bounds lines)
- Serve: from corner of court

---

## Detection Stack
- **Ball tracking:** asigatchov/fast-volleyball-tracking-inference (ONNX, 40-80fps CPU)
  - Repo: `/data/.openclaw/workspace/projects/ossie-ai-ref/fast-volleyball-tracking-inference/`
  - Model: `VballNetV1_seq9_grayscale_330_h288_w512.onnx`
  - Output: CSV of frame, visibility, x, y, radius
- **Player tracking (Phase 2):** YOLOv8 + pose estimation (MediaPipe)
  - For net touch detection (player hand/arm crosses net plane)
- **Ball spin tracking (Phase 3):** Panel rotation analysis at 60fps+
  - For carry detection (spin rate drops = ball in contact too long)

---

## Game Engine
File: `game-engine/game_engine.py`

### Rally State Machine
```
WAITING → SERVING → IN_PLAY → DEAD_BALL → POINT_AWARDED → WAITING
```

### Scoring Rules (Ossie-specific)
- Rally scoring (point awarded on every dead ball)
- Ball velocity < threshold for 20 frames = dead ball = point to opposing team
- Ball crosses top net boundary (upward/outward) = out = point to opposing team
- Serve: receiving team must make minimum 2 hits before returning
- During play: can return directly (1 hit allowed)
- Player touches centre net = fault = point to opposing team
- Ball hitting centre net = NOT a fault (play continues)
- Max 3 touches per side

### Boundary Detection
- **Current approach:** 2-point line calibration (click net corners in frame)
  - Works well for side-on camera angles
  - Ball crossing the 2D line in image = crossing boundary in real world
- **⚠️ ROADMAP: 3D triangulation (replaces homography for 4-camera setup)**
  - With 2+ cameras: use stereo vision / multi-view geometry to reconstruct real-world XYZ of ball
  - OpenCV `triangulatePoints()` — given ball position in 2 camera frames + camera calibration matrices → real 3D position
  - All boundary checks done in real-world space (metres, not pixels) — no perspective distortion at all
  - One-time calibration per court: film a checkerboard pattern to get camera intrinsics + extrinsics
  - Far more accurate and robust than homography
  - Critical for production-grade accuracy

---

## Calibration
- **Marker detection (future):** Coloured dots/tape on net posts → auto-detected on camera start → auto-calibrates boundary lines
- **Manual calibration (current):** Web UI — click 4 points on freeze frame
  - Top net left + right → out boundary
  - Centre net left + right → fault reference line (player body tracking uses this)
- **Calibration tool:** `game-engine/calibrate.html`
- **Calibration file:** `court_calibration.json`

---

## Test Player
File: `game-engine/player.html`
- Load video + ball tracking CSV
- Set net boundaries via click (Calibrate mode)
- Play video with live ball overlay + trail
- Score updates in real time
- Event log: rally start, point, dead ball, fault

---

## Review System (planned)
- Roaming supervisor carries tablet
- Web app — pick court, scrub last 10 seconds, both camera angles side by side
- Events flagged as "uncertain" (low detection confidence) auto-highlighted
- Supervisor can confirm or overrule — score updates live on scoreboard
- Stack: React PWA, served from Jetson, no internet required

---

## Phases

### Phase 1 — Ball tracking + basic scoring ✅ IN PROGRESS
- [x] Ball detection model running on Ossie footage
- [x] Game engine with rally state machine
- [x] Dead ball detection (velocity threshold)
- [x] Top net boundary crossing (out)
- [x] Interactive test player
- [ ] Homography calibration (see roadmap above)
- [ ] Fine-tune model on Ossie footage (currently 47-80% detection)
- [ ] Serve minimum 2-hit receive rule
- [ ] Wider angle footage + proper net calibration

### Phase 2 — Player tracking + net faults
- [ ] YOLOv8 player detection
- [ ] Pose estimation (hand/arm keypoints)
- [ ] Player net touch detection (hand crosses centre net plane)
- [ ] Touch counting per side (max 3)

### Phase 3 — Advanced rules
- [ ] Double hit detection (2 direction changes near same player)
- [ ] Carry detection (ball deceleration profile / spin rate drop)
- [ ] Serve fault detection (ball hits side net on serve)

### Phase 4 — Production hardware
- [ ] Permanent PoE camera mounts
- [ ] Jetson Orin Nano per court
- [ ] LED scoreboard integration
- [ ] Tablet review UI
- [ ] Calibration marker auto-detection

---

## Files
```
ossie-ai-ref/
├── SPEC.md                          ← this file
├── RESEARCH.md                      ← initial research notes
├── fast-volleyball-tracking-inference/  ← ball tracking model
│   ├── models/
│   ├── src/
│   ├── examples/                    ← sample footage + CSVs
│   └── output/                      ← processed tracking CSVs
├── ossie-footage/                   ← Mike's court footage
│   ├── clip1.mp4, clip2.mp4, clip3.mp4, ossie_court2.mp4
│   └── *_preview.gif                ← tracked output previews
└── game-engine/
    ├── game_engine.py               ← scoring logic
    ├── player.html                  ← interactive test player
    ├── calibrate.html               ← calibration UI
    ├── court_calibration.json       ← current calibration data
    ├── calibration_frame.jpg        ← frame used for calibration
    └── data/                        ← ball tracking CSVs for browser
```
