# Ossie AI Ref — System Spec

Last updated: 2026-05-11

---

## Overview
AI-powered automated referee system for Ossie Indoor Beach Volleyball.
Replaces human refs on 8 courts. Tracks ball, scores points, detects faults.
Human supervisor with tablet can review and overrule any call.

---

## Hardware (per court)
- 2x PoE IP cameras — 1080p 60fps, wide angle
  - Camera 1: elevated sideline (primary tracking)
  - Camera 2: above back net (net touch + player reach-over)
- 1x NVIDIA Jetson Orin Nano (~$250) — edge compute, self-contained per court
- 1x LED scoreboard display
- 1x buzzer/speaker (point/fault audio feedback)
- PoE switch port + cabling
- Calibration markers on net posts (coloured tape/reflective dots)

**Cost estimate:** ~$600-860/court, ~$5.2K-7.3K for 8 courts
**ROI:** ~3-4 months vs paying human refs

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
- **⚠️ ROADMAP: Homography calibration (add before production)**
  - Problem: perspective distortion — ball at back of court appears lower in image than same-height ball at front
  - Fix: mark 4 known real-world points at calibration time → OpenCV `findHomography()` → maps image coords to real-world coords → all boundary checks done in real-world space
  - One-time calibration per camera position
  - Critical for accuracy from elevated/angled cameras

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
