"""
Ossie AI Ref — Game Engine
Processes ball tracking CSV + court calibration JSON to produce scoring events.
"""

import json
import csv
import math
import argparse
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from enum import Enum


class RallyState(Enum):
    WAITING    = "waiting"     # Before serve / between points
    SERVING    = "serving"     # Ball in serve corner, about to be hit
    IN_PLAY    = "in_play"     # Rally active
    DEAD_BALL  = "dead_ball"   # Ball stopped or lost
    POINT      = "point"       # Point just scored


@dataclass
class BallPosition:
    frame: int
    x: float
    y: float
    radius: float
    visible: bool


@dataclass
class GameEvent:
    frame: int
    event_type: str   # "point_team_a", "point_team_b", "net_fault", "out_of_bounds", "serve", "rally_start", "dead_ball"
    description: str
    score_a: int = 0
    score_b: int = 0


@dataclass
class CalibrationData:
    image_width: int
    image_height: int
    top_net_left: Tuple[float, float]
    top_net_right: Tuple[float, float]
    centre_net_left: Tuple[float, float]
    centre_net_right: Tuple[float, float]
    sand_floor_left: Tuple[float, float]
    sand_floor_right: Tuple[float, float]


def load_calibration(path: str) -> CalibrationData:
    with open(path) as f:
        d = json.load(f)
    return CalibrationData(
        image_width=d['image_width'],
        image_height=d['image_height'],
        top_net_left=(d['top_net']['left']['x'], d['top_net']['left']['y']),
        top_net_right=(d['top_net']['right']['x'], d['top_net']['right']['y']),
        centre_net_left=(d['centre_net']['left']['x'], d['centre_net']['left']['y']),
        centre_net_right=(d['centre_net']['right']['x'], d['centre_net']['right']['y']),
        sand_floor_left=(d['sand_floor']['left']['x'], d['sand_floor']['left']['y']),
        sand_floor_right=(d['sand_floor']['right']['x'], d['sand_floor']['right']['y']),
    )


def load_ball_csv(path: str) -> List[BallPosition]:
    positions = []
    with open(path) as f:
        for row in csv.DictReader(f):
            visible = int(row['Visibility']) == 1
            positions.append(BallPosition(
                frame=int(row['Frame']),
                x=float(row['X']) if visible else -1,
                y=float(row['Y']) if visible else -1,
                radius=float(row['Radius']) if visible else 0,
                visible=visible,
            ))
    return positions


def point_to_line_distance(px, py, x1, y1, x2, y2) -> float:
    """Signed distance from point to line segment."""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.sqrt((px - x1)**2 + (py - y1)**2)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0, min(1, t))
    nearest_x = x1 + t * dx
    nearest_y = y1 + t * dy
    return math.sqrt((px - nearest_x)**2 + (py - nearest_y)**2)


def crosses_line(p1, p2, lx1, ly1, lx2, ly2) -> bool:
    """Check if trajectory from p1 to p2 crosses a line segment."""
    def cross(ax, ay, bx, by, cx, cy, dx, dy):
        def ccw(ax, ay, bx, by, cx, cy):
            return (cy - ay) * (bx - ax) > (by - ay) * (cx - ax)
        return (ccw(ax, ay, cx, cy, dx, dy) != ccw(bx, by, cx, cy, dx, dy) and
                ccw(ax, ay, bx, by, cx, cy) != ccw(ax, ay, bx, by, dx, dy))
    return cross(p1[0], p1[1], p2[0], p2[1], lx1, ly1, lx2, ly2)


def interpolate_y_on_line(x, x1, y1, x2, y2) -> float:
    """Get y value on a line at a given x."""
    if x2 == x1:
        return (y1 + y2) / 2
    return y1 + (y2 - y1) * (x - x1) / (x2 - x1)


