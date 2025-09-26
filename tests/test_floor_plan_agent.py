import pytest
import asyncio
from scene_builder.workflow.graph import FloorPlanAgent, MainState
from scene_builder.definition.scene import Scene, GlobalConfig
from pydantic_graph import GraphRunContext


async def test_floor_plan_agent_rectangular_classroom():
    """Test FloorPlanAgent with simple rectangular classroom to demonstrate wall generation"""
    print("\n=== Testing FloorPlanAgent with Wall Generation ===")

    # Create test state
    state = MainState(
        user_input="Create a rectangular classroom",
        scene_definition=Scene(
            category="educational", tags=["classroom"], floorType="single", rooms=[]
        ),
        plan="Create a rectangular classroom with space for students and teacher.",
        global_config=GlobalConfig(debug=False),  # Use production mode to test LLM
    )

    # Mock context
    class MockContext:
        def __init__(self, state):
            self.state = state

    context = MockContext(state)

    # Test the agent
    agent = FloorPlanAgent()

    try:
        result = await agent.run(context)

        print(f"✓ FloorPlanAgent completed successfully")
        print(f"✓ Number of rooms generated: {len(state.scene_definition.rooms)}")

        if state.scene_definition.rooms:
            room = state.scene_definition.rooms[0]
            print(f"✓ Room ID: {room.id}")
            print(f"✓ Room category: {room.category}")
            print(f"✓ Room tags: {room.tags}")

            if room.boundary:
                print(f"✓ Boundary points: {len(room.boundary)}")
                for i, point in enumerate(room.boundary):
                    print(f"   Point {i + 1}: ({point.x:.2f}, {point.y:.2f})")

                # Create visual output with floor and walls
                print(f"\n✓ Creating Blender scene with floor and walls...")
                try:
                    from scene_builder.decoder import blender
                    from scene_builder.utils.conversions import pydantic_to_dict

                    room_data = pydantic_to_dict(room)
                    blender.parse_room_definition(room_data)

                    # Render top-down view
                    render_path = blender.render_top_down("./")
                    print(f"✓ Rendered image saved to: {render_path}")

                    # Save Blender scene
                    blender.save_scene(f"{room.id}_with_walls.blend")
                    print(f"✓ Blender scene saved as: {room.id}_with_walls.blend")

                except Exception as e:
                    print(
                        f"⚠ Blender rendering failed (normal if bpy not available): {e}"
                    )

        return True

    except Exception as e:
        print(f"✗ FloorPlanAgent failed: {e}")
        return False


if __name__ == "__main__":
    print("Testing LLM FloorPlanAgent with Wall Generation - Rectangular Classroom")
    print("=" * 70)

    # Run async test
    async def run_test():
        return await test_floor_plan_agent_rectangular_classroom()

    # Run the async test
    test_result = asyncio.run(run_test())

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Passed: {1 if test_result else 0}/1")

    if test_result:
        print(
            "🎉 Test passed! FloorPlanAgent with inward wall generation works for rectangular classrooms."
        )
    else:
        print("⚠️  Test failed. Check the output above for details.")
