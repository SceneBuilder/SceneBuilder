from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest

from scene_builder.definition.scene import Object, Room, Scene, Vector2, Vector3
from scene_builder.lint import (
    AABB,
    LintingOptions,
    lint_room,
    lint_scene,
    LintSeverity,
)


def _make_object(
    object_id: str, *, position: tuple[float, float, float], scale: tuple[float, float, float]
) -> Object:
    return Object(
        id=object_id,
        name=object_id,
        description="",
        source="objaverse",
        source_id=object_id,
        position=Vector3(x=position[0], y=position[1], z=position[2]),
        rotation=Vector3(x=0.0, y=0.0, z=0.0),
        scale=Vector3(x=scale[0], y=scale[1], z=scale[2]),
    )


def _world_bounds_from_scale(obj: Object) -> AABB:
    half_x = obj.scale.x / 2.0
    half_y = obj.scale.y / 2.0
    half_z = obj.scale.z / 2.0
    return AABB(
        min_corner=(
            obj.position.x - half_x,
            obj.position.y - half_y,
            obj.position.z - half_z,
        ),
        max_corner=(
            obj.position.x + half_x,
            obj.position.y + half_y,
            obj.position.z + half_z,
        ),
    )


def _square_room(objects: list[Object]) -> Room:
    return Room(
        id="room",
        category="test",
        boundary=[
            Vector2(x=0.0, y=0.0),
            Vector2(x=4.0, y=0.0),
            Vector2(x=4.0, y=4.0),
            Vector2(x=0.0, y=4.0),
        ],
        objects=objects,
    )


def _l_shaped_room(objects: list[Object]) -> Room:
    return Room(
        id="irregular",
        category="test",
        boundary=[
            Vector2(x=0.0, y=0.0),
            Vector2(x=4.0, y=0.0),
            Vector2(x=4.0, y=4.0),
            Vector2(x=2.0, y=4.0),
            Vector2(x=2.0, y=2.0),
            Vector2(x=0.0, y=2.0),
        ],
        objects=objects,
    )


def test_lint_room_detects_floor_wall_and_overlap():
    floor_overlap = _make_object("floor", position=(1.0, 1.0, -0.1), scale=(1.0, 1.0, 1.0))
    wall_overlap = _make_object("wall", position=(3.8, 2.0, 0.5), scale=(1.5, 1.0, 1.0))
    oversized = _make_object("oversized", position=(2.0, 2.0, 0.5), scale=(6.0, 6.0, 1.0))
    overlap_a = _make_object("overlap_a", position=(1.5, 1.5, 0.5), scale=(1.0, 1.0, 1.0))
    overlap_b = _make_object("overlap_b", position=(1.7, 1.5, 0.5), scale=(1.0, 1.0, 1.0))

    room = _square_room([floor_overlap, wall_overlap, oversized, overlap_a, overlap_b])

    report = lint_room(room, size_provider=_world_bounds_from_scale)

    codes = {issue.code for issue in report.issues}
    assert "floor_overlap" in codes
    assert "wall_overlap" in codes
    assert "dominates_room" in codes
    assert "object_overlap" in codes

    severities = {issue.code: issue.severity for issue in report.issues}
    assert severities["floor_overlap"] is LintSeverity.ERROR
    assert severities["object_overlap"] is LintSeverity.ERROR

    floor_penetration = next(issue for issue in report.issues if issue.code == "floor_penetration")
    assert floor_penetration.hint is not None
    assert "Translate" in floor_penetration.hint


def test_lint_scene_runs_all_rooms():
    room_a = _square_room([_make_object("a", position=(1.0, 1.0, 0.0), scale=(1.0, 1.0, 1.0))])
    room_b = _square_room([_make_object("b", position=(1.0, 1.0, -0.2), scale=(1.0, 1.0, 1.0))])
    scene = Scene(category="test", height_class="single_story", rooms=[room_a, room_b], tags=None)

    reports = lint_scene(scene, size_provider=_world_bounds_from_scale)
    assert len(reports) == 2
    assert any(issue.code == "floor_overlap" for issue in reports[1].issues)


def test_lint_room_respects_provider_bounding_box_offsets():
    floating_origin = _make_object("offset", position=(1.0, 1.0, 0.2), scale=(1.0, 1.0, 1.0))

    def provider(_: Object) -> AABB:
        return AABB(
            min_corner=(0.5, 0.5, -0.2),
            max_corner=(1.5, 1.5, 0.8),
        )

    room = _square_room([floating_origin])

    report = lint_room(room, size_provider=provider)
    codes = {issue.code for issue in report.issues}
    assert "floor_penetration" in codes


def test_lint_room_detects_irregular_boundary_overlap():
    intruding = _make_object("intrude", position=(1.5, 3.0, 0.5), scale=(1.0, 1.0, 1.0))
    room = _l_shaped_room([intruding])

    report = lint_room(room, size_provider=_world_bounds_from_scale)

    assert any(issue.code == "wall_overlap" for issue in report.issues)


def test_lint_room_respects_rule_selection():
    floor_overlap = _make_object("floor", position=(1.0, 1.0, -0.1), scale=(1.0, 1.0, 1.0))
    wall_overlap = _make_object("wall", position=(3.8, 2.0, 0.5), scale=(1.5, 1.0, 1.0))
    room = _square_room([floor_overlap, wall_overlap])

    options = LintingOptions(enabled_rules={"floor_penetration"})
    report = lint_room(room, size_provider=_world_bounds_from_scale, options=options)

    codes = {issue.code for issue in report.issues}
    assert codes == {"floor_penetration"}
