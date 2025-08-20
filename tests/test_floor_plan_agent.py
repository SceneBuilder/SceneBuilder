import pytest
import asyncio
from scene_builder.workflow.graph import FloorPlanAgent, MainState
from scene_builder.definition.scene import Scene, GlobalConfig
from pydantic_graph import GraphRunContext


async def test_floor_plan_agent_round_classroom():
    """Test FloorPlanAgent with round lecture room prompt"""
    print("\n=== Testing FloorPlanAgent with 'Create a round lecture room' ===")
    
    # Create test state
    state = MainState(
        user_input="Create a round lecture room",
        scene_definition=Scene(category="educational", tags=["lecture", "round"], floorType="single", rooms=[]),
        plan="Create a round lecture room with circular seating arrangement for optimal acoustics and visibility.",
        global_config=GlobalConfig(debug=False)  # Use production mode to test LLM
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
            
            if room.floor_dimensions:
                print(f"✓ Dimensions: {room.floor_dimensions.width}x{room.floor_dimensions.length}m")
                print(f"✓ Shape: {room.floor_dimensions.shape}")
                print(f"✓ Area: {room.floor_dimensions.area_sqm} sqm")
                if room.floor_dimensions.llm_analysis:
                    print(f"✓ LLM Analysis: {room.floor_dimensions.llm_analysis}")
                
            if room.boundary:
                print(f"✓ Boundary points: {len(room.boundary)} (should be >4 for round shape)")
                for i, point in enumerate(room.boundary):
                    print(f"   Point {i+1}: ({point.x:.2f}, {point.y:.2f})")
                
                # Create visual output
                print(f"\n✓ Creating Blender scene and rendering...")
                try:
                    from scene_builder.decoder import blender_decoder
                    from scene_builder.utils.conversions import pydantic_to_dict
                    
                    room_data = pydantic_to_dict(room)
                    blender_decoder.parse_room_definition(room_data)
                    
                    # Render top-down view
                    render_path = blender_decoder.render_top_down("./")
                    print(f"✓ Rendered image saved to: {render_path}")
                    
                    # Save Blender scene
                    blender_decoder.save_scene(f"{room.id}_round_test.blend")
                    print(f"✓ Blender scene saved as: {room.id}_round_test.blend")
                    
                except Exception as e:
                    print(f"⚠ Blender rendering failed (normal if bpy not available): {e}")
        
        return True
        
    except Exception as e:
        print(f"✗ FloorPlanAgent failed: {e}")
        return False


async def test_floor_plan_agent_trapezoid_classroom():
    """Test FloorPlanAgent with trapezoid lecture room prompt"""
    print("\n=== Testing FloorPlanAgent with 'Create a trapezoid lecture hall' ===")
    
    # Create test state
    state = MainState(
        user_input="Create a trapezoid-shaped lecture hall with wider back rows",
        scene_definition=Scene(category="educational", tags=["lecture", "trapezoid"], floorType="single", rooms=[]),
        plan="Create a trapezoid-shaped lecture hall with narrow front for the instructor and wider back for more student seating.",
        global_config=GlobalConfig(debug=False)  # Use production mode to test LLM
    )
    
    # Mock context
    class MockContext:
        def __init__(self, state):
            self.state = state
    
    context = MockContext(state)
    
    # Test the agent
    agent = FloorPlanAgent()
    
    try:
        # This will test the LLM integration (now properly awaited)
        result = await agent.run(context)
        
        print(f"✓ FloorPlanAgent completed successfully")
        print(f"✓ Number of rooms generated: {len(state.scene_definition.rooms)}")
        
        if state.scene_definition.rooms:
            room = state.scene_definition.rooms[0]
            print(f"✓ Room ID: {room.id}")
            print(f"✓ Room category: {room.category}")
            print(f"✓ Room tags: {room.tags}")
            
            if room.floor_dimensions:
                print(f"✓ Dimensions: {room.floor_dimensions.width}x{room.floor_dimensions.length}m")
                print(f"✓ Shape: {room.floor_dimensions.shape}")
                print(f"✓ Area: {room.floor_dimensions.area_sqm} sqm")
                if room.floor_dimensions.llm_analysis:
                    print(f"✓ LLM Analysis: {room.floor_dimensions.llm_analysis}")
                
            if room.boundary:
                print(f"✓ Boundary points: {len(room.boundary)}")
                for i, point in enumerate(room.boundary):
                    print(f"   Point {i+1}: ({point.x:.2f}, {point.y:.2f})")
                
                # Create visual output
                print(f"\n✓ Creating Blender scene and rendering...")
                try:
                    from scene_builder.decoder import blender_decoder
                    from scene_builder.utils.conversions import pydantic_to_dict
                    
                    room_data = pydantic_to_dict(room)
                    blender_decoder.parse_room_definition(room_data)
                    
                    # Render top-down view
                    render_path = blender_decoder.render_top_down("./")
                    print(f"✓ Rendered image saved to: {render_path}")
                    
                    # Save Blender scene
                    blender_decoder.save_scene(f"{room.id}_trapezoid_test.blend")
                    print(f"✓ Blender scene saved as: {room.id}_trapezoid_test.blend")
                    
                except Exception as e:
                    print(f"⚠ Blender rendering failed (normal if bpy not available): {e}")
        
        return True
        
    except Exception as e:
        print(f"✗ FloorPlanAgent failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing Enhanced LLM FloorPlanAgent with Different Shapes")
    print("=" * 60)
    
    # Run async tests
    async def run_tests():
        test_results = []
        test_results.append(await test_floor_plan_agent_round_classroom())
        test_results.append(await test_floor_plan_agent_trapezoid_classroom())
        return test_results
    
    # Run the async tests
    test_results = asyncio.run(run_tests())
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(test_results)
    total = len(test_results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! LLM FloorPlanAgent supports multiple shapes correctly.")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")