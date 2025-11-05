"""Floorplan-level transforms and orientation utilities."""

from __future__ import annotations

from typing import Optional

import numpy as np
from shapely.geometry import Polygon

from scene_builder.definition.scene import Room, Vector2


def get_dominant_angle(
    polygons: list[Polygon] | list[list[Vector2]], strategy: str = "length_weighted"
) -> float:
    """
    Calculate the dominant angle of a set of polygons for orientation normalization.

    Args:
        polygons: List of shapely Polygon objects or list of list[Vector2] boundaries
        strategy: 'length_weighted' (robust to segmentation), 'count', or 'complex_sum' (length-weighted; more precise)

    Returns:
        Correction angle in degrees to rotate for axis alignment
    """
    angles = []
    edge_lengths = []

    for poly in polygons:
        # Convert to numpy array based on input type
        if isinstance(poly, Polygon):
            coords = np.array(poly.exterior.coords)
        elif isinstance(poly, list) and isinstance(poly[0], Vector2):
            coords = np.array([(v.x, v.y) for v in poly])
        else:
            raise TypeError("Expected shapely Polygon or list[Vector2]")

        vectors = np.diff(coords, axis=0)
        edge_angles = np.arctan2(vectors[:, 1], vectors[:, 0])
        edge_angles_deg = np.rad2deg(edge_angles) % 180
        lengths = np.linalg.norm(vectors, axis=1)

        angles.extend(edge_angles_deg)
        edge_lengths.extend(lengths)

    # Normalize to [0, 90) to treat parallel/perpendicular lines the same
    normalized_angles = np.array([angle % 90 for angle in angles])
    normalized_angles_rad = np.radians(normalized_angles)

    # Compute histogram with optional weighting
    if strategy == "length_weighted":
        hist, bin_edges = np.histogram(
            normalized_angles, bins=90, range=(0, 90), weights=edge_lengths
        )
        dominant_angle_bin = np.argmax(hist)
        dominant_angle = bin_edges[dominant_angle_bin] + 0.5
    elif strategy == "complex_sum":
        # NOTE: based on `length_weighted`, but applies averaging afterwards to
        #       combat histogram-induced bin truncation.
        weights = np.array(edge_lengths)
        hist, bin_edges = np.histogram(normalized_angles, bins=90, range=(0, 90), weights=weights)
        dominant_angle_bin = int(np.argmax(hist))
        bin_indices = np.digitize(normalized_angles, bin_edges, right=False) - 1
        bin_indices = np.clip(bin_indices, 0, len(hist) - 1)
        bin_mask = bin_indices == dominant_angle_bin
        if not np.any(bin_mask):
            bin_mask = np.ones_like(normalized_angles, dtype=bool)

        masked_weights = weights[bin_mask]
        masked_angles = normalized_angles_rad[bin_mask]

        if masked_angles.size == 0:
            dominant_angle = bin_edges[dominant_angle_bin] + 0.5
        else:
            double_angles = 2.0 * masked_angles
            sum_cos = np.sum(masked_weights * np.cos(double_angles))
            sum_sin = np.sum(masked_weights * np.sin(double_angles))

            if np.isclose(sum_cos, 0.0) and np.isclose(sum_sin, 0.0):
                dominant_angle = bin_edges[dominant_angle_bin] + 0.5
            else:
                dominant_angle_rad = 0.5 * np.arctan2(sum_sin, sum_cos)
                dominant_angle = np.rad2deg(dominant_angle_rad)
                dominant_angle = abs(dominant_angle) % 180
                if dominant_angle > 90:
                    dominant_angle = 180 - dominant_angle
    elif strategy == "count":
        hist, bin_edges = np.histogram(normalized_angles, bins=90, range=(0, 90))
        dominant_angle_bin = np.argmax(hist)
        dominant_angle = bin_edges[dominant_angle_bin] + 0.5
    else:
        raise ValueError("Unknown strategy. Use 'length_weighted', 'count', or 'complex_sum'.")

    # Choose smallest rotation to align to 0° or 90°
    if dominant_angle > 45:
        correction_angle = -(dominant_angle - 90)
    else:
        correction_angle = -dominant_angle

    return correction_angle


