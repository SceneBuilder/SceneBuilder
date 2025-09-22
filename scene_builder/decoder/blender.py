import os
import tempfile
import math
from pathlib import Path
from typing import Any, Optional

import bpy
import numpy as np
import yaml
from scipy.spatial.transform import Rotation

from scene_builder.definition.scene import Object, Room, Scene
from scene_builder.importer import objaverse_importer, test_asset_importer
from scene_builder.logging import logger
from scene_builder.utils.conversions import pydantic_to_dict
from scene_builder.utils.file import get_filename


HDRI_FILE_PATH = Path(
    "~/GitHub/SceneBuilder-Test-Assets/hdri/autumn_field_puresky_4k.exr"
).expanduser()  # TEMP HACK


def parse_scene_definition(scene_data: dict[str, Any]):
    """
    Parses the scene definition dictionary and creates the scene in Blender.

    Args:
        scene_data: A dictionary representing the scene, loaded from the YAML file.
    """
    logger.debug("Parsing scene definition and creating scene in Blender...")

    if isinstance(scene_data, Scene):
        scene_data = pydantic_to_dict(scene_data)

    # Clear the existing scene
    _clear_scene()

    for room_data in scene_data.get("rooms", []):
        _create_room(room_data)


def parse_room_definition(room_data: dict[str, Any], clear=False):
    """
    Parses the room definition dictionary and creates the scene in Blender.

    Args:
        room_data: A dictionary representing the room, loaded from the YAML file.
        clear: Whether to clear the Blender scene before building room.

    # NOTE: not sure if it's good for `clear` to default to True; (it was for testing)
    """
    logger.debug("Parsing room definition and creating scene")

    if isinstance(room_data, Room):
        room_data = pydantic_to_dict(room_data)

    # Clear the existing scene
    if clear:
        _clear_scene()

    _create_room(room_data)


