from typing import Any

import bpy
import yaml

from scene_builder.importer import objaverse_importer

# This script uses the `bpy` module to create a Blender scene.
# It can be run with a standalone `bpy` installation (e.g., from pip)
# or within the Blender Python environment.


def parse_scene_definition(scene_data: dict[str, Any]):
    """
    Parses the scene definition dictionary and creates the scene in Blender.

    Args:
        scene_data: A dictionary representing the scene, loaded from the YAML file.
    """
    print("Parsing scene definition and creating scene in Blender...")

    # Clear the existing scene
    _clear_scene()

    for room_data in scene_data.get("rooms", []):
        _create_room(room_data)


def parse_room_definition(room_data: dict[str, Any]):
    """
    Parses the room definition dictionary and creates the scene in Blender.

    Args:
        room_data: A dictionary representing the room, loaded from the YAML file.
    """
    print("Parsing room definition and creating scene in Blender...")

    # Clear the existing scene
    _clear_scene()

    _create_room(room_data)


def _clear_scene():
    """Clears all objects from the current Blender scene."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    print("Cleared existing scene.")


def _create_room(room_data: dict[str, Any]):
    """Creates a representation of a room (for now, just its objects)."""
    print(f"Creating room: {room_data.get('id')}")
    for obj_data in room_data.get("objects", []):
        _create_object(obj_data)


def _create_object(obj_data: dict[str, Any]):
    """
    Creates a single object in the Blender scene.
    Raises an IOError if the object cannot be imported.
    """
    object_name = obj_data.get("name", "Unnamed Object")
    print(f"Creating object: {object_name}")

    blender_obj = None

    if obj_data.get("source") == "objaverse":
        source_id = obj_data.get("sourceId")
        if not source_id:
            raise ValueError(
                f"Object '{object_name}' has source 'objaverse' but no 'sourceId'."
            )

        # Import the object from Objaverse
        object_path = objaverse_importer.import_object(source_id)

        # Import the .glb file
        if object_path and object_path.endswith(".glb"):
            try:
                bpy.ops.import_scene.gltf(filepath=object_path)
                # The imported object is the newly selected one
                blender_obj = bpy.context.selected_objects[0]
                blender_obj.name = object_name
            except Exception as e:
                raise IOError(
                    f"Failed to import GLB file for '{object_name}' from '{object_path}'. Blender error: {e}"
                )
        else:
            raise IOError(
                f"Failed to import object '{object_name}' (sourceId: {source_id}). "
                f"The file path was not found or was not a .glb file. Path: '{object_path}'"
            )
    else:
        # For other sources, we don't have an importer yet.
        # We can either raise an error or create a placeholder.
        # Raising an error is more explicit about what's happening.
        source = obj_data.get("source", "unknown")
        raise NotImplementedError(
            f"Object source '{source}' is not yet supported for '{object_name}'."
        )

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


def load_scene_from_yaml(filepath: str) -> dict[str, Any]:
    """
    Loads a scene definition from a YAML file.

    Args:
        filepath: The path to the YAML file.

    Returns:
        A dictionary representing the scene.
    """
    with open(filepath, "r") as f:
        return yaml.safe_load(f)


if __name__ == "__main__":
    # This is an example of how you might use this script.
    # You would first need to load your scene definition into a dictionary.

    # Example of loading from a YAML file:
    # Note: This will likely fail if the sourceIds in the yaml are not valid
    # or if the required importers are not available.
    try:
        scene_data = load_scene_from_yaml("scenes/generated_scene.yaml")
        parse_scene_definition(scene_data)
        save_scene("output.blend")
        print("\nBlender scene created successfully from YAML data.")
    except (IOError, NotImplementedError, ValueError, FileNotFoundError) as e:
        print(f"\n[ERROR] Could not create Blender scene: {e}")