def rotate_boundary(
    boundary: list[Vector2], angle_degrees: float, origin: tuple[float, float] = (0.0, 0.0)
) -> list[Vector2]:
    """Rotate a room boundary by a given angle around an origin point."""
    if not boundary:
        return boundary

    # Convert to radians
    angle_rad = np.deg2rad(angle_degrees)
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)

    # Rotation matrix
    ox, oy = origin

    rotated = []
    for v in boundary:
        # Translate to origin
        x = v.x - ox
        y = v.y - oy

        # Rotate
        x_new = x * cos_a - y * sin_a
        y_new = x * sin_a + y * cos_a

        # Translate back
        rotated.append(Vector2(x=x_new + ox, y=y_new + oy))

    return rotated


def calculate_floor_plan_centroid(boundaries: list[list[Vector2]]) -> tuple[float, float]:
    """Calculate the centroid of all boundaries for use as rotation/scaling origin."""
    all_x: list[float] = []
    all_y: list[float] = []

    for boundary in boundaries:
        for v in boundary:
            all_x.append(v.x)
            all_y.append(v.y)

    if not all_x:
        return (0.0, 0.0)

    return (sum(all_x) / len(all_x), sum(all_y) / len(all_y))


def scale_boundary(
    boundary: list[Vector2], scale_factor: float, origin: tuple[float, float] = (0.0, 0.0)
) -> list[Vector2]:
    """Scale a room boundary by a given factor around an origin point."""
    if not boundary:
        return boundary

    ox, oy = origin

    scaled: list[Vector2] = []
    for v in boundary:
        # Translate to origin
        x = v.x - ox
        y = v.y - oy

        # Scale
        x_new = x * scale_factor
        y_new = y * scale_factor

        # Translate back
        scaled.append(Vector2(x=x_new + ox, y=y_new + oy))

    return scaled


def scale_floor_plan(
    rooms: list[Room], scale_factor: float, origin: Optional[tuple[float, float]] = None
) -> list[Room]:
    """Scale a floor plan by a given factor.

    Scales each room's boundary and any attached structure boundaries around the
    provided origin (or the global centroid if origin is None).
    """
    if not rooms or scale_factor == 1.0:
        return rooms

    # Calculate centroid if origin not provided
    if origin is None:
        room_boundaries = [room.boundary for room in rooms]
        origin = calculate_floor_plan_centroid(room_boundaries)

    # Scale each room's boundary and structures
    for room in rooms:
        room.boundary = scale_boundary(room.boundary, scale_factor, origin=origin)
        if room.structure:
            for s in room.structure:
                if s.boundary:
                    s.boundary = scale_boundary(s.boundary, scale_factor, origin=origin)

    return rooms


def normalize_floor_plan_orientation(
    rooms: list[Room], strategy: str = "complex_sum", angle_threshold: float = 0.1
) -> tuple[list[Room], float]:
    """
    Normalize the orientation of a floor plan by rotating all rooms to be axis-aligned.

    Rotates each room's boundary and any attached structure boundaries around the
    global centroid used for normalization.

    Returns a tuple of (normalized_rooms, correction_angle).
    """
    if not rooms:
        return rooms, 0.0

    # Calculate orientation correction angle
    room_boundaries = [room.boundary for room in rooms]
    correction_angle = get_dominant_angle(room_boundaries, strategy=strategy)

    # Apply rotation if angle is significant
    if abs(correction_angle) > angle_threshold:
        centroid = calculate_floor_plan_centroid(room_boundaries)

        # Rotate each room's boundary and structures
        for room in rooms:
            room.boundary = rotate_boundary(room.boundary, correction_angle, origin=centroid)
            if room.structure:
                for s in room.structure:
                    if s.boundary:
                        s.boundary = rotate_boundary(s.boundary, correction_angle, origin=centroid)

    return rooms, correction_angle
