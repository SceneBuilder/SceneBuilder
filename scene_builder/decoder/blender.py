import os
import tempfile
import math
import time
from pathlib import Path
from typing import Any, Optional

import bpy
import bmesh
import numpy as np
import yaml
from scipy.spatial.transform import Rotation
from mathutils.geometry import tessellate_polygon
from mathutils import Vector

from scene_builder.config import TEST_ASSET_DIR
from scene_builder.definition.scene import Object, Room, Scene
from scene_builder.importer import objaverse_importer, test_asset_importer
from scene_builder.logging import logger
from scene_builder.utils.conversions import pydantic_to_dict
from scene_builder.utils.file import get_filename


HDRI_FILE_PATH = Path(
    f"{TEST_ASSET_DIR}/hdri/autumn_field_puresky_4k.exr"
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
    """Creates a representation of a room including floor mesh, walls, and objects."""
    if room_data is None:
        logger.warning("room_data is None, skipping room creation")
        return

    room_id = room_data.get("id", "unknown_room")
    logger.debug(f"Creating room: {room_id}")

    # Create floor mesh if boundary data exists
    boundary = room_data.get("boundary")
    if boundary:
        logger.debug(f"Creating floor mesh for room: {room_id}")
        try:
            # Extract LLM metadata if available
            llm_metadata = {}
            if "floor_dimensions" in room_data:
                floor_dims = room_data["floor_dimensions"]
                llm_metadata = {
                    "width": floor_dims.get("width", 0),
                    "height": floor_dims.get("height", 0),
                    "area_sqm": floor_dims.get("area_sqm", 0),
                    "shape": floor_dims.get("shape", "unknown"),
                    "confidence": floor_dims.get("confidence", 0),
                    "llm_analysis": floor_dims.get("llm_analysis", ""),
                }

            floor_result = _create_floor_mesh(
                boundary, room_id, llm_metadata=llm_metadata
            )
            logger.debug(f"Floor mesh created: {floor_result.get('status', 'unknown')}")
        except Exception as e:
            logger.error(f"Failed to create floor mesh for room {room_id}: {e}")

    # Create walls from boundary if ceiling height is available
    if boundary and room_data.get("floor_dimensions"):
        floor_dims = room_data["floor_dimensions"]
        ceiling_height = floor_dims.get(
            "ceiling_height", 2.7
        )  # Default to 2.7m if not specified

        logger.debug(f"Creating walls for room: {room_id} (height: {ceiling_height}m)")
        try:
            wall_result = _create_walls_from_boundary(boundary, room_id, ceiling_height)
            logger.debug(f"Walls created: {wall_result.get('status', 'unknown')}")
        except Exception as e:
            logger.error(f"Failed to create walls for room {room_id}: {e}")

    # Create objects in the room
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


def _create_floor_mesh(
    boundary: list[dict[str, float]],
    room_id: str,
    floor_thickness_m: float = 0.1,
    origin: str = "center",
    llm_metadata: dict[str, Any] = None,
) -> dict[str, Any]:
    """
    Creates a watertight floor mesh from room boundary points with LLM metadata integration.

    Args:
        boundary: List of Vector2 points from room.boundary [{"x": float, "y": float}, ...]
        room_id: Room identifier for naming
        floor_thickness_m: Thickness of the floor in meters (default: 0.1)
        origin: Origin placement - "center" or "min" (default: "center")
        llm_metadata: LLM analysis data from floor_dimensions

    Returns:
        Dictionary with creation status and metadata
    """

    if not boundary or len(boundary) < 3:
        return {
            "status": "error",
            "message": f"Room {room_id}: At least 3 boundary points required for floor mesh",
            "timestamp": int(time.time()),
        }

    # Generate timestamp for deterministic naming
    timestamp = int(time.time())
    floor_name = f"Floor_{room_id}_{timestamp}"
    mesh_name = f"FloorMesh_{room_id}_{timestamp}"

    # Ensure NavGo_Floors collection exists
    collection = _ensure_collection("NavGo_Floors")

    # Create new mesh and object
    mesh = bpy.data.meshes.new(mesh_name)
    floor_obj = bpy.data.objects.new(floor_name, mesh)

    # Link to collection
    collection.objects.link(floor_obj)

    # Create bmesh instance
    bm = bmesh.new()

    try:
        # Convert boundary points to 3D vertices (z=0 for top face)
        # Handle both Vector2 objects and dictionaries
        vertices_2d = []
        for point in boundary:
            if hasattr(point, "x"):  # Vector2 object
                vertices_2d.append((point.x, point.y))
            else:  # Dictionary format
                vertices_2d.append((point["x"], point["y"]))
        verts_3d = [(x, y, 0.0) for x, y in vertices_2d]

        # Create vertices in bmesh
        bmesh_verts = []
        for vert in verts_3d:
            bmesh_verts.append(bm.verts.new(vert))

        # Ensure face indices are valid
        bm.verts.ensure_lookup_table()

        # Create the top face using all vertices
        try:
            top_face = bm.faces.new(bmesh_verts)
            top_face.normal_update()
        except ValueError as e:
            # If direct face creation fails, try triangulation
            logger.debug(
                f"Direct face creation failed: {e}. Attempting triangulation..."
            )

            # Convert to mathutils Vectors for tessellation
            vectors = [Vector(v) for v in verts_3d]

            # Tessellate the polygon
            try:
                tessellated = tessellate_polygon([vectors])

                # Create faces from tessellation
                for tri in tessellated:
                    try:
                        face_verts = [bmesh_verts[i] for i in tri]
                        bm.faces.new(face_verts)
                    except (ValueError, IndexError):
                        continue

            except Exception as tess_error:
                logger.debug(f"Tessellation failed: {tess_error}")
                # Fallback: create a simple triangular fan
                for i in range(1, len(bmesh_verts) - 1):
                    try:
                        face_verts = [
                            bmesh_verts[0],
                            bmesh_verts[i],
                            bmesh_verts[i + 1],
                        ]
                        bm.faces.new(face_verts)
                    except ValueError as ve:
                        logger.debug(f"Failed to create fallback triangle face: {ve}")
                        continue

        # Create bottom face and side walls if thickness > 0
        if floor_thickness_m > 0:
            # Duplicate vertices for bottom face
            bottom_verts = []
            for x, y, _ in verts_3d:
                bottom_verts.append(bm.verts.new((x, y, -floor_thickness_m)))

            bm.verts.ensure_lookup_table()

            # Create bottom face (reversed order for correct normal)
            try:
                bottom_face = bm.faces.new(reversed(bottom_verts))
                bottom_face.normal_update()
            except ValueError:
                # Fallback triangulation for bottom face
                for i in range(1, len(bottom_verts) - 1):
                    face_verts = [bottom_verts[0], bottom_verts[i + 1], bottom_verts[i]]
                    bm.faces.new(face_verts)

            # Create side walls
            num_verts = len(bmesh_verts)
            for i in range(num_verts):
                next_i = (i + 1) % num_verts
                # Create quad face for each side
                side_face = bm.faces.new(
                    [
                        bmesh_verts[i],
                        bmesh_verts[next_i],
                        bottom_verts[next_i],
                        bottom_verts[i],
                    ]
                )
                side_face.normal_update()

        # Recalculate normals
        bm.faces.ensure_lookup_table()
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

        # Update mesh
        bm.to_mesh(mesh)
        mesh.update()

        # Generate UV coordinates for texturing
        bpy.context.view_layer.objects.active = floor_obj
        bpy.ops.object.select_all(action="DESELECT")
        floor_obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.001)
        bpy.ops.object.mode_set(mode="OBJECT")
        logger.debug(f"Generated UV coordinates for floor: {floor_name}")

    finally:
        bm.free()

    # Set object origin
    bpy.context.view_layer.objects.active = floor_obj
    bpy.ops.object.select_all(action="DESELECT")
    floor_obj.select_set(True)

    if origin == "center":
        bpy.ops.object.origin_set(type="ORIGIN_CENTER_OF_MASS", center="BOUNDS")
    elif origin == "min":
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")

    # Calculate bounds
    bounds = _calculate_bounds(vertices_2d)

    # Build result with LLM metadata
    result = {
        "status": "success",
        "object_name": floor_name,
        "mesh_name": mesh_name,
        "collection": "NavGo_Floors",
        "room_id": room_id,
        "vertex_count": len(vertices_2d),
        "face_count": len(mesh.polygons),
        "thickness_m": floor_thickness_m,
        "origin_mode": origin,
        "bounds": bounds,
        "timestamp": timestamp,
    }

    # Add LLM metadata to result
    if llm_metadata:
        result["llm_metadata"] = llm_metadata
        if llm_metadata.get("llm_analysis"):
            result["llm_analysis"] = llm_metadata["llm_analysis"]

    return result


