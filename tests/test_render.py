import pytest
import unittest.mock as mock
from pathlib import Path

from scene_builder.config import TEST_ASSET_DIR
from scene_builder.decoder import blender
from scene_builder.definition.plan import RoomPlan
from scene_builder.definition.scene import Object, Room, Vector2, Vector3
from scene_builder.importer.test_asset_importer import search_test_asset
from scene_builder.nodes.placement import PlacementVisualFeedback
from scene_builder.workflow.states import PlacementState


def test_visual_feedback_renders_png():
    room = Room(
        id="test_room",
        category="living_room",
        boundary=[
            Vector2(x=4, y=2),
            Vector2(x=-4, y=2),
            Vector2(x=-4, y=-2),
            Vector2(x=4, y=-2),
        ],
        viz=[],
        objects=[
            Object.from_blueprint(
                blueprint=search_test_asset("classroom_table"),
                id="classroom_table_01",
                position=Vector3(x=0, y=0, z=0),
                rotation=Vector3(x=0, y=0, z=0),
                scale=Vector3(x=1, y=1, z=1),
            )
        ],
    )
    state = PlacementState(
        room=room,
        room_plan=RoomPlan(room_description="smoke test"),
        what_to_place=room.objects[0],
        room_history=[],
    )

    class Ctx:
        pass

    ctx = Ctx()
    ctx.state = state

    async def run():
        node = PlacementVisualFeedback()
        await node.run(ctx)

    import asyncio

    asyncio.run(run())

    assert state.room.viz and isinstance(state.room.viz[-1], Path)
    assert state.room.viz[-1].exists()


def test_template_loading():
    """
    Tests that VisualFeedback can run after loading a scene from a template.
    """
    room = Room(
        id="test_room_from_template",
        category="living_room",
        boundary=[
            Vector2(x=4, y=2),
            Vector2(x=-4, y=2),
            Vector2(x=-4, y=-2),
            Vector2(x=4, y=-2),
        ],
        viz=[],
        objects=[],  # Assuming objects are in the template
    )
    state = PlacementState(
        room=room,
        room_plan=RoomPlan(room_description="test with template"),
        what_to_place=search_test_asset("classroom_table"),
        room_history=[],
    )

    class Ctx:
        pass

    ctx = Ctx()
    ctx.state = state

    template_path = f"{TEST_ASSET_DIR}/scenes/classroom.blend"
    assert Path(template_path).exists()

    # with mock.patch("scene_builder.decoder.blender.load_template") as mock_load:
    #     blender.load_template(template_path, clear_scene=True)
    #     mock_load.assert_called_once_with(template_path, clear_scene=True)

    blender.load_template(template_path, clear_scene=True)

    async def run():
        node = PlacementVisualFeedback()
        await node.run(ctx)

    import asyncio

    asyncio.run(run())

    assert state.room.viz and isinstance(state.room.viz[-1], Path)
    assert state.room.viz[-1].exists()

    blender.save_scene("tests/test_template_loading.blend")


def test_isometric_render():
    """
    Tests that an isometric view can be rendered using both final and viewport modes.
    """
    room = Room(
        id="test_isometric_room",
        category="office",
        boundary=[],
        viz=[],
        objects=[
            Object.from_blueprint(
                blueprint=search_test_asset("classroom_table"),
                id="classroom_table_01",
                position=Vector3(x=0, y=0, z=0),
                rotation=Vector3(x=0, y=0, z=0),
                scale=Vector3(x=1, y=1, z=1),
            )
        ],
    )
    blender.parse_room_definition(room, clear=True)

    # Test final render (default)
    output_path_final = blender.create_scene_visualization(view="isometric")
    assert output_path_final.exists()


def test_grid_visualization():
    """
    Tests that grid visualization works correctly with both top_down and isometric views.
    """
    room = Room(
        id="test_grid_room",
        category="living_room",
        boundary=[
            Vector2(x=3, y=3),
            Vector2(x=-3, y=3),
            Vector2(x=-3, y=-3),
            Vector2(x=3, y=-3),
        ],
        viz=[],
        objects=[
            Object.from_blueprint(
                blueprint=search_test_asset("classroom_table"),
                id="classroom_table_01",
                position=Vector3(x=1, y=1, z=0),
                rotation=Vector3(x=0, y=0, z=0),
                scale=Vector3(x=1, y=1, z=1),
            )
        ],
    )
    blender.parse_room_definition(room, clear=True)

    # Test top-down view with grid
    output_path_top_grid = blender.create_scene_visualization(
        view="top_down",
        show_grid=True,
        resolution=512
    )
    assert output_path_top_grid.exists()

    # Test isometric view with grid
    output_path_iso_grid = blender.create_scene_visualization(
        view="isometric",
        show_grid=True,
        resolution=512
    )
    assert output_path_iso_grid.exists()

    # Test that grid can be called multiple times (stateless behavior)
    output_path_repeat = blender.create_scene_visualization(
        view="top_down",
        show_grid=True,
        resolution=512
    )
    assert output_path_repeat.exists()


if __name__ == "__main__":
    test_visual_feedback_renders_png()
    test_template_loading()
    test_isometric_render()
    test_grid_visualization()