def _clear_scene():
    """Clears all objects from the current Blender scene."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    logger.debug("Cleared existing scene.")


def _create_room(room_data: dict[str, Any]):
    """Creates a representation of a room (for now, just its objects)."""
    logger.debug(f"Creating room: {room_data.get('id')}")
    for obj_data in room_data.get("objects", []):
        _create_object(obj_data)


def _create_object(obj_data: dict[str, Any], parent_location: str = "origin"):
    """
    Creates a single object in the Blender scene.
    Raises an IOError if the object cannot be imported.

    Args:
        obj_data: Dictionary containing object data
        parent_location: Strategy for placing the parent Empty object.
                        Options: "first_object", "median", "origin"
    """
    if isinstance(obj_data, Object):
        obj_data = pydantic_to_dict(obj_data)

    object_name = obj_data.get("name", "Unnamed Object")
    logger.debug(f"Creating object: {object_name}")

    blender_obj = None

    if obj_data.get("source") == "objaverse":
        source_id = obj_data.get("source_id")
        if not source_id:
            raise ValueError(
                f"Object '{object_name}' has source 'objaverse' but no 'source_id'."
            )

        # Import the object from Objaverse
        object_path = objaverse_importer.import_object(source_id)

    elif obj_data.get("source") == "test_asset":
        object_path = test_asset_importer.import_test_asset(obj_data.get("source_id"))

    elif obj_data.get("source") == "template":
        return

    else:
        # For other sources, we don't have an importer yet.
        # We can either raise an error or create a placeholder.
        # Raising an error is more explicit about what's happening.
        source = obj_data.get("source", "unknown")
        raise NotImplementedError(
            f"Object source '{source}' is not yet supported for '{object_name}'."
        )

    # Import the .glb file
    if object_path and object_path.endswith(".glb"):
        try:
            # Deselect all objects before import to ensure clean selection
            bpy.ops.object.select_all(action="DESELECT")

            # Import the GLTF file - imported objects will be selected
            bpy.ops.import_scene.gltf(filepath=object_path)

            # Get only top-level imported objects (no parents) to preserve hierarchy
            imported_objects = [
                obj for obj in bpy.context.selected_objects if obj.parent is None
            ]

            if not imported_objects:
                raise IOError(f"No objects were imported from '{object_path}'")

            # Create an Empty parent object to group all imported parts
            # Determine parent location based on strategy
            if parent_location == "first_object" and imported_objects:
                bpy.context.view_layer.objects.active = imported_objects[0]
                empty_location = imported_objects[0].location
            elif parent_location == "median" and imported_objects:
                # Calculate median position of all imported objects
                locations = [obj.location for obj in imported_objects]
                x_coords = sorted([loc.x for loc in locations])
                y_coords = sorted([loc.y for loc in locations])
                z_coords = sorted([loc.z for loc in locations])

                # Get median values
                n = len(locations)
                if n % 2 == 0:
                    median_x = (x_coords[n // 2 - 1] + x_coords[n // 2]) / 2
                    median_y = (y_coords[n // 2 - 1] + y_coords[n // 2]) / 2
                    median_z = (z_coords[n // 2 - 1] + z_coords[n // 2]) / 2
                else:
                    median_x = x_coords[n // 2]
                    median_y = y_coords[n // 2]
                    median_z = z_coords[n // 2]

                empty_location = (median_x, median_y, median_z)
            elif parent_location == "origin":
                empty_location = (0, 0, 0)
            else:
                # Fallback to origin if invalid option or no objects
                empty_location = (0, 0, 0)

            # Create Empty at the calculated location
            bpy.ops.object.empty_add(type="PLAIN_AXES", location=empty_location)
            blender_obj = bpy.context.active_object
            blender_obj.name = object_name

            # Parent all imported objects to the Empty
            for obj in imported_objects:
                obj.parent = blender_obj

        except Exception as e:
            raise IOError(
                f"Failed to import GLB file for '{object_name}' from '{object_path}'. Blender error: {e}"
            )
    else:
        raise IOError(
            f"Failed to import object '{object_name}' (source_id: {source_id}). "
            f"The file path was not found or was not a .glb file. Path: '{object_path}'"
        )

    # Set position, rotation, and scale from the object data
    pos = obj_data.get("position", {"x": 0, "y": 0, "z": 0})
    rot = obj_data.get("rotation", {"x": 0, "y": 0, "z": 0})
    # scl = obj_data.get("scale", {"x": 1, "y": 1, "z": 1})
    # NOTE: I think LLMs think scale to be a size (dimensions) attribute in meters,
    #       not the scaling factor (0-1.0 float). Probs bc they're not fed with dims.
    scl = {"x": 1, "y": 1, "z": 1}  # TEMP HACK

    blender_obj.location = (pos["x"], pos["y"], pos["z"])
    blender_obj.scale = (scl["x"], scl["y"], scl["z"])

    # Combine the original rotation with the rotation from the scene definition.
    original_rotation = Rotation.from_euler("xyz", blender_obj.rotation_euler)
    new_rotation = Rotation.from_euler("xyz", [rot["x"], rot["y"], rot["z"]])
    combined_rotation = new_rotation * original_rotation

    # Apply the combined rotation.
    blender_obj.rotation_euler = combined_rotation.as_euler("xyz")


def load_template(path: str, clear_scene: bool):
    """
    Loads a template .blend file.

    Args:
        path: The path to the .blend file.
        clear_scene: Whether to clear the current scene before loading.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Template file not found: {path}")

    if clear_scene:
        _clear_scene()

    bpy.ops.wm.open_mainfile(filepath=path)
    logger.debug(f"Loaded template from {path}")


def save_scene(filepath: str):
    """Saves the current Blender scene to a .blend file."""
    if not filepath.endswith(".blend"):
        filepath += ".blend"
    bpy.ops.wm.save_as_mainfile(filepath=filepath)
    logger.debug(f"Scene saved to {filepath}")


def _configure_output_image(format: str, resolution: int):
    format = format.upper()
    mapping = {"JPG": "JPEG"}
    if format in mapping.keys():
        format = mapping[format]

    bpy.context.scene.render.image_settings.file_format = format
    bpy.context.scene.render.resolution_x = resolution
    bpy.context.scene.render.resolution_y = resolution
    bpy.context.scene.render.resolution_percentage = 100


