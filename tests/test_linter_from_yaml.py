import asyncio
from pathlib import Path

import pytest
from rich import print as rprint

from scene_builder.decoder.blender import blender
from scene_builder.decoder.blender.blender import parse_room_definition, parse_scene_definition
from scene_builder.definition.plan import RoomPlan
from scene_builder.definition.scene import Object, Room, Scene
from scene_builder.nodes.design import apply_resolution_actions
from scene_builder.utils.conversions import pydantic_from_yaml
from scene_builder.validation import (
    AABB,
    LintingOptions,
    LintSeverity,
    format_lint_feedback,
    lint_room,
    lint_scene,
    save_lint_visualization,
)
from scene_builder.validation.rules import WallOverlapRule
from scene_builder.validation.resolver import IssueResolver
from scene_builder.validation.tracker import IssueTracker
from scene_builder.workflow.states import RoomDesignState

# params
linting_options = LintingOptions(rules=(WallOverlapRule(),))

# single
# TEST_CASE = "test_single_room_design_workflow_bar"
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


def test_auto_resolution_from_yaml_file(options=None):
    """
    Tests automatic lint resolution in isolation.

    This mimics the design loop by:
    - Loading a saved room YAML
    - Seeding an IssueTracker with an actual lint report
    - Calling IssueResolver (uses issue_resolution_agent) to propose a patch
    - Applying the resolver's output back into the room
    """
    room = pydantic_from_yaml(TEST_ROOM_PATH, Room)
    output_base = TEST_ROOM_PATH.with_name(f"{TEST_CASE}_auto_resolver")

    # Lint and log/visualize state (before)
    parse_room_definition(room)
    report = lint_room(room, options=options)
    rprint("[bold magenta]Before resolution:[/]")
    rprint(format_lint_feedback(report))

    blender.visualize(scene=room.id, output_dir=str(output_base), show_grid=True)
    blender.visualize(scene=room.id, output_dir=str(output_base), view="isometric", show_grid=True)
    save_lint_visualization(
        room,
        report,
        output_base.with_name(f"{output_base.name}_lint_before.png")
    )  # fmt:skip
    blender.save_scene(f"{output_base}_before.blend")

    # Set up issue tracker and run auto resolution
    tracker = IssueTracker()
    tracker.sync(report)
    issue_lookup = {tracker.compute_issue_id(item): item for item in report.issues}
    state = RoomDesignState(room=room, room_plan=RoomPlan(room_description="test"))
    resolver = IssueResolver(state=state, max_attempts=1, console=None)
    results = asyncio.run(resolver.attempt_auto_resolution(tracker, issue_lookup))
    apply_resolution_actions(room, results)

    # Lint and log/visualize state (after)
    parse_room_definition(room)
    updated_report = lint_room(room)
    rprint("[bold magenta]After lint feedback:[/]")
    rprint(format_lint_feedback(updated_report))

    blender.visualize(scene=room.id, output_dir=str(output_base), show_grid=True)
    blender.visualize(scene=room.id, output_dir=str(output_base), view="isometric", show_grid=True)
    save_lint_visualization(
        room,
        updated_report,
        output_base.with_name(f"{output_base.name}_lint_after.png"),
    )
    blender.save_scene(f"{output_base}_after.blend")


if __name__ == "__main__":
    # test_lint_room_from_yaml_file()
    # test_lint_scene_from_yaml_file()
    # test_auto_resolution_from_yaml_file()
    test_auto_resolution_from_yaml_file(linting_options)

    # # Allow running this test module directly
    # raise SystemExit(pytest.main([str(Path(__file__).resolve())]))
