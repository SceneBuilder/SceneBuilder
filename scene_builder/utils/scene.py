"""Scene-level utility functions for normalization and transforms."""

from __future__ import annotations

import math
from typing import Any

import bpy
from mathutils import Vector

from scene_builder.definition.scene import Scene, Vector2
from scene_builder.utils.conversions import pydantic_to_dict
from scene_builder.utils.floorplan import get_dominant_angle


def recenter_scene(scene: Scene | dict[str, Any], rotate: bool = True) -> dict[str, Any]:
    """
    Return a new scene dict with all rooms translated to origin and optionally rotated.

    - Computes a global centroid across all room boundary vertices.
    - Translates all room boundaries by subtracting this centroid.
    - If ``rotate`` is True, rotates boundaries to align dominant wall directions to axes.
    - Also transforms per-room structures and objects if present.

    The input is not mutated; a new dictionary is returned. No origin metadata is recorded.

    Args:
        scene: Scene model or dict with a ``rooms`` list containing boundaries/objects/structures.
        rotate: Whether to align orientation by rotating after recentring (default: True).

    Returns:
        New scene dictionary with transformed coordinates.
    """
    # Normalize input into a pure dict so we don't mutate original models
    scene_dict: dict[str, Any] = pydantic_to_dict(scene)

    rooms = scene_dict.get("rooms", []) or []
    if not rooms:
        return scene_dict

    # 1) Compute global centroid from all room boundary points
    all_boundaries: list[list[Vector2]] = []
    xs: list[float] = []
    ys: list[float] = []
    for room in rooms:
        boundary = room.get("boundary")
        if not boundary:
            continue
        # Convert to Vector2 sequence if needed
        boundary_vec = (
            [Vector2(x=p["x"], y=p["y"]) for p in boundary]
            if isinstance(boundary[0], dict)
            else boundary
        )
        all_boundaries.append(boundary_vec)
        for v in boundary_vec:
            xs.append(v.x)
            ys.append(v.y)

    if not xs:
        return scene_dict

    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)

    # 2) Compute rotation (dominant orientation) if requested
    theta = 0.0
    if rotate:
        centered = [[Vector2(x=p.x - cx, y=p.y - cy) for p in b] for b in all_boundaries]
        theta = math.radians(get_dominant_angle(centered, strategy="complex_sum"))

    cos_a, sin_a = math.cos(theta), math.sin(theta)

    # 3) Apply transform to room boundaries, structures, and objects
    for room in rooms:
        # Boundary
        boundary = room.get("boundary")
        if boundary:
            for pt in boundary:
                x = pt["x"] - cx
                y = pt["y"] - cy
                pt["x"] = x * cos_a - y * sin_a
                pt["y"] = x * sin_a + y * cos_a

        # Structures (e.g., doors/windows) boundaries
        structures = room.get("structure") or []
        for s in structures:
            sb = s.get("boundary")
            if not sb:
                continue
            for p in sb:
                x = p["x"] - cx
                y = p["y"] - cy
                p["x"] = x * cos_a - y * sin_a
                p["y"] = x * sin_a + y * cos_a

        # Objects (positions)
        objs = room.get("objects", []) or []
        for obj in objs:
            pos = obj.get("position")
            if not pos:
                continue
            x = pos.get("x", 0.0) - cx
            y = pos.get("y", 0.0) - cy
            pos["x"] = x * cos_a - y * sin_a
            pos["y"] = x * sin_a + y * cos_a

    return scene_dict


def calculate_scene_bounds():
    """Calculate the bounding box of all visible objects in the scene.

    Returns:
        tuple: (min_x, max_x, min_y, max_y, min_z, max_z) or None if no objects
    """
    objects = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH"
        and obj.visible_get()
        and not obj.name.startswith("Grid_")
        and not obj.name.startswith("X_Axis_")
        and not obj.name.startswith("Y_Axis_")
    ]

    if not objects:
        return None

    # Initialize with first object's bounds
    first_obj = objects[0]
    bbox_corners = [first_obj.matrix_world @ Vector(corner) for corner in first_obj.bound_box]

    min_x = min(v.x for v in bbox_corners)
    max_x = max(v.x for v in bbox_corners)
    min_y = min(v.y for v in bbox_corners)
    max_y = max(v.y for v in bbox_corners)
    min_z = min(v.z for v in bbox_corners)
    max_z = max(v.z for v in bbox_corners)

    # Extend bounds with remaining objects
    for obj in objects[1:]:
        bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        min_x = min(min_x, min(v.x for v in bbox_corners))
        max_x = max(max_x, max(v.x for v in bbox_corners))
        min_y = min(min_y, min(v.y for v in bbox_corners))
        max_y = max(max_y, max(v.y for v in bbox_corners))
        min_z = min(min_z, min(v.z for v in bbox_corners))
        max_z = max(max_z, max(v.z for v in bbox_corners))

    return (min_x, max_x, min_y, max_y, min_z, max_z)
