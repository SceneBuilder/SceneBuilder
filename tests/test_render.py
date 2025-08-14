import pytest
from pathlib import Path

# Skip if Blender's bpy is not available
bpy = pytest.importorskip("bpy", reason="Blender bpy not available")

from scene_builder.workflow.graph import VisualFeedback
from scene_builder.workflow.state import PlacementState
from scene_builder.definition.scene import Room, Object, Vector2, Vector3
from scene_builder.definition.plan import RoomPlan

def test_visual_feedback_renders_png():
    room = Room(
        id="test_room",
        category="living_room",
        boundary=[Vector2(x=4,y=2), Vector2(x=-4,y=2), Vector2(x=-4,y=-2), Vector2(x=4,y=-2)],
        viz=[],
        objects=[Object(
            id="sofa1",
            name="Modern Red Sofa",
            description="test object",
            source="objaverse",
            sourceId="000074a334c541878360457c672b6c2e",
            position=Vector3(x=0,y=0,z=0),
            rotation=Vector3(x=0,y=0,z=0),
            scale=Vector3(x=1,y=1,z=1),
        )],
    )
    state = PlacementState(
        room=room,
        room_plan=RoomPlan(room_description="smoke test"),
        what_to_place=room.objects[0],
        room_history=[],
    )

    class Ctx: pass
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
    test_visual_feedback_renders_png()