def _create_walls_from_boundary(
    boundary: list[dict[str, float]],
    room_id: str,
    ceiling_height: float = 2.7,
    wall_thickness: float = 0.2,
) -> dict[str, Any]:
    """
    Creates wall meshes from room boundary points.

    Args:
        boundary: List of Vector2 points from room.boundary [{"x": float, "y": float}, ...]
        room_id: Room identifier for naming
        ceiling_height: Height of walls in meters (default: 2.7)
        wall_thickness: Thickness of walls in meters (default: 0.2)

    Returns:
        Dictionary with creation status and metadata
    """

    if not boundary or len(boundary) < 3:
        return {
            "status": "error",
            "message": f"Room {room_id}: At least 3 boundary points required for wall creation",
            "timestamp": int(time.time()),
        }

    try:
        # Generate timestamp for naming
        timestamp = int(time.time())

        # Ensure NavGo_Walls collection exists
        collection = _ensure_collection("NavGo_Walls")

        # Convert boundary points to 2D coordinates
        vertices_2d = []
        for point in boundary:
            if hasattr(point, "x"):  # Vector2 object
                vertices_2d.append((point.x, point.y))
            else:  # Dictionary format
                vertices_2d.append((point["x"], point["y"]))

        walls_created = 0

        # Create walls between consecutive boundary points
        num_points = len(vertices_2d)
        for i in range(num_points):
            next_i = (i + 1) % num_points

            # Get current and next point
            p1 = vertices_2d[i]
            p2 = vertices_2d[next_i]

            # Create wall segment
            wall_name = f"Wall_{room_id}_{i}_{timestamp}"
            mesh_name = f"WallMesh_{room_id}_{i}_{timestamp}"

            # Calculate wall direction and normal for thickness
            wall_dir_x = p2[0] - p1[0]
            wall_dir_y = p2[1] - p1[1]
            wall_length = (wall_dir_x**2 + wall_dir_y**2) ** 0.5

            if wall_length < 0.01:  # Skip very short walls
                continue

            # Normalize direction vector
            wall_dir_x /= wall_length
            wall_dir_y /= wall_length

            # Calculate perpendicular vector for wall thickness (inward normal only)
            # Boundary points are the outer edge, walls extend inward
            inward_normal_x = -wall_dir_y * wall_thickness
            inward_normal_y = wall_dir_x * wall_thickness

            # Create wall vertices (rectangular wall segment)
            wall_verts = [
                # Bottom face - outer edge stays at boundary, inner edge moves inward
                (p1[0], p1[1], 0.0),  # Bottom left outer (at boundary)
                (p2[0], p2[1], 0.0),  # Bottom right outer (at boundary)
                (
                    p2[0] + inward_normal_x,
                    p2[1] + inward_normal_y,
                    0.0,
                ),  # Bottom right inner
                (
                    p1[0] + inward_normal_x,
                    p1[1] + inward_normal_y,
                    0.0,
                ),  # Bottom left inner
                # Top face
                (p1[0], p1[1], ceiling_height),  # Top left outer (at boundary)
                (p2[0], p2[1], ceiling_height),  # Top right outer (at boundary)
                (
                    p2[0] + inward_normal_x,
                    p2[1] + inward_normal_y,
                    ceiling_height,
                ),  # Top right inner
                (
                    p1[0] + inward_normal_x,
                    p1[1] + inward_normal_y,
                    ceiling_height,
                ),  # Top left inner
            ]

            # Define faces for the wall (quads)
            wall_faces = [
                # Outer face
                (0, 1, 5, 4),
                # Inner face
                (3, 7, 6, 2),
                # End faces
                (0, 4, 7, 3),  # Left end
                (1, 2, 6, 5),  # Right end
                # Top face
                (4, 5, 6, 7),
                # Bottom face (optional, usually covered by floor)
                (0, 3, 2, 1),
            ]

            # Create mesh
            mesh = bpy.data.meshes.new(mesh_name)
            mesh.from_pydata(wall_verts, [], wall_faces)
            mesh.update()

            # Create object
            wall_obj = bpy.data.objects.new(wall_name, mesh)
            collection.objects.link(wall_obj)

            walls_created += 1

        return {
            "status": "success",
            "room_id": room_id,
            "walls_created": walls_created,
            "collection": "NavGo_Walls",
            "ceiling_height": ceiling_height,
            "wall_thickness": wall_thickness,
            "timestamp": timestamp,
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Wall creation failed for room {room_id}: {str(e)}",
            "timestamp": int(time.time()),
        }


