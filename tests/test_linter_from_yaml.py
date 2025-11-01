from pathlib import Path

import pytest
from rich import print as rprint

from scene_builder.decoder.blender.blender import parse_room_definition, parse_scene_definition
from scene_builder.definition.scene import Object, Room, Scene
from scene_builder.lint import (
    AABB,
    LintSeverity,
    format_lint_feedback,
    lint_room,
    lint_scene,
    save_lint_visualization,
)
from scene_builder.utils.conversions import pydantic_from_yaml

# single
TEST_CASE = "test_single_room_design_workflow_classroom"

# multi
# TEST_CASE = "test_multi_room_design_workflow_recording_studio"

TEST_ROOM_PATH = Path(__file__).resolve().parents[1] / "test_output" / f"{TEST_CASE}.yaml"


def test_lint_room_from_yaml_file():
    room = pydantic_from_yaml(TEST_ROOM_PATH, Room)
    parse_room_definition(room)

    report = lint_room(room)

    # print(format_lint_feedback(report))
    rprint(format_lint_feedback(report))

    save_lint_visualization(
        room,
        report,
        TEST_ROOM_PATH.with_name(f"{TEST_CASE}_lint.jpg"),
    )

def test_lint_scene_from_yaml_file():
    scene_case = "test_multi_room_design_workflow_recording_studio"
    scene_yaml = Path(__file__).resolve().parents[1] / "test_output" / f"{scene_case}.yaml"

    scene = pydantic_from_yaml(scene_yaml, Scene)
    parse_scene_definition(scene)

    reports = lint_scene(scene)

    for report in reports:
        print(format_lint_feedback(report))


if __name__ == "__main__":
    test_lint_room_from_yaml_file()
    # test_lint_scene_from_yaml_file()

    # # Allow running this test module directly
    # raise SystemExit(pytest.main([str(Path(__file__).resolve())]))
