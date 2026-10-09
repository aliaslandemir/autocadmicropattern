"""Validated pattern geometry shared by the preview and AutoCAD export."""
from dataclasses import dataclass
import math

import numpy as np

MAX_GRID_RADIUS = 100


@dataclass(frozen=True)
class PatternParameters:
    radius: int = 9
    side_length: float = 16.0
    one_or_two: int = 1
    shape_type: str = "rectangle"
    defect1: tuple = (50.0, 50.0)
    defect2: tuple = (-50.0, -50.0)
    theta0: float = 0.0  # degrees
    m: float = 1.0
    rect_w: float = 22.4
    rect_h: float = 11.2
    triangle_edge: float = 12.0
    shape_circle_r: float = 10.0
    circle_r: float = 45.0
    circle_r2: float = 45.0

    def validate(self):
        if isinstance(self.radius, bool) or not isinstance(self.radius, int):
            raise ValueError("Hex grid radius must be a whole number.")
        if not 0 <= self.radius <= MAX_GRID_RADIUS:
            raise ValueError(f"Hex grid radius must be between 0 and {MAX_GRID_RADIUS}.")
        if self.one_or_two not in (1, 2):
            raise ValueError("Select one or two defects.")
        if self.shape_type not in ("rectangle", "triangle", "circle"):
            raise ValueError("Select a rectangle, triangle, or circle.")
        positive = {"Hex side length": self.side_length}
        if self.shape_type == "rectangle":
            positive.update({"Rectangle width": self.rect_w, "Rectangle height": self.rect_h})
        elif self.shape_type == "triangle":
            positive["Triangle edge length"] = self.triangle_edge
        else:
            positive["Shape circle radius"] = self.shape_circle_r
        for name, value in positive.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a finite positive number.")
        for name, value in (("Angle offset", self.theta0), ("Angle multiplier", self.m)):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite.")
        for index, defect in enumerate((self.defect1, self.defect2)[:self.one_or_two], 1):
            if defect is None or len(defect) != 2 or not all(math.isfinite(v) for v in defect):
                raise ValueError(f"Defect #{index} must contain two finite coordinates (x,y).")
        for name, value in (("Center circle radius", self.circle_r), ("Center circle radius 2", self.circle_r2)):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative (0 disables it).")
        # Reject finite inputs whose derived coordinates would overflow.
        extent = (2 * MAX_GRID_RADIUS + 2) * self.side_length
        shape_extent = max(positive.values())
        defects = (self.defect1, self.defect2)[:self.one_or_two]
        coordinate_extent = max(abs(v) for defect in defects for v in defect)
        bound = max(extent + shape_extent + coordinate_extent, self.circle_r, self.circle_r2)
        if not math.isfinite(4 * bound):
            raise ValueError("Dimensions or coordinates are too large.")
        if not math.isfinite(abs(math.radians(self.theta0)) + abs(self.m) * math.pi):
            raise ValueError("Angle offset or multiplier is too large.")
        return self

    @property
    def center_circle_radii(self):
        """Zero disables a ring; identical radii produce only one entity."""
        return tuple(dict.fromkeys(r for r in (self.circle_r, self.circle_r2) if r > 0))


def generate_hex_grid(radius, side_length):
    """Return flat-top hex centers in the original row-major axial order."""
    PatternParameters(radius=radius, side_length=side_length).validate()
    # Allocate only valid cells rather than a full square mesh and mask.
    rows = []
    for r in range(-radius, radius + 1):
        q = np.arange(max(-radius, -radius-r), min(radius, radius-r) + 1)
        rows.append(np.column_stack((1.5 * side_length * q,
                                    math.sqrt(3) * side_length * (r + 0.5*q))))
    return np.concatenate(rows)


def hexagon_xy(center, size):
    angles = np.linspace(0, 2 * np.pi, 7)
    vertices = np.asarray(center) + size * np.column_stack((np.cos(angles), np.sin(angles)))
    return vertices[:, 0], vertices[:, 1]


def orientation_angle_1_defect(center, defect, theta0, m):
    return theta0 + m * math.atan2(center[1]-defect[1], center[0]-defect[0])


def orientation_angle_2_defects(center, defects, theta0):
    return theta0 + sum(math.atan2(center[1]-d[1], center[0]-d[0]) for d in defects)


def orientation_angles(centers, params):
    theta0 = math.radians(params.theta0)
    if params.one_or_two == 1:
        delta = centers - params.defect1
        return theta0 + params.m * np.arctan2(delta[:, 1], delta[:, 0])
    result = np.full(len(centers), theta0)
    for defect in (params.defect1, params.defect2):
        delta = centers - defect
        result += np.arctan2(delta[:, 1], delta[:, 0])
    return result


def shape_vertices(centers, angles, params):
    """Return NxVx2 world coordinates for rectangle or triangle shapes."""
    if params.shape_type == "rectangle":
        points = np.array([[-params.rect_w/2, -params.rect_h/2],
                           [params.rect_w/2, -params.rect_h/2],
                           [params.rect_w/2, params.rect_h/2],
                           [-params.rect_w/2, params.rect_h/2]])
    elif params.shape_type == "triangle":
        h = math.sqrt(3) * params.triangle_edge / 2
        points = np.array([[-params.triangle_edge/2, -h/3],
                           [params.triangle_edge/2, -h/3], [0, 2*h/3]])
    else:
        raise ValueError("Circle shapes do not have polygon vertices.")
    c, s = np.cos(angles)[:, None], np.sin(angles)[:, None]
    x = c * points[:, 0] - s * points[:, 1]
    y = s * points[:, 0] + c * points[:, 1]
    return np.stack((x, y), axis=-1) + centers[:, None, :]
