"""Integration tests for Blender-backed overlap verification."""

from __future__ import annotations

import bpy

from scene_builder.decoder.blender import blender
from scene_builder.definition.scene import Object, Room, Vector2, Vector3
from scene_builder.validation import LintingOptions, lint_room


def _reset_scene() -> None:
    """Clear the Blender scene and associated trackers."""

    blender._clear_scene()  # type: ignore[attr-defined]


def _register_tracked_cube(object_id: str, location: tuple[float, float, float]) -> Object:
    """Create a cube in Blender, register it with the tracker, and return its Object model."""

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    cube = bpy.context.active_object
    assert cube is not None
    cube.name = object_id

    obj = Object(
        name=object_id,
        id=object_id,
        source="test_asset",
        source_id=object_id,
        description="Test cube",
        position=Vector3(x=location[0], y=location[1], z=location[2]),
        rotation=Vector3(x=0.0, y=0.0, z=0.0),
        scale=Vector3(x=1.0, y=1.0, z=1.0),
    )

    blender._scene_tracker.register_object(  # type: ignore[attr-defined]
        {
            "id": object_id,
            "source_id": object_id,
            "position": {"x": location[0], "y": location[1], "z": location[2]},
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
            "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
        },
        cube.name,
    )

    return obj


def _lint_for_overlap(objects: list[Object]) -> tuple[list[str], list[str]]:
    room = Room(
        id="bvh_room",
        boundary=[
            Vector2(x=0.0, y=0.0),
            Vector2(x=4.0, y=0.0),
            Vector2(x=4.0, y=4.0),
            Vector2(x=0.0, y=4.0),
        ],
        objects=objects,
    )
    options = LintingOptions(enabled_rules={"object_overlap"})
    report = lint_room(room, options=options)
    codes = [issue.code for issue in report.issues]
    object_ids = [issue.object_id for issue in report.issues if issue.code == "object_overlap"]
    return codes, object_ids


def test_blender_bvh_filters_vertical_separation():
    _reset_scene()
    low = _register_tracked_cube("cube_low", (0.0, 0.0, 0.5))
    high = _register_tracked_cube("cube_high", (0.0, 0.0, 5.0))

    codes, _ = _lint_for_overlap([low, high])

    assert "object_overlap" not in codes


def test_blender_bvh_detects_real_overlap():
    _reset_scene()
    base = _register_tracked_cube("cube_a", (0.0, 0.0, 0.5))
    stacked = _register_tracked_cube("cube_b", (0.0, 0.0, 0.5))

    codes, offenders = _lint_for_overlap([base, stacked])

    assert "object_overlap" in codes
    assert offenders == ["cube_a,cube_b"]
