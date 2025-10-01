import pytest
from pathlib import Path

from scene_builder.decoder import blender
from scene_builder.definition.scene import Vector2

def test_floor_mesh():
    boundary = [Vector2(x=4,y=2), Vector2(x=-4,y=2), Vector2(x=-4,y=-2), Vector2(x=4,y=-2)] 
    result = blender._create_floor_mesh(boundary, "test_room")
    print(result)

    blender.save_scene("test_room.blend")
    blender.create_scene_visualization(output_dir=".")

def test_bound_calculation():
    bounds = blender._calculate_bounds([])
    print(bounds)
    


if __name__ == "__main__":
    test_floor_mesh()
    test_bound_calculation()