from typing import Any
from pathlib import Path
import os
import tempfile
import numpy as np

import bpy
import yaml

from scene_builder.importer import objaverse_importer, test_asset_importer

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
            raise ValueError(f"Object '{object_name}' has source 'objaverse' but no 'sourceId'.")

        # Import the object from Objaverse
        object_path = objaverse_importer.import_object(source_id)

    elif obj_data.get("source") == "test_asset":
        object_path = test_asset_importer.import_test_asset(obj_data.get("id"))

    else:
        # For other sources, we don't have an importer yet.
        # We can either raise an error or create a placeholder.
        # Raising an error is more explicit about what's happening.
        source = obj_data.get('source', 'unknown')
        raise NotImplementedError(f"Object source '{source}' is not yet supported for '{object_name}'.")

    # Import the .glb file
    if object_path and object_path.endswith(".glb"):
        try:
            bpy.ops.import_scene.gltf(filepath=object_path)
            # The imported object is the newly selected one
            blender_obj = bpy.context.selected_objects[0]
            blender_obj.name = object_name
        except Exception as e:
            raise IOError(f"Failed to import GLB file for '{object_name}' from '{object_path}'. Blender error: {e}")
    else:
        raise IOError(
            f"Failed to import object '{object_name}' (sourceId: {source_id}). "
            f"The file path was not found or was not a .glb file. Path: '{object_path}'"
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


def render_top_down(output_dir: str = None) -> Path:
    """
    Brief Pipeline:
    1. Build the scene in Blender (bpy) 
    2. Set the camera to top-down + orthographic, then render
    3. Save the rendered image as a file (PNG) 
    4. Attach the generated top-down image to the Pydantic graph (viz field)
    
    Returns:
        Path to the rendered top-down PNG file.
    """
    print("Setting up top-down orthographic render...")

    # Select a compatible render engine (handles Blender versions where 'EEVEE' is renamed)
    try:
        engine_prop = bpy.context.scene.render.bl_rna.properties['engine']
        available_engines = [item.identifier for item in engine_prop.enum_items]
    except Exception:
        available_engines = []

    preferred_engines = ['BLENDER_EEVEE_NEXT', 'EEVEE', 'CYCLES', 'BLENDER_WORKBENCH']
    for candidate in preferred_engines:
        if candidate in available_engines:
            bpy.context.scene.render.engine = candidate
            break
    else:
        # Fallback to whatever is currently set if preferences are unavailable
        pass
    bpy.context.scene.render.image_settings.file_format = 'PNG'
    bpy.context.scene.render.resolution_x = 1024
    bpy.context.scene.render.resolution_y = 1024
    bpy.context.scene.render.resolution_percentage = 100
    
    # Clear existing cameras
    for obj in bpy.context.scene.objects:
        if obj.type == 'CAMERA':
            bpy.data.objects.remove(obj, do_unlink=True)
    
    # Add top-down orthographic camera
    bpy.ops.object.camera_add(location=(0, 0, 10))  # 10 units above origin
    camera = bpy.context.object
    camera.name = "TopDownCamera"
    
    # Set to orthographic projection
    camera.data.type = 'ORTHO'
    # camera.data.ortho_scale = 1.0  # Adjust based on room size
    # camera.data.ortho_scale = 5.0  # Adjust based on room size
    camera.data.ortho_scale = 20.0  # Adjust based on room size
    
    # Point camera straight down (top-down view)
    camera.rotation_euler = (0, 0, 0)  # Looking straight down Z-axis
    
    # Set as active camera
    bpy.context.scene.camera = camera
    
    # Add basic lighting for visibility
    if not any(obj.type == 'LIGHT' for obj in bpy.context.scene.objects):
        bpy.ops.object.light_add(type='SUN', location=(0, 0, 15))
        light = bpy.context.object
        # light.data.energy = 5.0
        light.data.energy = 0.5
        light.rotation_euler = (0, 0, 0)  # Light pointing down
        print("Added top-down lighting")
    
    # Prepare output filepath
    if output_dir is None:
        output_dir = tempfile.gettempdir()
    
    output_path = Path(output_dir) / f"room_topdown_{abs(hash(str(bpy.context.scene.objects)))}.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Set render output path
    bpy.context.scene.render.filepath = str(output_path)
    
    # Render the scene
    print(f"Rendering top-down view to {output_path}")
    bpy.ops.render.render(write_still=True)
    
    if output_path.exists():
        print(f"Top-down render completed: {output_path}")
        return output_path
    else:
        raise IOError(f"Top-down render failed - output file not created: {output_path}")


def render() -> np.ndarray:
    """
    Main render function for the workflow - renders scene to NumPy array.
    Sets up top-down orthographic view and renders directly to memory.
    
    Returns:
        NumPy array of rendered top-down image data (RGBA format).
    """
    print("Setting up top-down orthographic render...")

    # Select a compatible render engine (handles Blender versions where 'EEVEE' is renamed)
    try:
        engine_prop = bpy.context.scene.render.bl_rna.properties['engine']
        available_engines = [item.identifier for item in engine_prop.enum_items]
    except Exception:
        available_engines = []

    preferred_engines = ['BLENDER_EEVEE_NEXT', 'EEVEE', 'CYCLES', 'BLENDER_WORKBENCH']
    for candidate in preferred_engines:
        if candidate in available_engines:
            bpy.context.scene.render.engine = candidate
            break
    else:
        # Fallback to whatever is currently set if preferences are unavailable
        pass
    bpy.context.scene.render.image_settings.file_format = 'PNG'
    bpy.context.scene.render.resolution_x = 1024
    bpy.context.scene.render.resolution_y = 1024
    bpy.context.scene.render.resolution_percentage = 100
    
    # Clear existing cameras
    for obj in bpy.context.scene.objects:
        if obj.type == 'CAMERA':
            bpy.data.objects.remove(obj, do_unlink=True)
    
    # Add top-down orthographic camera
    bpy.ops.object.camera_add(location=(0, 0, 10))  # 10 units above origin
    camera = bpy.context.object
    camera.name = "TopDownCamera"
    
    # Set to orthographic projection
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 20.0  # Adjust based on room size
    
    # Point camera straight down (top-down view)
    camera.rotation_euler = (0, 0, 0)  # Looking straight down Z-axis
    
    # Set as active camera
    bpy.context.scene.camera = camera
    
    # Add basic lighting for visibility
    if not any(obj.type == 'LIGHT' for obj in bpy.context.scene.objects):
        bpy.ops.object.light_add(type='SUN', location=(0, 0, 15))
        light = bpy.context.object
        light.data.energy = 5.0
        light.rotation_euler = (0, 0, 0)  # Light pointing down
        print("Added top-down lighting")
    
    # Render to Blender's internal buffer
    print("Rendering top-down view to memory...")
    bpy.ops.render.render()
    
    # Get rendered image from Blender
    render_result = bpy.context.scene.render
    width = render_result.resolution_x
    height = render_result.resolution_y
    
    # Extract pixel data
    pixels = bpy.data.images['Render Result'].pixels[:]
    
    # Convert to NumPy array (RGBA format)
    image_array = np.array(pixels).reshape((height, width, 4))
    
    print(f"Render completed: {width}x{height} RGBA array")
    return image_array


def render_to_numpy() -> np.ndarray:
    """
    Alternative: Render directly to NumPy array in memory (no file).
    
    Returns:
        NumPy array of rendered image data.
    """
    # Render to Blender's internal buffer
    bpy.ops.render.render()
    
    # Get rendered image from Blender
    render_result = bpy.context.scene.render
    width = render_result.resolution_x
    height = render_result.resolution_y
    
    # Extract pixel data
    pixels = bpy.data.images['Render Result'].pixels[:]
    
    # Convert to NumPy array (RGBA format)
    image_array = np.array(pixels).reshape((height, width, 4))
    
    return image_array


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