def _calculate_bounds(
    vertices_2d: list[tuple[float, float]],
) -> dict[str, float | bool | int]:
    """
    Calculate bounding box dimensions from 2D vertices.

    Args:
        vertices_2d: List of (x, y) coordinate tuples

    Returns:
        Dictionary containing min/max coordinates, width, height, and area
    """

    if not vertices_2d:
        return {
            "value": False,
            "count": 0,
            "min_x": 0,
            "max_x": 0,
            "min_y": 0,
            "max_y": 0,
            "width": 0,
            "height": 0,
            "area": 0,
            "has_area": False,
        }

    x_coords = [x for x, y in vertices_2d]
    y_coords = [y for x, y in vertices_2d]

    min_x, max_x = min(x_coords), max(x_coords)
    min_y, max_y = min(y_coords), max(y_coords)
    width = max_x - min_x
    height = max_y - min_y
    area = width * height

    return {
        "value": True,
        "count": len(vertices_2d),
        "min_x": min_x,
        "max_x": max_x,
        "min_y": min_y,
        "max_y": max_y,
        "width": width,
        "height": height,
        "area": area,
        "has_area": (width > 0 and height > 0),
    }


def _ensure_collection(collection_name: str):
    """Ensures a collection exists and returns it."""
    if collection_name in bpy.data.collections:
        return bpy.data.collections[collection_name]

    # Create new collection
    collection = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(collection)
    return collection


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

    # Pack all external images into the .blend file
    try:
        bpy.ops.file.pack_all()
        logger.debug("✅ Packed all external images into .blend file")
    except Exception as e:
        logger.debug(f"⚠️  Warning: Could not pack images: {e}")

    # Ensure viewport is set to Material Preview before saving
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.type = "MATERIAL"
                    break

    bpy.ops.wm.save_as_mainfile(filepath=filepath)
    logger.debug(f"Scene saved to {filepath}")


