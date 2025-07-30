import bpy
from typing import Dict, Any
from . import objaverse_importer

# This script uses the `bpy` module to create a Blender scene.
# It can be run with a standalone `bpy` installation (e.g., from pip)
# or within the Blender Python environment.


def parse_scene_definition(scene_data: Dict[str, Any]):
    """
    Parses the scene definition dictionary and creates the scene in Blender.

    Args:
        scene_data: A dictionary representing the scene, loaded from the Pkl file.
    """
    print("Parsing scene definition and creating scene in Blender...")

    # Clear the existing scene
    _clear_scene()

    for room_data in scene_data.get("rooms", []):
        _create_room(room_data)


def _clear_scene():
    """Clears all objects from the current Blender scene."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    print("Cleared existing scene.")


def _create_room(room_data: Dict[str, Any]):
    """Creates a representation of a room (for now, just its objects)."""
    print(f"Creating room: {room_data.get('id')}")
    for obj_data in room_data.get("objects", []):
        _create_object(obj_data)


def _create_object(obj_data: Dict[str, Any]):
    """
    Creates a single object in the Blender scene.

    For now, this creates a simple cube as a placeholder for the actual 3D model.
    """
    print(f"Creating object: {obj_data.get('name')}")

    if obj_data.get("source") == "objaverse":
        # Import the object from Objaverse
        object_path = objaverse_importer.import_object(obj_data.get("sourceId"))

        # Import the .glb file
        if object_path and object_path.endswith(".glb"):
            bpy.ops.import_scene.gltf(filepath=object_path)
            blender_obj = bpy.context.selected_objects[0]
            blender_obj.name = obj_data.get("name", "Unnamed Object")
        else:
            # Fallback to a placeholder cube if the import fails
            bpy.ops.mesh.primitive_cube_add()
            blender_obj = bpy.context.object
            blender_obj.name = obj_data.get("name", "Unnamed Object")
    else:
        # Create a placeholder cube
        bpy.ops.mesh.primitive_cube_add()
        blender_obj = bpy.context.object
        blender_obj.name = obj_data.get("name", "Unnamed Object")

    # Set position, rotation, and scale from the object data
    pos = obj_data.get("position", {"x": 0, "y": 0, "z": 0})
    rot = obj_data.get("rotation", {"x": 0, "y": 0, "z": 0})
    scl = obj_data.get("scale", {"x": 1, "y": 1, "z": 1})

    blender_obj.location = (pos["x"], pos["y"], pos["z"])
    blender_obj.rotation_euler = (rot["x"], rot["y"], rot["z"])
    blender_obj.scale = (scl["x"], scl["y"], scl["z"])


def save_scene(filepath: str):
    """Saves the current Blender scene to a .blend file."""
    if not filepath.endswith(".blend"):
        filepath += ".blend"
    bpy.ops.wm.save_as_mainfile(filepath=filepath)
    print(f"Scene saved to {filepath}")


if __name__ == "__main__":
    # This is an example of how you might use this script.
    # You would first need to load your scene definition into a dictionary.

    # Example mock scene data:
    mock_scene = {
        "category": "residential",
        "tags": ["modern"],
        "floorType": "single",
        "rooms": [
            {
                "id": "living_room_1",
                "category": "living_room",
                "tags": ["main"],
                "objects": [
                    {
                        "id": "objaverse-sofa-123",
                        "name": "Modern Red Sofa",
                        "source": "objaverse",
                        "sourceId": "objaverse-sofa-123",
                        "position": {"x": 0, "y": 0, "z": 0},
                        "rotation": {
                            "x": 0,
                            "y": 0,
                            "z": 1.57,
                        },  # 90 degrees rotation on Z
                        "scale": {"x": 2, "y": 1, "z": 1},
                    }
                ],
            }
        ],
    }

    parse_scene_definition(mock_scene)
    save_scene("output.blend")

    print("\nBlender scene created successfully from mock data.")
