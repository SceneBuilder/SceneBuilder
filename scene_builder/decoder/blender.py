import os
import tempfile
import math
import sys
from contextlib import contextmanager
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Optional, Dict, Tuple

import bpy
import bmesh
import numpy as np
import yaml
from scipy.spatial.transform import Rotation
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

from scene_builder.config import BLENDER_LOG_FILE, TEST_ASSET_DIR
from scene_builder.database.material import MaterialDatabase
from scene_builder.definition.scene import Object, Room, Scene
from scene_builder.importer import objaverse_importer, test_asset_importer
from scene_builder.logging import logger
from scene_builder.tools.material_applicator import texture_floor_mesh
from scene_builder.utils.blender import SceneSwitcher
from scene_builder.utils.conversions import pydantic_to_dict
from scene_builder.utils.file import get_filename


HDRI_FILE_PATH = Path(
    f"{TEST_ASSET_DIR}/hdri/autumn_field_puresky_4k.exr"
).expanduser()  # TEMP HACK

BACKGROUND_COLOR = (0.02, 0.02, 0.02, 1.0)


@dataclass
class BlenderObjectState:
    """Tracks state of objects created in Blender."""
    blender_name: str
    object_id: str
    source_id: str
    position: Tuple[float, float, float]
    rotation: Tuple[float, float, float]
    scale: Tuple[float, float, float]


class BlenderSceneTracker:
    """Tracks created objects by ID with readable position/rotation data."""

    def __init__(self):
        # Key: object_id, Value: BlenderObjectState
        self._objects: Dict[str, BlenderObjectState] = {}
        # Cache: Key: source_id, Value: blender_name of the Empty parent
        self._source_cache: Dict[str, str] = {}

    def object_exists_unchanged(self, object_id: str, pos: dict, rot: dict) -> bool:
        """Check if object exists with exact same position/rotation."""
        if object_id not in self._objects:
            return False

        existing = self._objects[object_id]
        pos_tuple = (pos["x"], pos["y"], pos["z"])
        rot_tuple = (rot["x"], rot["y"], rot["z"])

        return (existing.position == pos_tuple and
                existing.rotation == rot_tuple)

    def object_exists_but_moved(self, object_id: str, pos: dict, rot: dict) -> bool:
        """Check if object exists but has moved to different position/rotation."""
        if object_id not in self._objects:
            return False

        # If it exists but positions/rotations don't match, it moved
        return not self.object_exists_unchanged(object_id, pos, rot)

    def register_object(self, obj_data: dict, blender_name: str):
        """Register a newly created object (overwrites if object moved)."""
        object_id = obj_data["id"]
        source_id = obj_data["source_id"]
        pos = obj_data["position"]
        rot = obj_data["rotation"]
        scale = obj_data["scale"]

        self._objects[object_id] = BlenderObjectState(
            blender_name=blender_name,
            object_id=object_id,
            source_id=source_id,
            position=(pos["x"], pos["y"], pos["z"]),
            rotation=(rot["x"], rot["y"], rot["z"]),
            scale=(scale["x"], scale["y"], scale["z"])
        )

    def clear_all(self):
        """Clear all tracked objects."""
        self._objects.clear()
        self._source_cache.clear()
        logger.debug("Cleared all object tracking")

    def get_object_count(self) -> int:
        """Get total count of tracked objects."""
        return len(self._objects)

    def get_object_state(self, object_id: str) -> Optional[BlenderObjectState]:
        """Get current state for a specific object."""
        return self._objects.get(object_id)

    def get_cached_empty(self, source_id: str) -> Optional[Any]:
        """Get cached Empty parent object for a source_id if it exists.

        Args:
            source_id: The source_id to look up in cache

        Returns:
            Blender Empty object if found in cache and still exists, None otherwise
        """
        if source_id not in self._source_cache:
            return None

        blender_name = self._source_cache[source_id]

        # Verify the object still exists in Blender
        if blender_name in bpy.data.objects:
            return bpy.data.objects[blender_name]
        else:
            # Object was deleted, clean up cache
            del self._source_cache[source_id]
            return None

    def register_source_cache(self, source_id: str, blender_name: str):
        """Register a source_id -> Empty parent mapping in cache.

        Args:
            source_id: The source identifier (e.g., Objaverse ID)
            blender_name: The name of the Empty parent object in Blender
        """
        self._source_cache[source_id] = blender_name
        logger.debug(f"Cached source_id '{source_id}' -> Empty '{blender_name}'")