class GameEngine:
    # Tuning parameters
    DEAD_BALL_FRAMES = 15      # Frames of no movement to declare dead ball
    STILL_VELOCITY = 8.0       # Pixels per frame — below this = "stopped"
    SERVE_CORNER_MARGIN = 0.15 # 15% from corners = serve zone
    NET_PROXIMITY = 25         # Pixels from net line = "near net"
    MIN_RALLY_FRAMES = 10      # Minimum frames for a valid rally

    def __init__(self, cal: CalibrationData):
        self.cal = cal
        self.state = RallyState.WAITING
        self.score_a = 0
        self.score_b = 0
        self.events: List[GameEvent] = []
        self.rally_start_frame = 0
        self.last_visible_frame = 0
        self.invisible_streak = 0
        self.last_pos: Optional[BallPosition] = None
        self.prev_pos: Optional[BallPosition] = None

    def _is_in_serve_corner(self, x, y) -> Optional[str]:
        """Returns 'A' or 'B' if ball is in a serve corner, else None."""
        w, h = self.cal.image_width, self.cal.image_height
        margin_x = w * self.SERVE_CORNER_MARGIN
        margin_y = h * self.SERVE_CORNER_MARGIN
        if x < margin_x and y > h - margin_y:
            return 'A'
        if x > w - margin_x and y > h - margin_y:
            return 'B'
        if x < margin_x and y < margin_y:
            return 'A'
        if x > w - margin_x and y < margin_y:
            return 'B'
        return None

    def _is_above_top_net(self, x, y) -> bool:
        """Returns True if ball is above the top net boundary."""
        net_y = interpolate_y_on_line(
            x,
            self.cal.top_net_left[0], self.cal.top_net_left[1],
            self.cal.top_net_right[0], self.cal.top_net_right[1]
        )
        return y < net_y

    def _is_below_sand_floor(self, x, y) -> bool:
        """Returns True if ball has hit/crossed the sand floor."""
        floor_y = interpolate_y_on_line(
            x,
            self.cal.sand_floor_left[0], self.cal.sand_floor_left[1],
            self.cal.sand_floor_right[0], self.cal.sand_floor_right[1]
        )
        return y >= floor_y

    def _crossed_centre_net(self, prev, curr) -> bool:
        """Detect if ball crossed the centre net between two frames."""
        if not prev or not curr:
            return False
        return crosses_line(
            (prev.x, prev.y), (curr.x, curr.y),
            self.cal.centre_net_left[0], self.cal.centre_net_left[1],
            self.cal.centre_net_right[0], self.cal.centre_net_right[1]
        )

    def _ball_side(self, x) -> str:
        """Returns 'A' or 'B' based on which side of centre net ball is on."""
        mid_x = (self.cal.centre_net_left[0] + self.cal.centre_net_right[0]) / 2
        return 'A' if x < mid_x else 'B'

    def _velocity(self, p1: BallPosition, p2: BallPosition) -> float:
        return math.sqrt((p2.x - p1.x)**2 + (p2.y - p1.y)**2)

    def _add_event(self, frame: int, event_type: str, description: str):
        self.events.append(GameEvent(
            frame=frame,
            event_type=event_type,
            description=description,
            score_a=self.score_a,
            score_b=self.score_b
        ))

    def process_frame(self, pos: BallPosition):
        frame = pos.frame

        if not pos.visible:
            self.invisible_streak += 1
            if self.invisible_streak >= self.DEAD_BALL_FRAMES and self.state == RallyState.IN_PLAY:
                rally_len = frame - self.rally_start_frame
                if rally_len >= self.MIN_RALLY_FRAMES:
                    self.state = RallyState.DEAD_BALL
                    self._add_event(frame, "dead_ball", f"Ball lost for {self.invisible_streak} frames — rally ended")
            return

        # Ball is visible
        self.invisible_streak = 0

        if self.last_pos and self.last_pos.visible:
            velocity = self._velocity(self.last_pos, pos)

            # --- OUT OF BOUNDS (above top net) ---
            if self._is_above_top_net(pos.x, pos.y) and self.state == RallyState.IN_PLAY:
                losing_side = self._ball_side(pos.x)
                winning_side = 'B' if losing_side == 'A' else 'A'
                if winning_side == 'A':
                    self.score_a += 1
                else:
                    self.score_b += 1
                self._add_event(frame, f"point_team_{winning_side.lower()}",
                    f"Ball went out over top net on side {losing_side} — point to Team {winning_side} ({self.score_a}-{self.score_b})")
                self.state = RallyState.WAITING

            # --- BALL LANDS IN SAND ---
            elif self._is_below_sand_floor(pos.x, pos.y) and self.state == RallyState.IN_PLAY:
                scoring_side = 'A' if self._ball_side(pos.x) == 'B' else 'B'  # lands on opponent's side
                if scoring_side == 'A':
                    self.score_a += 1
                else:
                    self.score_b += 1
                self._add_event(frame, f"point_team_{scoring_side.lower()}",
                    f"Ball landed in sand on side {self._ball_side(pos.x)} — point to Team {scoring_side} ({self.score_a}-{self.score_b})")
                self.state = RallyState.WAITING

            # --- RALLY START (ball moving fast, was in waiting state) ---
            elif self.state in (RallyState.WAITING, RallyState.DEAD_BALL) and velocity > self.STILL_VELOCITY * 2:
                self.state = RallyState.IN_PLAY
                self.rally_start_frame = frame
                self._add_event(frame, "rally_start", f"Rally started at frame {frame}")

            # --- BALL STILL (possible dead ball) ---
            elif velocity < self.STILL_VELOCITY and self.state == RallyState.IN_PLAY:
                # Only declare dead if ball has been slow for a few frames (handled via invisible streak logic above)
                pass

        # Detect serve position
        if self.state == RallyState.WAITING:
            corner = self._is_in_serve_corner(pos.x, pos.y)
            if corner:
                self._add_event(frame, "serve", f"Ball in Team {corner} serve position")

        self.prev_pos = self.last_pos
        self.last_pos = pos

    def run(self, positions: List[BallPosition]):
        for pos in positions:
            self.process_frame(pos)
        return self.events

    def summary(self):
        print(f"\n{'='*50}")
        print(f"FINAL SCORE: Team A {self.score_a} — Team B {self.score_b}")
        print(f"Total events: {len(self.events)}")
        print(f"{'='*50}\n")
        for e in self.events:
            marker = "🏆" if "point" in e.event_type else "🏐" if e.event_type == "rally_start" else "•"
            print(f"  {marker} Frame {e.frame:4d} | {e.description}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ossie AI Ref Game Engine")
    parser.add_argument("--csv", required=True, help="Ball tracking CSV path")
    parser.add_argument("--cal", required=True, help="Court calibration JSON path")
    parser.add_argument("--output", default="events.json", help="Output events JSON")
    args = parser.parse_args()

    cal = load_calibration(args.cal)
    positions = load_ball_csv(args.csv)

    engine = GameEngine(cal)
    events = engine.run(positions)
    engine.summary()

    with open(args.output, 'w') as f:
        json.dump([{
            'frame': e.frame,
            'event_type': e.event_type,
            'description': e.description,
            'score_a': e.score_a,
            'score_b': e.score_b
        } for e in events], f, indent=2)

    print(f"\nEvents saved to {args.output}")
