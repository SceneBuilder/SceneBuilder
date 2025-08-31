import pytest
import unittest.mock as mock
from pathlib import Path

from scene_builder.database.object import ObjectDatabase
from scene_builder.decoder import blender
from scene_builder.definition.plan import RoomPlan
from scene_builder.definition.scene import Room, Object, Vector2, Vector3, Scene
from scene_builder.importer.test_asset_importer import search_test_asset
from scene_builder.utils.conversions import pydantic_to_dict
from scene_builder.utils.conversions import pydantic_from_yaml
from scene_builder.workflow.graphs import VisualFeedback
from scene_builder.workflow.states import PlacementState


obj_db = ObjectDatabase()


def test_scene_building_from_yaml():
    """Tests building a Blender scene from YAML data."""
    scene_data = pydantic_from_yaml("scenes/generated_scene.yaml", Scene)
    blender.parse_scene_definition(scene_data)
    blender.save_scene("output.blend")
    print("\nBlender scene created successfully from YAML data.")


def test_template_blend_loading():
    """
    Tests that template loading works correctly.
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

    template_path = "test_assets/scenes/classroom.blend"
    assert Path(template_path).exists()

    blender.load_template(template_path, clear_scene=True)
    blender.parse_room_definition(dict(room), clear=False)
    blender.save_scene("tests/test_template_loading.blend")


def test_isometric_render():
    """
    Tests that an isometric view can be rendered.
    """
    room = Room(
        id="test_isometric_room",
        category="office",
        boundary=[],
        viz=[],
        objects=[
            Object(
                # **pydantic_to_dict(search_test_asset("sofa")),
                **pydantic_to_dict(obj_db.query("sofa")[0]),
                id="desk",
                position=Vector3(x=0, y=0, z=0),
                rotation=Vector3(x=0, y=0, z=0),
                scale=Vector3(x=1, y=1, z=1),
            )
        ],
    )
    blender.parse_room_definition(dict(room), clear=True)
    output_path = blender.create_scene_visualization(view="isometric")
    assert output_path.exists()
    blender.save_scene("debug.blend")


def test_top_down_render():
    """
    Tests that a top-down view can be rendered.
    """
    room = Room(
        id="test_top_down_room",
        category="office",
        boundary=[],
        viz=[],
        objects=[
            Object(
                # **pydantic_to_dict(search_test_asset("sofa")),
                **pydantic_to_dict(obj_db.query("sofa")[0]),
                id="desk",
                position=Vector3(x=0, y=0, z=0),
                rotation=Vector3(x=0, y=0, z=0),
                scale=Vector3(x=1, y=1, z=1),
            )
        ],
    )
    blender.parse_room_definition(dict(room), clear=True)
    output_path = blender.create_scene_visualization(view="top_down")
    assert output_path.exists()


def test_visual_feedback_workflow():
    """Tests the VisualFeedback workflow node integration."""
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
            Object(
                # **pydantic_to_dict(search_test_asset("sofa")),
                **pydantic_to_dict(obj_db.query("sofa")[0]),
                id="sofa1",
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
        node = VisualFeedback()
        await node.run(ctx)

    import asyncio

    asyncio.run(run())

    assert state.room.viz and isinstance(state.room.viz[-1], Path)
    assert state.room.viz[-1].exists()


if __name__ == "__main__":
    test_scene_building_from_yaml()
    test_template_blend_loading()
    test_isometric_render()
    test_top_down_render()
    test_visual_feedback_workflow()