def render_top_down(output_dir: str = None) -> Path:
    """
    Brief Pipeline:
    1. Build the scene in Blender (bpy)
    2. Set the camera to top-down + orthographic, then render
    3. Save the rendered image as a file (PNG)

    Returns:
        Path to the rendered top-down PNG file.
    """
    logger.debug("Setting up top-down orthographic render...")

    # Use existing modular functions instead of duplicating code
    _configure_render_settings()
    _configure_output_image("PNG", 1024)
    _setup_top_down_camera()
    _setup_lighting(energy=0.5)

    # Prepare output filepath
    if output_dir is None:
        output_dir = tempfile.gettempdir()

    output_path = (
        Path(output_dir)
        / f"room_topdown_{abs(hash(str(bpy.context.scene.objects)))}.png"
    )

    return render_to_file(output_path)


def render() -> np.ndarray:
    """
    Main render function for the workflow - renders scene to NumPy array.
    Sets up top-down orthographic view and renders directly to memory.

    Returns:
        NumPy array of rendered top-down image data (RGBA format).
    """
    logger.debug("Setting up top-down orthographic render...")

    _configure_render_settings()
    _configure_output_image("PNG", 1024)
    _setup_top_down_camera()
    _setup_lighting(energy=5.0)

    logger.debug("Rendering top-down view to memory...")
    bpy.ops.render.render()

    render_result = bpy.context.scene.render
    width = render_result.resolution_x
    height = render_result.resolution_y

    pixels = bpy.data.images["Render Result"].pixels[:]

    image_array = np.array(pixels).reshape((height, width, 4))

    logger.debug(f"Render completed: {width}x{height} RGBA array")
    return image_array


def _configure_output_image(format: str, resolution: int):
    format = format.upper()
    mapping = {"JPG": "JPEG"}
    if format in mapping.keys():
        format = mapping[format]

    bpy.context.scene.render.image_settings.file_format = format
    bpy.context.scene.render.resolution_x = resolution
    bpy.context.scene.render.resolution_y = resolution
    bpy.context.scene.render.resolution_percentage = 100


def _configure_render_settings(engine: str = None, samples: int = 256, enable_gpu: bool = True):
    """Selects a compatible render engine and configures render settings."""
    try:
        engine_prop = bpy.context.scene.render.bl_rna.properties["engine"]
        available_engines = [item.identifier for item in engine_prop.enum_items]
    except Exception:
        available_engines = []

    # Use specified engine if provided and available
    if engine and engine in available_engines:
        bpy.context.scene.render.engine = engine
    else:
        # Fallback to preferred engines
        preferred_engines = ["BLENDER_EEVEE_NEXT", "EEVEE", "CYCLES", "BLENDER_WORKBENCH"]
        for candidate in preferred_engines:
            if candidate in available_engines:
                bpy.context.scene.render.engine = candidate
                break
        else:
            # Fallback to whatever is currently set if preferences are unavailable
            pass

    # Configure samples based on selected engine
    if samples is not None:
        if bpy.context.scene.render.engine == 'CYCLES':
            bpy.context.scene.cycles.samples = samples
        elif bpy.context.scene.render.engine in ['BLENDER_EEVEE_NEXT', 'EEVEE']:
            bpy.context.scene.eevee.taa_render_samples = samples

    # Enable GPU rendering for Cycles if requested
    if enable_gpu and bpy.context.scene.render.engine == 'CYCLES':
        try:
            prefs = bpy.context.preferences.addons['cycles'].preferences
            prefs.compute_device_type = 'CUDA'  # Try CUDA first
            bpy.context.scene.cycles.device = 'GPU'
        except Exception:
            # Fallback if CUDA not available or addon not found
            try:
                prefs = bpy.context.preferences.addons['cycles'].preferences
                prefs.compute_device_type = 'OPENCL'
                bpy.context.scene.cycles.device = 'GPU'
            except Exception:
                # GPU acceleration not available, continue with CPU
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

    _configure_render_settings()
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