def _select_render_engine():
    """Selects a compatible render engine."""
    try:
        engine_prop = bpy.context.scene.render.bl_rna.properties["engine"]
        available_engines = [item.identifier for item in engine_prop.enum_items]
    except Exception:
        available_engines = []

    preferred_engines = ["BLENDER_EEVEE_NEXT", "EEVEE", "CYCLES", "BLENDER_WORKBENCH"]
    for candidate in preferred_engines:
        if candidate in available_engines:
            bpy.context.scene.render.engine = candidate
            break
    else:
        # Fallback to whatever is currently set if preferences are unavailable
        pass


def _setup_top_down_camera():
    """Sets up a top-down orthographic camera."""
    # Clear existing cameras
    for obj in bpy.context.scene.objects:
        if obj.type == "CAMERA":
            bpy.data.objects.remove(obj, do_unlink=True)

    # Add top-down orthographic camera
    bpy.ops.object.camera_add(location=(0, 0, 10))  # 10 units above origin
    camera = bpy.context.object
    camera.name = "TopDownCamera"

    # Set to orthographic projection
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 20.0  # Adjust based on room size

    # Point camera straight down (top-down view)
    camera.rotation_euler = (0, 0, 0)  # Looking straight down Z-axis

    # Set as active camera
    bpy.context.scene.camera = camera


def _setup_isometric_camera():
    """Sets up an isometric orthographic camera."""
    # Clear existing cameras
    for obj in bpy.context.scene.objects:
        if obj.type == "CAMERA":
            bpy.data.objects.remove(obj, do_unlink=True)

    # Add isometric orthographic camera
    bpy.ops.object.camera_add(location=(10, -10, 10))
    camera = bpy.context.object
    camera.name = "IsometricCamera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 20.0  # Adjust based on room size

    # Point camera towards the origin with isometric rotation
    camera.rotation_euler = (math.radians(54.736), 0, math.radians(45))

    # Set as active camera
    bpy.context.scene.camera = camera


def _setup_lighting(energy: float = 1.0):
    """Sets up basic lighting for the scene."""
    if not any(obj.type == "LIGHT" for obj in bpy.context.scene.objects):
        bpy.ops.object.light_add(type="SUN", location=(0, 0, 15))
        light = bpy.context.object
        light.data.energy = energy
        light.rotation_euler = (0, 0, 0)  # Light pointing down
        logger.debug("Added top-down lighting")


def render_to_file(output_path: str | Path) -> Path:
    """
    Renders the current scene to a file.

    Args:
        output_path: The path to save the rendered image to.

    Returns:
        The path to the rendered image.
    """
    if not isinstance(output_path, Path):
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Set render output path
    bpy.context.scene.render.filepath = str(output_path)

    # Render the scene
    logger.debug(f"Rendering scene to {output_path}")
    bpy.ops.render.render(write_still=True)

    if output_path.exists():
        logger.debug(f"Render completed: {output_path}")
        return output_path
    else:
        raise IOError(f"Render failed - output file not created: {output_path}")


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
    pixels = bpy.data.images["Render Result"].pixels[:]

    # Convert to NumPy array (RGBA format)
    image_array = np.array(pixels).reshape((height, width, 4))

    return image_array


def create_scene_visualization(
    resolution=1024, format="jpg", output_dir: str = None, view: str = "top_down"
) -> Path:
    """
    Creates a visualization of the current scene.

    Args:
        resolution: The resolution of the output image.
        format: The format of the output image.
        output_dir: The directory to save the output image to.
        view: The view to render from. Can be 'top_down' or 'isometric'.

    Returns:
        Path to the rendered scene visualization file.
    """
    logger.debug(f"Setting up {view} orthographic render...")

    _select_render_engine()
    _configure_output_image(format, resolution)
    if view == "top_down":
        _setup_top_down_camera()
    elif view == "isometric":
        _setup_isometric_camera()
    else:
        raise ValueError(
            f"Unsupported view type: {view}. Must be 'top_down' or 'isometric'."
        )
    _setup_lighting(energy=0.5)

    # Prepare output filepath
    if output_dir is None:
        output_dir = tempfile.gettempdir()

    output_path = get_filename(
        output_dir=output_dir,
        base_name=f"sb_scene_viz_{view}",
        extension=format.lower(),
        strategy="increment",
    )

    scene = bpy.context.scene
    setup_lighting_foundation(scene)
    setup_post_processing(scene)

    return render_to_file(output_path)


