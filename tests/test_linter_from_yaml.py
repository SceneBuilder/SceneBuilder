from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scene_builder.definition.scene import Object, Room
from scene_builder.lint import AABB, LintSeverity, lint_room
from scene_builder.utils.conversions import pydantic_from_yaml


TEST_ROOM_PATH = Path(__file__).resolve().parents[0] / "data" / "lint_sample_room.yaml"


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


def test_lint_room_from_yaml_file():
    room = pydantic_from_yaml(TEST_ROOM_PATH, Room)

    report = lint_room(room, size_provider=_world_bounds_from_scale)

    codes = {issue.code for issue in report.issues}
    assert {"floor_penetration", "wall_overlap", "object_overlap"}.issubset(codes)

    severities = {issue.code: issue.severity for issue in report.issues}
    assert severities["floor_penetration"] is LintSeverity.ERROR