# Global scene tracker instance
_scene_tracker = BlenderSceneTracker()



@contextmanager
def suppress_blender_logs(log_file_path: str = BLENDER_LOG_FILE):
    """A context manager that redirects stdout and stderr to a file or devnull.

    This is used to suppress verbose console output from Blender operations
    that cannot be controlled through Python's logging module.

    Args:
        log_file_path: If provided, logs are written to this file.
                      If None, logs are discarded to devnull.
    """
    # Save the original stdout and stderr file descriptors
    original_stdout_fd = sys.stdout.fileno()
    original_stderr_fd = sys.stderr.fileno()

    # Create duplicates of the original file descriptors
    saved_stdout_fd = os.dup(original_stdout_fd)
    saved_stderr_fd = os.dup(original_stderr_fd)

    # Open log file or devnull depending on parameter
    if log_file_path:
        target_fd = os.open(log_file_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    else:
        target_fd = os.open(os.devnull, os.O_WRONLY)

    try:
        # Redirect stdout and stderr to the target
        os.dup2(target_fd, original_stdout_fd)
        os.dup2(target_fd, original_stderr_fd)

        # Yield control back to the 'with' block
        yield
    finally:
        # Restore the original stdout and stderr
        os.dup2(saved_stdout_fd, original_stdout_fd)
        os.dup2(saved_stderr_fd, original_stderr_fd)

        # Close the file descriptors we opened
        os.close(target_fd)
        os.close(saved_stdout_fd)
        os.close(saved_stderr_fd)


def parse_scene_definition(scene_data: dict[str, Any]):
    """
    Parses the scene definition dictionary and creates the scene in Blender.

    Args:
        scene_data: A dictionary representing the scene, loaded from the YAML file.
    """
    logger.debug("Parsing scene definition and creating scene in Blender...")

    if isinstance(scene_data, Scene):
        scene_data = pydantic_to_dict(scene_data)

    with suppress_blender_logs():
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
    # NOTE: I think there's a bug where if `clear=True`, not all assets are recreated at next iteration's `parse_room_definition()` call. this happens after critique's rejection. look into it!
    """
    if isinstance(room_data, Room):
        room_data = pydantic_to_dict(room_data)

    logger.debug(f"Parsing room definition for {room_data['id']} and creating scene")

    with suppress_blender_logs():
        with SceneSwitcher(room_data["id"]) as active_scene:
            # Clear the existing scene
            if clear:
                _clear_scene()

            _create_room(room_data)


def _clear_scene():
    """Clears all objects from the current Blender scene."""
    with suppress_blender_logs():
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()

    # Clear object tracking as well
    _scene_tracker.clear_all()

    logger.debug("Cleared existing scene.")


def _create_room(room_data: dict[str, Any]):
    """Creates a representation of a room including floor mesh, walls, and objects."""
    if room_data is None:
        logger.warning("room_data is None, skipping room creation")
        return

    room_id = room_data.get("id", "unknown_room")
    logger.debug(f"Creating room: {room_id}")

    # Create floor mesh
    floor_result = _create_floor_mesh(room_data["boundary"], room_id)
    logger.debug(f"Created floor: {floor_result['status']}")

    # Apply floor material
    if room_data["floor"]:
        material_id = room_data["floor"]["material_id"]
        apply_floor_material(
            material_id=material_id,
            floor_object_name=floor_result["object_name"],
            boundary=room_data["boundary"]
        )
        logger.debug(f"Applied material {material_id} to floor")

    # Create walls from boundary if ceiling height is available
    # if boundary and room_data.get("floor_dimensions"):
    #     floor_dims = room_data["floor_dimensions"]
    #     ceiling_height = floor_dims.get(
    #         "ceiling_height", 2.7
    #     )  # Default to 2.7m if not specified

    #     logger.debug(f"Creating walls for room: {room_id} (height: {ceiling_height}m)")
    #     try:
    #         wall_result = _create_walls_from_boundary(boundary, room_id, ceiling_height)
    #         logger.debug(f"Walls created: {wall_result.get('status', 'unknown')}")
    #     except Exception as e:
    #         logger.error(f"Failed to create walls for room {room_id}: {e}")

    # Create objects in the room
    for obj_data in room_data.get("objects", []):
        _create_object(obj_data)

def _check_object_duplicate_status(obj_data: dict[str, Any]) -> str:
    """
    Check if object already exists and determine what action to take.

    Args:
        obj_data: Dictionary containing object data

    Returns:
        String indicating status: "skip_unchanged", "recreate_moved", or "proceed_new"
    """
    object_id = obj_data.get("id")
    object_name = obj_data.get("name", "Unnamed Object")
    pos = obj_data.get("position", {"x": 0, "y": 0, "z": 0})
    rot = obj_data.get("rotation", {"x": 0, "y": 0, "z": 0})

    if not object_id:
        return "proceed_new"

    if _scene_tracker.object_exists_unchanged(object_id, pos, rot):
        logger.debug(f"Skipping duplicate object: {object_name} (id: {object_id}) - unchanged at {pos}")
        return "skip_unchanged"

    if _scene_tracker.object_exists_but_moved(object_id, pos, rot):
        logger.debug(f"Object {object_name} (id: {object_id}) has moved - will recreate at {pos}")
        return "recreate_moved"

    return "proceed_new"

def _check_object_duplicate_status(obj_data: dict[str, Any]) -> str:
    """
    Check if object already exists and determine what action to take.

    Args:
        obj_data: Dictionary containing object data

    Returns:
        String indicating status: "skip_unchanged", "recreate_moved", or "proceed_new"
    """
    object_id = obj_data.get("id")
    object_name = obj_data.get("name", "Unnamed Object")
    pos = obj_data.get("position", {"x": 0, "y": 0, "z": 0})
    rot = obj_data.get("rotation", {"x": 0, "y": 0, "z": 0})

    if not object_id:
        return "proceed_new"

    if _scene_tracker.object_exists_unchanged(object_id, pos, rot):
        logger.debug(f"Skipping duplicate object: {object_name} (id: {object_id}) - unchanged at {pos}")
        return "skip_unchanged"

    if _scene_tracker.object_exists_but_moved(object_id, pos, rot):
        logger.debug(f"Object {object_name} (id: {object_id}) has moved - will recreate at {pos}")
        return "recreate_moved"

    return "proceed_new"


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

    # Load data from object
    object_name = obj_data.get("name", "Unnamed Object")
    object_id = obj_data["id"]
    pos = obj_data.get("position", {"x": 0, "y": 0, "z": 0})
    rot = obj_data.get("rotation", {"x": 0, "y": 0, "z": 0})
    # scl = obj_data.get("scale", {"x": 1, "y": 1, "z": 1})
    # NOTE: I think LLMs think scale to be a size (dimensions) attribute in meters,
    #       not the scaling factor (0-1.0 float). Probs bc they're not fed with dims.
    scl = {"x": 1, "y": 1, "z": 1}  # TEMP HACK

    # Check for duplicates and determine action
    status = _check_object_duplicate_status(obj_data)
    if status == "skip_unchanged":
        return
    # TODO: Handle "recreate_moved" case if needed (remove old Blender object)

    logger.debug(f"Creating object: {object_name} (id: {object_id})")

    blender_obj = None
    source_id = obj_data.get("source_id")

    # Check if we've already imported this source_id
    if source_id:
        cached_empty = _scene_tracker.get_cached_empty(source_id)
        if cached_empty:
            logger.debug(f"Reusing cached model for source_id: {source_id}")

            # Create new Empty parent with linked duplicate children
            with suppress_blender_logs():
                bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
            blender_obj = bpy.context.active_object
            blender_obj.name = object_name

            # Create linked duplicates of all children
            for child in cached_empty.children:
                new_child = child.copy()
                new_child.data = child.data  # Share mesh data (linked duplicate)
                bpy.context.collection.objects.link(new_child)
                new_child.parent = blender_obj

            # Skip to transformation section
            # (Set position, rotation, and scale)
            blender_obj.location = (pos["x"], pos["y"], pos["z"])
            blender_obj.scale = (scl["x"], scl["y"], scl["z"])

            # Combine the original rotation with the rotation from the scene definition.
            original_rotation = Rotation.from_euler("xyz", blender_obj.rotation_euler)
            new_rotation = Rotation.from_euler("xyz", [rot["x"], rot["y"], rot["z"]], degrees=True)
            combined_rotation = new_rotation * original_rotation

            # Apply the combined rotation.
            blender_obj.rotation_euler = combined_rotation.as_euler("xyz")

            # Register the created object in tracker
            if object_id and blender_obj:
                _scene_tracker.register_object(obj_data, blender_obj.name)
                logger.debug(f"Registered object in tracker: {object_name} (id: {object_id})")

            return

    if obj_data.get("source").lower() == "objaverse":
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
        logger.warning(f"Unknown object source: {source}. For now, overwriting with objaverse.")
        source = "objaverse"  # TEMP HACK
        # raise NotImplementedError(
        #     f"Object source '{source}' is not yet supported for '{object_name}'."
        # )

    # Import the .glb file
    if object_path and object_path.endswith(".glb"):
        try:
            # Deselect all objects before import to ensure clean selection
            with suppress_blender_logs():
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
            with suppress_blender_logs():
                bpy.ops.object.empty_add(type="PLAIN_AXES", location=empty_location)
            blender_obj = bpy.context.active_object
            blender_obj.name = object_name

            # Parent all imported objects to the Empty
            for obj in imported_objects:
                obj.parent = blender_obj

            # Register this Empty in the source cache for future reuse
            if source_id:
                _scene_tracker.register_source_cache(source_id, blender_obj.name)

        except Exception as e:
            raise IOError(
                f"Failed to import GLB file for '{object_name}' from '{object_path}'. Blender error: {e}"
            )
    else:
        raise IOError(
            f"Failed to import object '{object_name}' (source_id: {source_id}). "
            f"The file path was not found or was not a .glb file. Path: '{object_path}'"
        )

    # Set position, rotation, and scale
    blender_obj.location = (pos["x"], pos["y"], pos["z"])
    blender_obj.scale = (scl["x"], scl["y"], scl["z"])

    # Combine the original rotation with the rotation from the scene definition.
    original_rotation = Rotation.from_euler("xyz", blender_obj.rotation_euler)
    new_rotation = Rotation.from_euler("xyz", [rot["x"], rot["y"], rot["z"]], degrees=True)
    combined_rotation = new_rotation * original_rotation

    # Apply the combined rotation.
    blender_obj.rotation_euler = combined_rotation.as_euler("xyz")

    # Register the created object in tracker
    if object_id and blender_obj:
        _scene_tracker.register_object(obj_data, blender_obj.name)
        logger.debug(f"Registered object in tracker: {object_name} (id: {object_id})")


def _create_floor_mesh(
    boundary: list[dict[str, float]],
    room_id: str,
    floor_thickness_m: float = 0.1,
    origin: str = "center",
) -> dict[str, Any]:
    """
    Args:
        boundary: List of Vector2 points from room.boundary [{"x": float, "y": float}, ...]
        room_id: Room identifier for naming
        floor_thickness_m: Thickness of the floor in meters (default: 0.1)
        origin: Origin placement - "center" or "min" (default: "center")

    Returns:
        Dictionary with creation status and metadata
    """

    if not boundary or len(boundary) < 3:
        return {
            "status": "error",
            "message": f"Room {room_id}: At least 3 boundary points required for floor mesh",
        }

    floor_name = f"Floor_{room_id}"
    mesh_name = f"FloorMesh_{room_id}"

    # Check if floor already exists
    if floor_name in bpy.data.objects:
        logger.debug(f"Floor '{floor_name}' already exists, skipping creation")
        existing_floor = bpy.data.objects[floor_name]
        return {
            "status": "skipped",
            "object_name": floor_name,
            "mesh_name": existing_floor.data.name if existing_floor.data else mesh_name,
            "collection": "Floor",
            "room_id": room_id,
            "message": f"Floor '{floor_name}' already exists",
        }

    # Ensure floor collection exists
    collection = _ensure_collection("Floor")

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
        with suppress_blender_logs():
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
        "collection": "Floor",
        "room_id": room_id,
        "vertex_count": len(vertices_2d),
        "face_count": len(mesh.polygons),
        "thickness_m": floor_thickness_m,
        "origin_mode": origin,
        "bounds": bounds,
    }

    return result


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
    """Ensures a collection exists in the current scene and returns it.

    Creates scene-specific collections to avoid cross-scene contamination.
    """
    current_scene = bpy.context.scene

    # Create scene-specific collection name to avoid conflicts
    scene_specific_name = f"{collection_name}_{current_scene.name}"

    # Check if scene-specific collection already exists in current scene
    for collection in current_scene.collection.children:
        if collection.name == scene_specific_name:
            return collection

    # Check if it exists globally but not linked to current scene
    if scene_specific_name in bpy.data.collections:
        existing_collection = bpy.data.collections[scene_specific_name]
        current_scene.collection.children.link(existing_collection)
        return existing_collection

    # Create new scene-specific collection
    collection = bpy.data.collections.new(scene_specific_name)
    current_scene.collection.children.link(collection)
    logger.debug(f"Created collection '{scene_specific_name}' in scene '{current_scene.name}'")
    return collection


def _create_unlit_material(name: str, color: tuple[float, float, float, float]):
    """Creates or gets an unlit material with the specified name and color."""
    if name in bpy.data.materials:
        material = bpy.data.materials[name]
    else:
        material = bpy.data.materials.new(name=name)

    material.use_nodes = True
    # Clear existing nodes to start fresh
    for node in material.node_tree.nodes:
        material.node_tree.nodes.remove(node)

    # Create the new Emission and Material Output nodes
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    emission_node = nodes.new(type='ShaderNodeEmission')
    output_node = nodes.new(type='ShaderNodeOutputMaterial')

    # Set the color and link the nodes
    emission_node.inputs['Color'].default_value = color
    links.new(emission_node.outputs['Emission'], output_node.inputs['Surface'])
    return material


def _create_grid(
    grid_size_meters: int = 20,
    wireframe_thickness: float = 0.01,
    grid_color: tuple[float, float, float, float] = (0.2, 0.2, 0.2, 1.0),
    axis_thickness: float = 0.02,
    axis_extension: float = 1.0,
    axis_x_color: tuple[float, float, float, float] = (0.8, 0.1, 0.1, 1.0),
    axis_y_color: tuple[float, float, float, float] = (0.1, 0.8, 0.1, 1.0),
):
    """
    Creates a customizable grid in Blender with red (X) and green (Y) axis lines.

    Args:
        grid_size_meters: The width and height of the grid in meters
        wireframe_thickness: Thickness of the grid wireframe
        grid_color: RGBA color for the grid
        axis_thickness: Thickness of the axis lines
        axis_extension: How many meters the axis lines extend beyond the grid
        axis_x_color: RGBA color for the X-axis (red)
        axis_y_color: RGBA color for the Y-axis (green)
    """
    GRID_NAME = "Grid"

    # Check if grid already exists
    if GRID_NAME in bpy.data.objects:
        logger.debug(f"Grid '{GRID_NAME}' already exists, skipping creation")
        return

    with suppress_blender_logs():
        # Ensure we are in Object Mode
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Delete any existing grid objects to avoid duplicates
        for name in [GRID_NAME, "X_Axis", "Y_Axis"]:
            if name in bpy.data.objects:
                obj = bpy.data.objects[name]
                bpy.data.objects.remove(obj, do_unlink=True)

        # 1. Create the Plane mesh for the grid
        bpy.ops.mesh.primitive_plane_add(
            size=grid_size_meters,
            enter_editmode=False,
            align='WORLD',
            location=(0, 0, 0)
        )
        grid_object = bpy.context.active_object
        grid_object.name = GRID_NAME

        # 2. Subdivide the plane to create 1x1 meter squares
        subdivision_cuts = grid_size_meters - 1
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.subdivide(number_cuts=subdivision_cuts)
        bpy.ops.object.mode_set(mode='OBJECT')

        # 3. Apply the Wireframe modifier
        wireframe_mod = grid_object.modifiers.new(name="GridWire", type='WIREFRAME')
        wireframe_mod.thickness = wireframe_thickness
        wireframe_mod.use_replace = True

        # 4. Create and apply the grid material
        grid_material = _create_unlit_material("GridMaterial_Unlit", grid_color)
        if grid_object.data.materials:
            grid_object.data.materials[0] = grid_material
        else:
            grid_object.data.materials.append(grid_material)

        # 5. Create Axis Visualization
        total_axis_length = grid_size_meters + (axis_extension * 2)

        # X-Axis (Red Line)
        bpy.ops.mesh.primitive_cube_add(
            location=(0, 0, 0.001)  # Place slightly above grid to prevent z-fighting
        )
        x_axis_obj = bpy.context.active_object
        x_axis_obj.name = "X_Axis"
        x_axis_obj.scale = (total_axis_length / 2, axis_thickness / 2, 0.001)
        x_axis_mat = _create_unlit_material("Axis_X_Material", axis_x_color)
        x_axis_obj.data.materials.append(x_axis_mat)

        # Y-Axis (Green Line)
        bpy.ops.mesh.primitive_cube_add(
            location=(0, 0, 0.001)
        )
        y_axis_obj = bpy.context.active_object
        y_axis_obj.name = "Y_Axis"
        y_axis_obj.scale = (axis_thickness / 2, total_axis_length / 2, 0.001)
        y_axis_mat = _create_unlit_material("Axis_Y_Material", axis_y_color)
        y_axis_obj.data.materials.append(y_axis_mat)

        # 6. Parent axes to the grid so they move together
        x_axis_obj.parent = grid_object
        y_axis_obj.parent = grid_object

        # 7. Clean up selection state
        bpy.ops.object.select_all(action='DESELECT')
        grid_object.select_set(True)
        bpy.context.view_layer.objects.active = grid_object

    logger.debug(f"Successfully created '{GRID_NAME}' object with axis lines")


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

    with suppress_blender_logs():
        bpy.ops.wm.open_mainfile(filepath=path)
    logger.debug(f"Loaded template from {path}")


def save_scene(filepath: str):
    """Saves the current Blender scene to a .blend file."""
    if not filepath.endswith(".blend"):
        filepath += ".blend"

    # Pack all external images into the .blend file
    try:
        with suppress_blender_logs():
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

    with suppress_blender_logs():
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


def _configure_render_settings(
    engine: str = None, samples: int = 256, enable_gpu: bool = False
):
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
        preferred_engines = [
            "BLENDER_EEVEE_NEXT",
            "EEVEE",
            "CYCLES",
            "BLENDER_WORKBENCH",
        ]
        for candidate in preferred_engines:
            if candidate in available_engines:
                bpy.context.scene.render.engine = candidate
                break
        else:
            # Fallback to whatever is currently set if preferences are unavailable
            pass

    # Configure samples based on selected engine
    if samples is not None:
        # NOTE: set sample count for all engines, since the choice of rendering engine may be
        #       reverted later (and we don't want to waste time rendering 4096 samples of Cycles)
        # if bpy.context.scene.render.engine == "CYCLES":
        bpy.context.scene.cycles.samples = samples
        # elif bpy.context.scene.render.engine in ["BLENDER_EEVEE_NEXT", "EEVEE"]:
        bpy.context.scene.eevee.taa_render_samples = samples

    # Enable GPU rendering for Cycles if requested
    if enable_gpu and bpy.context.scene.render.engine == "CYCLES":
        try:
            # NOTE: seems to fail here
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "CUDA"  # Try CUDA first
            bpy.context.scene.cycles.device = "GPU"
        except Exception:
            # Fallback if CUDA not available or addon not found
            try:
                prefs = bpy.context.preferences.addons["cycles"].preferences
                prefs.compute_device_type = "OPENCL"
                bpy.context.scene.cycles.device = "GPU"
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
    with suppress_blender_logs():
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
    with suppress_blender_logs():
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
        with suppress_blender_logs():
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
    # logger.debug(f"Rendering scene to {output_path}")
    with suppress_blender_logs():
        # NOTE: `bpy` seems to switch context between `_configure_render_settings()` call
        #       and render call, reverting the rendering engine back to Cycles.
        # print(f"{bpy.context.scene.render.engine=}")  # TEMP
        bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"  # TEMP HACK
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
    with suppress_blender_logs():
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
    resolution=1024,
    format="jpg",
    output_dir: str = None,
    view: str = "top_down",
    background_color: tuple[float, float, float, float] = BACKGROUND_COLOR,
    show_grid: bool = False,
) -> Path:
    """
    Creates a visualization of the current scene.

    Args:
        resolution: The resolution of the output image.
        format: The format of the output image.
        output_dir: The directory to save the output image to.
        view: The view to render from. Can be 'top_down' or 'isometric'.
        background_color: RGBA color for the background.
        show_grid: Whether to show a grid in the visualization.

    Returns:
        Path to the rendered scene visualization file.
    """
    logger.debug(f"Setting up {view} orthographic render...")

    # Prepare output filepath
    if output_dir is None:
        output_dir = tempfile.gettempdir()

    output_path = get_filename(
        output_dir=output_dir,
        base_name=f"sb_scene_viz_{view}",
        extension=format.lower(),
        strategy="increment",
    )

    # Suppress verbose Blender output during scene setup and rendering
    with suppress_blender_logs():
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

        # Create grid if requested
        if show_grid:
            _create_grid()

        scene = bpy.context.scene
        setup_lighting_foundation(scene, background_color=background_color)
        setup_post_processing(scene)

    return render_to_file(output_path)


def visualize(scene=None, **kwargs):
    """
    A thin wrapper for `create_scene_visualization()` with active scene specifiability.
    """
    
    with SceneSwitcher(scene) as active_scene:
        return create_scene_visualization(**kwargs)


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
    background_color: tuple[float, float, float, float] = BACKGROUND_COLOR,
):
    """Sets up global illumination and world environment lighting."""
    print("Setting up foundation lighting...")
    scene.render.engine = "CYCLES"
    cycles_settings = scene.cycles

    # Configure GI bounces
    cycles_settings.max_bounces = 6
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

    # Create nodes for separating HDRI lighting from background color
    output_node = nt.nodes.new(type="ShaderNodeOutputWorld")
    output_node.location = (400, 0)

    # Mix Shader to combine HDRI lighting and background color
    mix_node = nt.nodes.new(type="ShaderNodeMixShader")
    mix_node.location = (200, 0)

    # Background node for HDRI lighting
    bg_hdri_node = nt.nodes.new(type="ShaderNodeBackground")
    bg_hdri_node.location = (0, 100)
    bg_hdri_node.inputs["Strength"].default_value = hdri_strength

    # Background node for solid color background
    bg_color_node = nt.nodes.new(type="ShaderNodeBackground")
    bg_color_node.location = (0, -100)
    bg_color_node.inputs["Color"].default_value = background_color
    bg_color_node.inputs["Strength"].default_value = 1.0

    # Light Path node to distinguish camera rays from other rays
    light_path_node = nt.nodes.new(type="ShaderNodeLightPath")
    light_path_node.location = (0, -250)

    # Set up HDRI or fallback color for lighting
    if hdri_path and Path(hdri_path).exists():
        env_node = nt.nodes.new(type="ShaderNodeTexEnvironment")
        env_node.location = (-200, 100)
        env_node.image = bpy.data.images.load(str(hdri_path))
        nt.links.new(env_node.outputs["Color"], bg_hdri_node.inputs["Color"])
    else:
        # Fallback to a neutral color for lighting
        bg_hdri_node.inputs["Color"].default_value = (0.1, 0.1, 0.1, 1.0)

    # Connect nodes: HDRI for lighting, solid color for camera-visible background
    nt.links.new(bg_hdri_node.outputs["Background"], mix_node.inputs[1])
    nt.links.new(bg_color_node.outputs["Background"], mix_node.inputs[2])
    nt.links.new(light_path_node.outputs["Is Camera Ray"], mix_node.inputs["Fac"])
    nt.links.new(mix_node.outputs["Shader"], output_node.inputs["Surface"])


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


def apply_floor_material(
    material_id: str,
    floor_object_name: str,
    uv_scale: Optional[float] = None,
    boundary: Optional[list] = None
) -> bool:
    """
    Apply a material to a floor object in Blender.
    Material should already be selected by LLM workflow.

    Args:
        material_id: Material UID from Graphics-DB (already selected by workflow)
        floor_object_name: Name of the floor object in Blender
        uv_scale: UV scaling for texture tiling (optional if boundary provided)
        boundary: List of Vector2 points for UV scale calculation

    Returns:
        True if successful, False otherwise
    """

    # Calculate UV scale from boundary if provided
    if boundary is not None and uv_scale is None:
        # Convert boundary points to tuples for _calculate_bounds
        boundary_tuples = []
        for point in boundary:
            if hasattr(point, "x"):  # Vector2 object
                boundary_tuples.append((point.x, point.y))
            else:  # Dictionary format
                boundary_tuples.append((point["x"], point["y"]))

        bounds = _calculate_bounds(boundary_tuples)
        current_size = max(bounds["width"], bounds["height"])
        reference_size = 10.0  # 10x10 room -> uv_scale=30.0 base
        reference_uv_scale = 30.0
        calculated_uv_scale = reference_uv_scale * (current_size / reference_size)
        uv_scale = calculated_uv_scale
    elif uv_scale is None:
        # Default UV scale
        uv_scale = 2.0

    # Download texture using MaterialDatabase
    material_db = MaterialDatabase()
    texture_path = material_db.download_texture(material_id)

    if not texture_path:
        logger.debug(f"Failed to download texture for material: {material_id}")
        return False

    # Apply texture using material_applicator
    success = texture_floor_mesh(
        floor_object_name=floor_object_name,
        texture_path=texture_path,
        uv_scale=uv_scale,
    )

    if success:
        logger.debug(f"Applied material {material_id} to floor {floor_object_name}")
    else:
        logger.debug(f"Failed to apply material to floor {floor_object_name}")

    return success