### Lighting
# TODO: Modularize lighting stuff into a file (i.e., turn blender decoder into a folder, not a single file)
def setup_lighting_foundation(
    scene: bpy.types.Scene,
    hdri_path: Optional[str | Path] = HDRI_FILE_PATH,
    hdri_strength: float = 1.0,
):
    """Sets up global illumination and world environment lighting."""
    print("Setting up foundation lighting...")
    scene.render.engine = "CYCLES"
    cycles_settings = scene.cycles

    # Configure GI bounces
    cycles_settings.max_bounces = 12
    cycles_settings.diffuse_bounces = 4
    cycles_settings.glossy_bounces = 4

    # Set up the world environment
    world = scene.world
    if not world:
        world = bpy.data.worlds.new("AutomatedWorld")
        scene.world = world

    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()

    # Create and link shader nodes
    bg_node = nt.nodes.new(type="ShaderNodeBackground")
    output_node = nt.nodes.new(type="ShaderNodeOutputWorld")
    bg_node.inputs["Strength"].default_value = hdri_strength

    if hdri_path and Path(hdri_path).exists():
        env_node = nt.nodes.new(type="ShaderNodeTexEnvironment")
        env_node.image = bpy.data.images.load(str(hdri_path))
        nt.links.new(env_node.outputs["Color"], bg_node.inputs["Color"])
    else:
        bg_node.inputs["Color"].default_value = (0.1, 0.1, 0.1, 1.0)

    nt.links.new(bg_node.outputs["Background"], output_node.inputs["Surface"])


# TODO: Implement this function to work with windows built by SceneBuilder.
# def add_motivated_lights(scene: bpy.types.Scene, sun_energy: float = 5.0):
#     """Adds key lights based on semantic information in the scene."""
#     print("Adding motivated lights...")
#     bpy.ops.object.light_add(type='SUN', location=(0, 0, 10))
#     sun = bpy.context.active_object
#     sun.data.energy = sun_energy
#     sun.data.angle = math.radians(0.53)

#     # --- Your Custom Logic Goes Here ---
#     # Example: Find windows and add portals
#     for obj in scene.objects:
#         if "window" in obj.name.lower():
#             print(f"Found window: {obj.name}. Adding light portal.")
#             bpy.ops.object.light_add(type='AREA', location=obj.location)
#             portal = bpy.context.active_object
#             portal.data.is_portal = True
#             portal.scale = (obj.dimensions.x, obj.dimensions.y, 1)


# def add_fill_lights():
#     """Adds subtle, non-shadow-casting lights to brighten dark areas."""
#     print("Adding fill lights...")
#     bpy.ops.object.light_add(type='POINT', location=(-3, -3, 1.5))
#     fill_light = bpy.context.active_object
#     fill_light.name = "FillLight"

#     fill_light.data.energy = 20.0
#     fill_light.data.shadow_soft_size = 3.0
#     fill_light.visible_shadow = False


def setup_post_processing(scene: bpy.types.Scene):
    """Configures color management and compositor nodes for the final look."""
    print("Setting up post-processing...")
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"

    scene.use_nodes = True
    nt = scene.node_tree
    nt.nodes.clear()

    render_layers = nt.nodes.new(type="CompositorNodeRLayers")
    composite_output = nt.nodes.new(type="CompositorNodeComposite")
    glare_node = nt.nodes.new(type="CompositorNodeGlare")

    glare_node.glare_type = "FOG_GLOW"
    glare_node.threshold = 1.5
    glare_node.size = 8

    nt.links.new(render_layers.outputs["Image"], glare_node.inputs["Image"])
    nt.links.new(glare_node.outputs["Image"], composite_output.inputs["Image"])
