import pytest
from pathlib import Path
# from scene_builder.workflow.graph import VisualFeedback
# from scene_builder.workflow.state import PlacementState
# from scene_builder.definition.scene import Room, Object, Vector2, Vector3
# from scene_builder.definition.plan import RoomPlan
# from scene_builder.decoder import blender

from scene_builder.definition.scene import Vector2
from scene_builder.decoder import blender

def test_floor_mesh():
    boundary = [Vector2(x=4,y=2), Vector2(x=-4,y=2), Vector2(x=-4,y=-2), Vector2(x=4,y=-2)] 
    result = blender._create_floor_mesh(boundary, "test_room")
    print(result)

    blender.save_scene("test_room.blend")
    blender.render_top_down()

def test_bound_calculation():
    bounds = blender._calculate_bounds([])
    print(bounds)
    


if __name__ == "__main__":
    test_floor_mesh()
    test_bound_calculation()