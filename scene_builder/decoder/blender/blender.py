import math
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import bpy
import bmesh
import addon_utils
import numpy as np
import yaml
from matplotlib import pyplot as plt
from PIL import Image
from mathutils import Vector
from mathutils.geometry import tessellate_polygon
from scipy.spatial.transform import Rotation
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union

from scene_builder.config import BLENDER_LOG_FILE, TEST_ASSET_DIR
from scene_builder.database.material import MaterialDatabase
from scene_builder.decoder.blender_materials import create_translucent_material
from scene_builder.decoder.blender.controllers.interior_door import create_interior_door
from scene_builder.decoder.blender.controllers.window import create_window
from scene_builder.definition.scene import Object, Room, Scene, Vector2, find_shell
from scene_builder.importer import objaverse_importer, test_asset_importer
from scene_builder.logging import logger
from scene_builder.tools.material_applicator import texture_floor_mesh
from scene_builder.utils.blender import SceneSwitcher
from scene_builder.utils.conversions import pydantic_to_dict
from scene_builder.utils.file import get_filename
from scene_builder.utils.floorplan import (
    _find_adjacent_wall_segments_from_centers_to_edges,
    calculate_bounds_for_objects,
    classify_door_type,
    find_nearest_wall_point,
    longest_edge_angle,
    scale_boundary_for_cutout,
)
from scene_builder.utils.geometry import calculate_bounds_2d, distance_to_box_2d, polygon_centroid
from scene_builder.utils.image import compose_image_grid
from scene_builder.utils.scene import calculate_scene_bounds

HDRI_FILE_PATH = Path(
    f"{TEST_ASSET_DIR}/hdri/autumn_field_puresky_4k.exr"
).expanduser()  # TEMP HACK

BACKGROUND_COLOR = (0.02, 0.02, 0.02, 1.0)
DEFAULT_DOOR_HEIGHT = 2.5
DEFAULT_WINDOW_HEIGHT_BOTTOM = 1.0
DEFAULT_WINDOW_HEIGHT_TOP = 2.5
DEFAULT_WINDOW_DEPTH = 0.05  # Window thickness into wall (meters)

OBJECT_PREVIEW_CAMERA_NAME = "ObjectPreviewCamera"
OBJECT_LABEL_MATERIAL_NAME = "ObjectLabelMaterial"
OBJECT_HIGHLIGHT_PASS_INDEX = 101


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

        return existing.position == pos_tuple and existing.rotation == rot_tuple

    def object_exists_but_moved(self, object_id: str, pos: dict, rot: dict) -> bool:
        """Check if object exists but has moved to different position/rotation."""
        if object_id not in self._objects:
            return False

        # If it exists but positions/rotations don't match, it moved
        return not self.object_exists_unchanged(object_id, pos, rot)

    def register_object(
        self,
        obj_data: dict,
        blender_name: str,
    ):
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
            scale=(scale["x"], scale["y"], scale["z"]),
        )

    def clear_all(self):
        """Clear all tracked objects."""
        self._objects.clear()
        self._source_cache.clear()
        # logger.debug("Cleared all object tracking")

    def get_object_count(self) -> int:
        """Get total count of tracked objects."""
        return len(self._objects)

    def get_object_state(self, object_id: str) -> Optional[BlenderObjectState]:
        """Get current state for a specific object."""
        return self._objects.get(object_id)

    def iter_states(self) -> tuple[BlenderObjectState, ...]:
        """Return a snapshot tuple of all tracked object states."""

        return tuple(self._objects.values())

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


def iter_tracked_object_states() -> tuple[BlenderObjectState, ...]:
    """Return tracked object states."""

    return _scene_tracker.iter_states()


def get_tracked_object_state(object_id: str) -> Optional[BlenderObjectState]:
    """Return the tracked state for ``object_id`` if present."""

    return _scene_tracker.get_object_state(object_id)


def get_object_bounds(
    object_id: str,
) -> tuple[Tuple[float, float, float], Tuple[float, float, float]] | None:
    """Compute world-space bounding box corners for a tracked object."""

    state = _scene_tracker.get_object_state(object_id)
    if state is None:
        return None

    blender_obj = bpy.data.objects.get(state.blender_name)
    if blender_obj is None:
        return None

    return _compute_object_bounds(blender_obj)


def _iter_mesh_descendants(root_obj):
    """Yield mesh objects under the provided Blender object.

    Assets often import as empties that parent several mesh nodes.  Walking the
    hierarchy ensures the bounding-box query accounts for every mesh that makes
    up the logical object instead of just the top-level container.
    """

    stack = [root_obj]
    while stack:
        current = stack.pop()
        if current is None:
            continue
        if getattr(current, "type", None) == "MESH":
            yield current
        stack.extend(getattr(current, "children", []) or [])


def _compute_object_bounds(
    blender_obj,
) -> tuple[Tuple[float, float, float], Tuple[float, float, float]] | None:
    """Return world axis-aligned bounds for the provided object."""

    mesh_children = list(_iter_mesh_descendants(blender_obj))
    if not mesh_children:
        return None

    min_world = Vector((math.inf, math.inf, math.inf))
    max_world = Vector((-math.inf, -math.inf, -math.inf))

    for mesh_obj in mesh_children:
        try:
            matrix_world = mesh_obj.matrix_world
            corners = getattr(mesh_obj, "bound_box", None)
        except Exception:
            continue

        if not corners:
            continue

        for corner in corners:
            world_corner = matrix_world @ Vector(corner)
            min_world.x = min(min_world.x, world_corner.x)
            min_world.y = min(min_world.y, world_corner.y)
            min_world.z = min(min_world.z, world_corner.z)
            max_world.x = max(max_world.x, world_corner.x)
            max_world.y = max(max_world.y, world_corner.y)
            max_world.z = max(max_world.z, world_corner.z)

    return (
        (float(min_world.x), float(min_world.y), float(min_world.z)),
        (float(max_world.x), float(max_world.y), float(max_world.z)),
    )


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


def parse_scene_definition(scene_data: dict[str, Any], with_walls: bool = False):
    """
    Parses the scene definition dictionary and creates the scene in Blender.

    Optionally creates room walls (with structural cutouts) after all rooms
    are laid out when `with_walls` is True.

    Args:
        scene_data: A dictionary representing the scene, loaded from the YAML file.
        with_walls: If True, also create walls for all rooms after layout.
    """
    # logger.debug("Parsing scene definition and creating scene in Blender...")

    if isinstance(scene_data, Scene):
        scene_data = pydantic_to_dict(scene_data)

    # Clear the existing scene
    with suppress_blender_logs():
        _clear_scene()

    for room_data in scene_data.get("rooms", []):
        _create_room(room_data)

    # Optionally add walls after all floors/objects are created
    if with_walls:
        try:
            create_room_walls(scene_data.get("rooms", []))

            # Apply wall materials if specified in shells
            for room_data in scene_data.get("rooms", []):
                try:
                    wall_shell = find_shell(room_data, "wall")
                    if wall_shell and getattr(wall_shell, "material_id", None):
                        room_id = (
                            room_data.get("id")
                            if isinstance(room_data, dict)
                            else getattr(room_data, "id", "unknown")
                        )
                        apply_wall_material(
                            material_id=wall_shell.material_id,
                            wall_object_name=f"Wall_{room_id}",
                        )
                except Exception as mat_err:
                    logger.warning(f"Failed to apply wall material: {mat_err}")
        except Exception as e:
            logger.warning(f"Failed to create walls: {e}")


def parse_room_definition(
    room_data: dict[str, Any],
    clear=True,
    with_walls: Union[bool, str] = False,
):
    """
    Parses the room definition dictionary and creates the scene in Blender.

    Args:
        room_data: A dictionary representing the room, loaded from the YAML file.
        clear: Whether to clear the Blender scene before building room.
        with_walls: If True, also create walls for this room after layout.
                    If set to "translucent", creates walls with a translucent material
                    for clearer visual feedback.

    # NOTE: not sure if it's good for `clear` to default to True; (it was for testing)
    # NOTE: I think there's a bug where if `clear=True`, not all assets are recreated at next iteration's `parse_room_definition()` call. this happens after critique's rejection. look into it!
    """
    if isinstance(room_data, Room):
        room_data = pydantic_to_dict(room_data)

    logger.debug(f"Parsing room definition for {room_data['id']} and creating scene")

    with suppress_blender_logs():
        with SceneSwitcher(room_data["id"]):
            # Clear the existing scene
            if clear:
                _clear_scene()

            _create_room(room_data)

            if with_walls:
                try:
                    translucent = (
                        isinstance(with_walls, str) and with_walls.lower() == "translucent"
                    )
                    create_room_walls([room_data], translucent=translucent)

                    # Apply wall material if specified and walls are opaque
                    if not translucent:
                        try:
                            wall_shell = find_shell(room_data, "wall")
                            if wall_shell and getattr(wall_shell, "material_id", None):
                                room_id = (
                                    room_data.get("id")
                                    if isinstance(room_data, dict)
                                    else getattr(room_data, "id", "unknown")
                                )
                                apply_wall_material(
                                    material_id=wall_shell.material_id,
                                    wall_object_name=f"Wall_{room_id}",
                                )
                        except Exception as mat_err:
                            logger.warning(f"Failed to apply wall material: {mat_err}")
                except Exception as e:
                    logger.warning(
                        f"Failed to create walls for room {room_data.get('id', 'unknown')}: {e}"
                    )


def cleanup_orphan_data(num_passes: int = 3):
    """Removes unused data blocks (meshes, materials, images, etc.) from Blender.

    Uses Blender's built-in orphan purge operator with multiple passes to handle
    cascading orphans (data blocks that become orphaned after others are removed).

    Args:
        num_passes: Number of purge passes to run (default: 3)

    Returns:
        Number of passes executed
    """
    with suppress_blender_logs():
        for i in range(num_passes):
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

    logger.debug(f"Cleaned up orphan data blocks ({num_passes} passes)")
    return num_passes


def _clear_scene():
    """Clears all objects from the current Blender scene."""
    with suppress_blender_logs():
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()

    # Clear object tracking as well
    _scene_tracker.clear_all()

    logger.debug("Cleared existing scene.")


def _create_room(room_data: dict[str, Any]):
    """Creates a representation of a room including floor mesh and objects."""
    if room_data is None:
        logger.warning("room_data is None, skipping room creation")
        return

    room_id = room_data.get("id", "unknown_room")
    logger.debug(f"Creating room: {room_id}")

    # Create floor mesh
    floor_result = _create_floor_mesh(room_data["boundary"], room_id)
    logger.debug(f"Created floor: {floor_result['status']}")

    # Apply floor material
    floor = find_shell(room_data, "floor")
    if floor and getattr(floor, "material_id", None):
        apply_floor_material(
            material_id=floor.material_id,
            floor_object_name=floor_result["object_name"],
            boundary=room_data["boundary"],
        )
        logger.debug(f"Applied material {floor.material_id} to floor")
    # Create objects in the room
    for obj_data in room_data.get("objects", []):
        try:
            _create_object(obj_data)
        except Exception as e:
            logger.warning(e)


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
        logger.debug(
            f"Skipping duplicate object: {object_name} (id: {object_id}) - unchanged at {pos}"
        )
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
        logger.debug(
            f"Skipping duplicate object: {object_name} (id: {object_id}) - unchanged at {pos}"
        )
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

            # Duplicate the entire cached hierarchy via selection, linking mesh data
            with suppress_blender_logs():
                # Deselect everything
                bpy.ops.object.select_all(action="DESELECT")

                # Ensure the root is selected and active
                cached_empty.select_set(True)
                bpy.context.view_layer.objects.active = cached_empty

                # Select all descendants (recursive) using Blender operator
                bpy.ops.object.select_grouped(type="CHILDREN_RECURSIVE", extend=True)

                # Snapshot objects before duplication to identify new ones
                pre_objs = set(bpy.data.objects)

                # Perform a linked duplicate so meshes share data
                bpy.ops.object.duplicate(linked=True)

            # Identify duplicated objects and pick the duplicated root
            post_objs = set(bpy.data.objects)
            new_objs = list(post_objs - pre_objs)
            if not new_objs:
                raise RuntimeError("Linked duplication produced no new objects.")

            dup_roots = [o for o in new_objs if (o.parent is None) or (o.parent not in new_objs)]
            if not dup_roots:
                # Fallback: use any new object; hierarchy may be flat
                dup_roots = [new_objs[0]]

            blender_obj = dup_roots[0]
            blender_obj.name = object_name

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
                _scene_tracker.register_object(
                    obj_data,
                    blender_obj.name,
                )
                logger.debug(f"Registered object in tracker: {object_name} (id: {object_id})")

            return

    if obj_data.get("source").lower() == "objaverse":
        if not source_id:
            raise ValueError(f"Object '{object_name}' has source 'objaverse' but no 'source_id'.")

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
            imported_objects = [obj for obj in bpy.context.selected_objects if obj.parent is None]

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
        _scene_tracker.register_object(
            obj_data,
            blender_obj.name,
        )
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
            logger.debug(f"Direct face creation failed: {e}. Attempting triangulation...")

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
        # logger.debug(f"Generated UV coordinates for floor: {floor_name}")

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
    bounds = calculate_bounds_2d(vertices_2d)

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


def _create_window_cutout(
    wall_obj,
    apt_id: str,
    window_idx: int,
    window_boundary: list,
    z_bottom: float,
    z_top: float,
    scale_factor: float = 2.00,
    scale_short_axis: bool = True,
    scale_long_axis: bool = True,
    scale_long_factor: float = 0.95,
    debug=False,
    keep_cutter_visible: bool = False,
):
    """Create and apply a window cutout to a wall object.

    Scales the window boundary by scale_factor and applies a boolean cutout operation.

    Args:
        wall_obj: Blender wall object to cut
        apt_id: Apartment ID for naming
        window_idx: Window index for naming
        window_boundary: List of (x, y) tuples defining window polygon
        z_bottom: Bottom Z height of window cutout
        z_top: Top Z height of window cutout
        scale_factor: Factor to scale the shorter axis (default: 2.00)
        scale_short_axis: If True, scale along the axis orthogonal to the dominant direction (default: True)
        scale_long_axis: If True, scale along the dominant (longer) direction (default: True)
        scale_long_factor: Factor to scale the longer axis (default: 0.99)
        debug: If True, plots window geometry (original scaled, dominant axis) (default: False)
        keep_cutter_visible: If True, keep the cutter object visible with red color for debugging (default: False)
    """
    # Scale the window boundary using geometry function (no Blender dependency)
    expanded_boundary = scale_boundary_for_cutout(
        boundary=window_boundary,
        scale_short_factor=scale_factor,
        scale_short_axis=scale_short_axis,
        scale_long_axis=scale_long_axis,
        scale_long_factor=scale_long_factor,
        debug=debug,
        debug_prefix="window",
        debug_id=f"{apt_id}_{window_idx}",
    )

    # Create cutter mesh and apply boolean operation (Blender-specific)
    cutter_mesh = bpy.data.meshes.new(f"WindowCutter_{apt_id}_{window_idx}")
    cutter_obj = bpy.data.objects.new(f"WindowCutter_{apt_id}_{window_idx}", cutter_mesh)
    bpy.context.collection.objects.link(cutter_obj)

    bm = bmesh.new()
    try:
        # Create bottom and top vertices
        bottom_verts = [bm.verts.new((x, y, z_bottom)) for x, y in expanded_boundary]
        top_verts = [bm.verts.new((x, y, z_top)) for x, y in expanded_boundary]
        bm.verts.ensure_lookup_table()

        # Create faces
        bm.faces.new(bottom_verts)
        bm.faces.new(list(reversed(top_verts)))

        num_verts = len(bottom_verts)
        for i in range(num_verts):
            next_i = (i + 1) % num_verts
            bm.faces.new([bottom_verts[i], bottom_verts[next_i], top_verts[next_i], top_verts[i]])

        bm.to_mesh(cutter_mesh)
        cutter_mesh.update()
    finally:
        bm.free()

    bpy.context.view_layer.objects.active = cutter_obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    cutter_obj.display_type = "WIRE" if hasattr(cutter_obj, "display_type") else "SOLID"

    # Apply boolean modifier
    bool_mod = wall_obj.modifiers.new(name=f"WindowCut_{window_idx}", type="BOOLEAN")
    bool_mod.operation = "DIFFERENCE"
    bool_mod.object = cutter_obj

    bpy.context.view_layer.objects.active = wall_obj
    bpy.ops.object.modifier_apply(modifier=bool_mod.name)

    if not keep_cutter_visible:
        bpy.data.objects.remove(cutter_obj, do_unlink=True)


def _create_interior_door_cutout(
    wall_obj,
    apt_id: str,
    door_idx: int,
    door_boundary: list,
    z_bottom: float = 0.0,
    z_top: float = 2.1,
    scale_factor: float = 2.00,
    scale_short_axis: bool = True,
    scale_long_axis: bool = True,
    scale_long_factor: float = 0.98,
    debug=False,
    keep_cutter_visible: bool = False,
):
    """Create and apply an interior door cutout to a wall object.

    Scales the door boundary by scale_factor and applies a boolean cutout operation.

    Args:
        wall_obj: Blender wall object to cut
        apt_id: Apartment ID for naming
        door_idx: Door index for naming
        door_boundary: List of (x, y) tuples defining door polygon
        z_bottom: Bottom Z height of door cutout (default: 0.0)
        z_top: Top Z height of door cutout (default: 2.1)
        scale_factor: Factor to scale the shorter axis (default: 2.00)
        scale_short_axis: If True, scale along the axis orthogonal to the dominant direction (default: True)
        scale_long_axis: If True, scale along the dominant (longer) direction (default: True)
        scale_long_factor: Factor to scale the longer axis (default: 0.99)
        debug: If True, plots door geometry (original scaled, dominant axis) (default: False)
        keep_cutter_visible: If True, keep the cutter object visible with red color for debugging (default: False)
    """
    # Scale the door boundary using geometry function (no Blender dependency)
    expanded_boundary = scale_boundary_for_cutout(
        boundary=door_boundary,
        scale_short_factor=scale_factor,
        scale_short_axis=scale_short_axis,
        scale_long_axis=scale_long_axis,
        scale_long_factor=scale_long_factor,
        debug=debug,
        debug_prefix="interior_door",
        debug_id=f"{apt_id}_{door_idx}",
    )

    # Create cutter mesh (Blender-specific)
    cutter_mesh = bpy.data.meshes.new(f"InteriorDoorCutter_{apt_id}_{door_idx}")
    cutter_obj = bpy.data.objects.new(f"InteriorDoorCutter_{apt_id}_{door_idx}", cutter_mesh)
    bpy.context.collection.objects.link(cutter_obj)

    bm = bmesh.new()
    try:
        # Create bottom and top vertices
        bottom_verts = [bm.verts.new((x, y, z_bottom)) for x, y in expanded_boundary]
        top_verts = [bm.verts.new((x, y, z_top)) for x, y in expanded_boundary]
        bm.verts.ensure_lookup_table()

        # Create faces
        bm.faces.new(bottom_verts)
        bm.faces.new(list(reversed(top_verts)))

        # Create side faces
        num_verts = len(bottom_verts)
        for i in range(num_verts):
            next_i = (i + 1) % num_verts
            bm.faces.new([bottom_verts[i], bottom_verts[next_i], top_verts[next_i], top_verts[i]])

        bm.to_mesh(cutter_mesh)
        cutter_mesh.update()
    finally:
        bm.free()

    bpy.context.view_layer.objects.active = cutter_obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    cutter_obj.display_type = "WIRE" if hasattr(cutter_obj, "display_type") else "SOLID"
    # Apply boolean modifier
    bool_mod = wall_obj.modifiers.new(name=f"InteriorDoorCut_{door_idx}", type="BOOLEAN")
    bool_mod.operation = "DIFFERENCE"
    bool_mod.object = cutter_obj

    bpy.context.view_layer.objects.active = wall_obj
    bpy.ops.object.modifier_apply(modifier=bool_mod.name)

    if not keep_cutter_visible:
        bpy.data.objects.remove(cutter_obj, do_unlink=True)


def check_and_enable_door_addon() -> bool:
    """Enable Door It! Interior addon."""

    addon_module = (
        "DoorItInterior"  # NOTE: more addon_moudle will be added for exterior walls, windows, etc.
    )

    bpy.ops.preferences.addon_enable(module=addon_module)
    addon_utils.modules_refresh()
    logger.debug(f"Enabled {addon_module} addon")


def create_door_from_boundary(
    door_boundary: list,
    door_id: str,
    z_position: float = 0.0,
    **door_settings,
) -> Optional[Dict[str, object]]:
    """Create a Door It! Interior door object from a door boundary polygon.

    Args:
        door_boundary: List of (x, y) tuples defining door polygon
        door_id: Unique identifier for the door
        z_position: Z-height to place the door (default: 0.0 for floor level)
        **door_settings: Additional settings to pass to create_interior_door
                        (e.g., door_height, randomize_type, randomize_handle, etc.)

    Returns:
        Dictionary with creation summary, or None if failed

    Note:
        Door depth is automatically calculated from the door boundary polygon.
    """

    # Create polygon and get basic properties
    door_poly = Polygon(door_boundary)
    centroid = door_poly.centroid
    centroid_coords = (centroid.x, centroid.y)

    rotation_angle = longest_edge_angle(door_poly)

    # Rotate polygon to axis-aligned orientation
    aligned_poly = affinity.rotate(
        door_poly, rotation_angle, origin=centroid_coords, use_radians=False
    )

    # Get axis-aligned dimensions
    minx, miny, maxx, maxy = aligned_poly.bounds
    width = maxx - minx
    height = maxy - miny

    # Determine which is longer axis
    is_width_dominant = width >= height

    clearance_per_side = 0.04  # Add 0.02m clearance on each side (0.04m total)

    if is_width_dominant:
        door_depth = height  # Use actual depth from door boundary
        door_width = width + (clearance_per_side * 2)  # Longer axis + clearance
    else:
        door_depth = width  # Use actual depth from door boundary
        door_width = height + (clearance_per_side * 2)  # Longer axis + clearance

    door_height = door_settings.pop("door_height", DEFAULT_DOOR_HEIGHT)

    location = (centroid.x, centroid.y, z_position)

    # logger.debug(
    #     f"Door {door_id}: dimensions x={door_depth:.3f}m (depth), "
    #     f"y={door_width:.3f}m (width), z={door_height:.3f}m (height), "
    #     f"rotation={-rotation_angle:.1f}°"
    # )

    result = create_interior_door(
        name=f"InteriorDoor_{door_id}",
        location=location,
        rotation_angle=rotation_angle + 90,
        width=door_width,
        height=door_height,
        depth=door_depth,
        **door_settings,
    )

    # Log door creation
    if result.get("created") or result.get("linked"):
        door_obj = bpy.data.objects.get(result["object"])
        controller_name = result.get("controller")

        if door_obj and controller_name:
            logger.debug(
                f"Created door '{door_obj.name}' at {location} with rotation {-rotation_angle:.1f}° via empty controller '{controller_name}'"
            )

    return result


def create_window_from_boundary(
    window_boundary: list,
    window_id: str,
    z_position: float = 0.0,
    window_height_bottom: float = DEFAULT_WINDOW_HEIGHT_BOTTOM,
    window_height_top: float = DEFAULT_WINDOW_HEIGHT_TOP,
    room_boundaries: Optional[list] = None,
    **window_settings,
) -> Optional[Dict[str, object]]:
    """Create a Window object from a window boundary polygon.

    Args:
        window_boundary: List of (x, y) tuples defining window polygon
        window_id: Unique identifier for the window
        z_position: Z-height to place the window (default: 0.0 for floor level)
        window_height_bottom: Bottom height of window (default: DEFAULT_WINDOW_HEIGHT_BOTTOM)
        window_height_top: Top height of window (default: DEFAULT_WINDOW_HEIGHT_TOP)
        room_boundaries: List of room boundaries to find nearest wall point (optional)
        **window_settings: Additional settings to pass to create_window

    Returns:
        Dictionary with creation summary, or None if failed
    """

    # Create polygon and get basic properties
    window_poly = Polygon(window_boundary)
    centroid = window_poly.centroid
    centroid_coords = (centroid.x, centroid.y)
    window_center = Vector2(x=centroid.x, y=centroid.y)

    rotation_angle = longest_edge_angle(window_poly)

    # Rotate polygon to axis-aligned orientation
    aligned_poly = affinity.rotate(
        window_poly, rotation_angle, origin=centroid_coords, use_radians=False
    )

    # Get axis-aligned dimensions
    minx, miny, maxx, maxy = aligned_poly.bounds
    width = maxx - minx
    height = maxy - miny

    # Determine which is longer axis (width is the horizontal opening dimension)
    is_width_dominant = width >= height

    # For windows, we use the dimensions directly (no clearance needed like doors)
    if is_width_dominant:
        window_width = width
    else:
        window_width = height

    # Set fixed window depth (thickness into wall)
    window_depth = DEFAULT_WINDOW_DEPTH

    # Calculate window vertical height from top and bottom heights
    window_height_value = window_height_top - window_height_bottom

    # Find nearest wall point if room boundaries provided
    if room_boundaries:
        nearest_wall_point = find_nearest_wall_point(window_center, room_boundaries)
        if nearest_wall_point:
            # Use the nearest wall point as the window location
            location = (nearest_wall_point.x, nearest_wall_point.y, z_position)
            logger.debug(
                f"Window {window_id}: positioned at nearest wall point ({nearest_wall_point.x:.3f}, {nearest_wall_point.y:.3f})"
            )
        else:
            # Fall back to centroid if no wall point found
            location = (centroid.x, centroid.y, z_position)
    else:
        # Use centroid if no room boundaries provided
        location = (centroid.x, centroid.y, z_position)

    logger.debug(
        f"Window {window_id}: dimensions x={window_depth:.3f}m (depth), "
        f"y={window_width:.3f}m (width), z={window_height_value:.3f}m (height), "
        f"rotation={-rotation_angle:.1f}°"
    )

    result = create_window(
        name=f"Window_{window_id}",
        location=location,
        rotation_angle=rotation_angle + 90,
        width=window_width,
        height=window_height_value,
        depth=window_depth,
        **window_settings,
    )

    # Log window creation (no longer using push_window_to_wall)
    if result.get("created") or result.get("linked"):
        window_obj = bpy.data.objects.get(result["object"])
        controller_name = result.get("controller")

        if window_obj and controller_name:
            logger.debug(
                f"Created window '{window_obj.name}' at {location} with rotation {-rotation_angle:.1f}° via empty controller '{controller_name}'"
            )

    return result


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
    emission_node = nodes.new(type="ShaderNodeEmission")
    output_node = nodes.new(type="ShaderNodeOutputMaterial")

    # Set the color and link the nodes
    emission_node.inputs["Color"].default_value = color
    links.new(emission_node.outputs["Emission"], output_node.inputs["Surface"])
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
    current_scene = bpy.context.scene
    GRID_NAME = f"Grid_{current_scene.name}"
    X_AXIS_NAME = f"X_Axis_{current_scene.name}"
    Y_AXIS_NAME = f"Y_Axis_{current_scene.name}"

    # Check if grid already exists in current scene
    if GRID_NAME in bpy.data.objects and GRID_NAME in current_scene.objects:
        logger.debug(
            f"Grid '{GRID_NAME}' already exists in scene '{current_scene.name}', skipping creation"
        )
        return

    with suppress_blender_logs():
        # Ensure we are in Object Mode
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        # Delete any existing grid objects to avoid duplicates
        for name in [GRID_NAME, X_AXIS_NAME, Y_AXIS_NAME]:
            if name in bpy.data.objects:
                obj = bpy.data.objects[name]
                bpy.data.objects.remove(obj, do_unlink=True)

        # Create the Plane mesh for the grid
        bpy.ops.mesh.primitive_plane_add(
            size=grid_size_meters, enter_editmode=False, align="WORLD", location=(0, 0, 0)
        )
        grid_object = bpy.context.active_object
        grid_object.name = GRID_NAME

        # Subdivide the plane to create 1x1 meter squares
        subdivision_cuts = grid_size_meters - 1
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.subdivide(number_cuts=subdivision_cuts)
        bpy.ops.object.mode_set(mode="OBJECT")

        # Apply the Wireframe modifier
        wireframe_mod = grid_object.modifiers.new(name="GridWire", type="WIREFRAME")
        wireframe_mod.thickness = wireframe_thickness
        wireframe_mod.use_replace = True

        # Create and apply the grid material
        grid_material = _create_unlit_material("GridMaterial_Unlit", grid_color)
        if grid_object.data.materials:
            grid_object.data.materials[0] = grid_material
        else:
            grid_object.data.materials.append(grid_material)

        # Create Axis Visualization
        total_axis_length = grid_size_meters + (axis_extension * 2)

        # X-Axis (Red Line)
        bpy.ops.mesh.primitive_cube_add(
            location=(0, 0, 0.001)  # Place slightly above grid to prevent z-fighting
        )
        x_axis_obj = bpy.context.active_object
        x_axis_obj.name = X_AXIS_NAME
        x_axis_obj.scale = (total_axis_length / 2, axis_thickness / 2, 0.001)
        x_axis_mat = _create_unlit_material("Axis_X_Material", axis_x_color)
        x_axis_obj.data.materials.append(x_axis_mat)

        # Y-Axis (Green Line)
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0.001))
        y_axis_obj = bpy.context.active_object
        y_axis_obj.name = Y_AXIS_NAME
        y_axis_obj.scale = (axis_thickness / 2, total_axis_length / 2, 0.001)
        y_axis_mat = _create_unlit_material("Axis_Y_Material", axis_y_color)
        y_axis_obj.data.materials.append(y_axis_mat)

        # Parent axes to the grid so they move together
        x_axis_obj.parent = grid_object
        y_axis_obj.parent = grid_object

        # Clean up selection state
        bpy.ops.object.select_all(action="DESELECT")
        grid_object.select_set(True)
        bpy.context.view_layer.objects.active = grid_object

    # logger.debug(f"Successfully created '{GRID_NAME}' object with axis lines")


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


def save_scene(filepath: str, scene: str = None, exclude_grid: bool = True):
    """
    Saves a Blender scene to a .blend file.

    Args:
        filepath: Path to save the .blend file.
        scene: Name of the scene to save. If None, uses current scene.
        exclude_grid: If True, temporarily removes grid objects before saving.
    """
    if not filepath.endswith(".blend"):
        filepath += ".blend"

    with SceneSwitcher(scene) as active_scene:
        # Temporarily remove grid if requested
        grid_objects = []
        if exclude_grid:
            current_scene = bpy.context.scene
            GRID_NAME = f"Grid_{current_scene.name}"
            X_AXIS_NAME = f"X_Axis_{current_scene.name}"
            Y_AXIS_NAME = f"Y_Axis_{current_scene.name}"

            for name in [GRID_NAME, X_AXIS_NAME, Y_AXIS_NAME]:
                if name in bpy.data.objects and name in current_scene.objects:
                    obj = bpy.data.objects[name]
                    grid_objects.append((name, obj))
                    current_scene.collection.objects.unlink(obj)

        # Clean up unused data blocks before saving
        cleanup_orphan_data()

        # Pack all external images into the .blend file
        try:
            with suppress_blender_logs():
                bpy.ops.file.pack_all()
            # logger.debug("Packed all external images into .blend file")
        except Exception as e:
            logger.debug(f"Warning: Could not pack images: {e}")

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

        # Re-link grid objects if they were temporarily removed
        if exclude_grid and grid_objects:
            for name, obj in grid_objects:
                current_scene.collection.objects.link(obj)


def export_to_gltf(filepath: str, scene: str = None, exclude_grid: bool = True) -> Path:
    """
    Exports a Blender scene to a GLTF file.

    Args:
        filepath: Path to save the GLTF file.
        scene: Name of the scene to export. If None, uses current scene.
        exclude_grid: If True, temporarily removes grid objects before exporting.

    Returns:
        Path to the exported GLTF file.
    """
    if not filepath.endswith(".gltf") and not filepath.endswith(".glb"):
        filepath += ".gltf"

    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with SceneSwitcher(scene) as active_scene:
        # Temporarily remove grid if requested
        grid_objects = []
        if exclude_grid:
            current_scene = bpy.context.scene
            GRID_NAME = f"Grid_{current_scene.name}"
            X_AXIS_NAME = f"X_Axis_{current_scene.name}"
            Y_AXIS_NAME = f"Y_Axis_{current_scene.name}"

            for name in [GRID_NAME, X_AXIS_NAME, Y_AXIS_NAME]:
                if name in bpy.data.objects and name in current_scene.objects:
                    obj = bpy.data.objects[name]
                    grid_objects.append((name, obj))
                    current_scene.collection.objects.unlink(obj)

        # Export to GLTF
        with suppress_blender_logs():
            bpy.ops.export_scene.gltf(
                filepath=str(filepath),
                export_format="GLTF_EMBEDDED" if filepath.suffix == ".gltf" else "GLB",
                use_selection=False,
            )

        logger.debug(f"Scene exported to GLTF: {filepath}")

        # Re-link grid objects if they were temporarily removed
        if exclude_grid and grid_objects:
            for name, obj in grid_objects:
                current_scene.collection.objects.link(obj)

    return filepath


def debug_scene_summary(max_other: int = 20) -> dict:
    """Return a quick summary of objects in the current scene.

    Includes lists of floor and wall object names and a sample of other objects.
    """
    objs = list(bpy.context.scene.objects)
    floors = [o.name for o in objs if o.type == "MESH" and o.name.startswith("Floor_")]
    walls = [o.name for o in objs if o.type == "MESH" and o.name.startswith("Wall_")]
    others = [(o.name, o.type) for o in objs if o.name not in floors + walls][:max_other]

    summary = {
        "count": len(objs),
        "floors": floors,
        "walls": walls,
        "others": others,
    }
    logger.debug(
        "Scene summary: count=%d, floors=%d, walls=%d, others(sample)=%d",
        summary["count"],
        len(floors),
        len(walls),
        len(others),
    )
    return summary


def _configure_output_image(format: str, resolution: int):
    format = format.upper()
    mapping = {"JPG": "JPEG"}
    if format in mapping.keys():
        format = mapping[format]

    bpy.context.scene.render.image_settings.file_format = format
    bpy.context.scene.render.resolution_x = resolution
    bpy.context.scene.render.resolution_y = resolution
    bpy.context.scene.render.resolution_percentage = 100


def _configure_render_settings(engine: str = None, samples: int = 256, enable_gpu: bool = False):
    """Selects a compatible render engine and configures render settings."""

    available_engines = ["BLENDER_EEVEE", "BLENDER_WORKBENCH", "CYCLES"]
    # try:
    #     engine_prop = bpy.context.scene.render.bl_rna.properties["engine"]
    #     available_engines = [item.identifier for item in engine_prop.enum_items]
    # except Exception:
    #     available_engines = []

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

    # Enable shadows for EEVEE engines
    if bpy.context.scene.render.engine in ["BLENDER_EEVEE_NEXT", "EEVEE"]:
        bpy.context.scene.eevee.use_shadows = True

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


def _setup_top_down_camera(auto_zoom: bool = True, margin: float = 2.0):
    """Sets up a top-down orthographic camera.

    Args:
        auto_zoom: Automatically fit camera to scene bounds
        margin: Multiplicative margin for auto-zoom (e.g., 1.5 = 50% padding)
    """
    # Clear existing cameras
    for obj in bpy.context.scene.objects:
        if obj.type == "CAMERA":
            bpy.data.objects.remove(obj, do_unlink=True)

    # Calculate ortho_scale
    if auto_zoom:
        bounds = calculate_scene_bounds()
        if bounds:
            min_x, max_x, min_y, max_y, _, _ = bounds
            width = max_x - min_x
            height = max_y - min_y
            # Use the larger dimension and apply margin
            ortho_scale = max(width, height) * margin
        else:
            ortho_scale = 20.0  # Fallback
    else:
        ortho_scale = 20.0

    # Add top-down orthographic camera
    with suppress_blender_logs():
        bpy.ops.object.camera_add(location=(0, 0, 10))  # 10 units above origin
    camera = bpy.context.object
    camera.name = "TopDownCamera"

    # Set to orthographic projection
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale

    # Point camera straight down (top-down view)
    camera.rotation_euler = (0, 0, 0)  # Looking straight down Z-axis

    # Set as active camera
    bpy.context.scene.camera = camera


def _setup_isometric_camera(auto_zoom: bool = True, margin: float = 2.0):
    """Sets up an isometric orthographic camera.

    Args:
        auto_zoom: Automatically fit camera to scene bounds
        margin: Multiplicative margin for auto-zoom (e.g., 1.5 = 50% padding)
    """
    # Clear existing cameras
    for obj in bpy.context.scene.objects:
        if obj.type == "CAMERA":
            bpy.data.objects.remove(obj, do_unlink=True)

    # Calculate ortho_scale
    if auto_zoom:
        bounds = calculate_scene_bounds()
        if bounds:
            min_x, max_x, min_y, max_y, min_z, max_z = bounds
            width = max_x - min_x
            height = max_y - min_y
            # For isometric view, consider all three dimensions
            # Use diagonal distance for better framing
            diagonal = max(width, height) * math.sqrt(
                2
            )  # might be something in the right direction. scale power should not be linear.
            ortho_scale = diagonal * margin * 0.7  # Scale factor for isometric projection # ORIG
            # ortho_scale = diagonal * margin * 0.7**4 # HACK
            # ortho_scale = diagonal * margin * 0.7**3 # HACK
        else:
            ortho_scale = 20.0  # Fallback
    else:
        ortho_scale = 20.0

    # Add isometric orthographic camera
    with suppress_blender_logs():
        bpy.ops.object.camera_add(location=(10, -10, 10))
        # bpy.ops.object.camera_add(location=(5.77, -5.77, 5.77))
    camera = bpy.context.object
    camera.name = "IsometricCamera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale

    # Point camera towards the origin with isometric rotation
    camera.rotation_euler = (math.radians(54.736), 0, math.radians(45))

    # Set as active camera
    bpy.context.scene.camera = camera


def _apply_camera_track(camera: bpy.types.Object, target: bpy.types.Object) -> None:
    """Apply tracking constraints so the camera points at ``target`` while staying upright.

    Adds two Locked Track constraints:
    - TRACK_NEGATIVE_Z with LOCK_Y
    - TRACK_NEGATIVE_Z with LOCK_X

    This combination robustly preserves world-up (+Z) without roll while aiming at the target.
    Any existing TRACK_TO/DAMPED_TRACK/LOCKED_TRACK constraints are removed first.
    """
    # Remove existing tracking constraints to avoid stacking
    for c in list(camera.constraints):
        if c.type in ("TRACK_TO", "DAMPED_TRACK", "LOCKED_TRACK"):
            camera.constraints.remove(c)

    def _add_locked(lock_axis: str):
        con = camera.constraints.new(type="LOCKED_TRACK")
        con.target = target
        # Cameras in Blender look down -Z
        con.track_axis = "TRACK_NEGATIVE_Z"
        con.lock_axis = lock_axis
        return con

    # Apply two locked tracks for stability
    _add_locked("LOCK_Y")
    _add_locked("LOCK_X")


def _setup_egocentric_camera(
    auto_zoom: bool = True,
    margin: float = 1.5,
    fallback_distance: float = 5.0,
    default_height: float = 1.6,
    track_target: Optional[bpy.types.Object] = None,
):
    """Sets up a perspective camera from a first-person viewpoint.

    If ``track_target`` is provided, attaches a tracking constraint so the camera
    continuously points at that object instead of computing orientation manually.
    """

    for obj in bpy.context.scene.objects:
        if obj.type == "CAMERA":
            bpy.data.objects.remove(obj, do_unlink=True)

    bounds = calculate_scene_bounds()

    if bounds:
        min_x, max_x, min_y, max_y, min_z, max_z = bounds
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        center_z = (min_z + max_z) / 2
        width = max_x - min_x
        depth = max_y - min_y
    else:
        center_x = center_y = 0.0
        min_z = 0.0
        center_z = default_height
        width = depth = 4.0

    camera_height = max(center_z, min_z + default_height)

    with suppress_blender_logs():
        bpy.ops.object.camera_add(location=(center_x, center_y, camera_height))

    camera = bpy.context.object
    camera.name = "EgocentricCamera"
    camera.data.type = "PERSP"
    camera.data.clip_start = 0.05
    camera.data.clip_end = 500.0
    # Spawn with initial rotation: +X 90 degrees (XYZ Euler)
    camera.rotation_euler = (math.radians(90.0), 0.0, 0.0)

    if auto_zoom:
        forward_distance = max(max(width, depth) * margin, 1.0)
        lens = max(18.0, min(45.0, (36.0 * margin) / max(max(width, depth), 1.0)))
    else:
        forward_distance = fallback_distance
        lens = 35.0

    if track_target is not None:
        _apply_camera_track(camera, track_target)
    else:
        # Manual look-at straight ahead along +Y at eye height
        look_target = Vector((center_x, center_y + forward_distance, camera_height))
        direction = look_target - Vector(camera.location)
        if direction.length == 0:
            direction = Vector((0.0, 1.0, 0.0))
        camera.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    camera.data.lens = lens

    bpy.context.scene.camera = camera


def _setup_lighting(energy: float = 0.2):
    """Sets up basic lighting for the scene."""
    if not any(obj.type == "LIGHT" for obj in bpy.context.scene.objects):
        with suppress_blender_logs():
            bpy.ops.object.light_add(type="SUN", location=(0, 0, 15))
        light = bpy.context.object
        light.data.energy = energy
        light.rotation_euler = (math.radians(15), math.radians(30), 0)  # tilt, rotation, ?
        # logger.debug("Added top-down lighting")


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
        # bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"  # TEMP HACK
        bpy.ops.render.render(write_still=True)

    if output_path.exists():
        logger.debug(f"Render completed: {output_path}")
        return output_path
    else:
        raise IOError(f"Render failed - output file not created: {output_path}")


def render_to_numpy() -> np.ndarray:
    """
    Alternative: Render directly to NumPy array in memory (no file).

    NOTE: This function does not seem to work with `bpy` in "standalone" mode (directly invoked from Python).
          To save render, it seems necessary to save the render into the filesystem, and retrieve as file.

    Returns:
        NumPy array of rendered image data.
    """
    # Render to Blender's internal buffer
    with suppress_blender_logs():
        bpy.ops.render.render(write_still=False)

    # ORIG (doesn't work)
    # Get rendered image from Blender
    render_result = bpy.context.scene.render
    width = render_result.resolution_x
    height = render_result.resolution_y

    # Extract pixel data
    pixels = bpy.data.images["Render Result"].pixels[:]

    # Convert to NumPy array (RGBA format)
    image_array = np.array(pixels).reshape((height, width, 4))

    # # ALT (doesn't work)
    # # Access pixels from the Compositor Viewer node image
    # # NOTE: This requires setting up a 'Viewer' terminal output node.
    # viewer_img = bpy.data.images.get("Viewer Node")
    # if viewer_img is None:
    #     raise RuntimeError("Viewer Node image not found.")

    # px = viewer_img.pixels[:]
    # if not px:
    #     raise RuntimeError("Viewer Node pixels are empty.")

    # width = int(viewer_img.size[0])
    # height = int(viewer_img.size[1])
    # if width <= 0 or height <= 0:
    #     raise RuntimeError("Viewer Node reported invalid size (0x0). Check compositor setup and render settings.")

    # image_array = np.array(px).reshape((height, width, 4))

    return image_array


def create_scene_visualization(
    resolution=1024,
    format="jpg",
    filename: str = None,
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
        view: The view to render from. Can be 'top_down', 'isometric', or 'egocentric'.
        background_color: RGBA color for the background.
        show_grid: Whether to show a grid in the visualization.

    Returns:
        Path to the rendered scene visualization file.
    """
    # logger.debug(f"Setting up {view} orthographic render...")

    if not filename:
        filename = "render"

    # Prepare output filepath
    if output_dir is None:
        output_dir = tempfile.gettempdir()

    output_path = get_filename(
        output_dir=output_dir,
        base_name=f"{filename}_{view}",
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
        elif view == "egocentric":
            _setup_egocentric_camera()
        else:
            raise ValueError(
                f"Unsupported view type: {view}. Must be 'top_down', 'isometric', or 'egocentric'."
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

    with SceneSwitcher(scene):
        return create_scene_visualization(**kwargs)


class _ObjectAugmentor:
    """Applies temporary object augmentations for visualization renders."""

    def __init__(self, target_ids: list[str], augmentations: set[str]):
        self.target_ids = target_ids
        self.augmentations = augmentations
        self._target_pairs = self._resolve_targets()
        self._original_pass_indices: dict[str, int] = {}
        self._view_layer_state: bool | None = None
        self._text_objects: list[bpy.types.Object] = []

    @property
    def has_targets(self) -> bool:
        return bool(self._target_pairs)

    def _resolve_targets(self) -> list[tuple[str, bpy.types.Object]]:
        resolved: list[tuple[str, bpy.types.Object]] = []
        seen: set[str] = set()
        for object_id in self.target_ids:
            state = _scene_tracker.get_object_state(object_id)
            if not state:
                continue
            blender_obj = bpy.data.objects.get(state.blender_name)
            if not blender_obj or blender_obj.name in seen:
                continue
            resolved.append((object_id, blender_obj))
            seen.add(blender_obj.name)
        return resolved

    def prepare_highlight(self, view_layer: bpy.types.ViewLayer) -> int | None:
        if "highlight" not in self.augmentations:
            return None

        mesh_objects: list[bpy.types.Object] = []
        for _, obj in self._target_pairs:
            mesh_objects.extend(_collect_mesh_descendants(obj))

        if not mesh_objects:
            return None

        self._view_layer_state = view_layer.use_pass_object_index
        view_layer.use_pass_object_index = True

        for mesh in mesh_objects:
            self._original_pass_indices[mesh.name] = mesh.pass_index
            mesh.pass_index = OBJECT_HIGHLIGHT_PASS_INDEX

        return OBJECT_HIGHLIGHT_PASS_INDEX

    def create_labels(self, camera: bpy.types.Object | None):
        if "show_id" not in self.augmentations or camera is None:
            return

        for object_id, blender_obj in self._target_pairs:
            label_obj = _create_object_label(object_id, blender_obj, camera)
            if label_obj:
                self._text_objects.append(label_obj)

    def update_camera(self, camera: bpy.types.Object | None):
        if camera is None:
            return

        for label in self._text_objects:
            for constraint in label.constraints:
                if constraint.type == "TRACK_TO":
                    constraint.target = camera

    def get_bounds(self) -> tuple[Vector | None, float]:
        mesh_objects: list[bpy.types.Object] = []
        for _, obj in self._target_pairs:
            mesh_objects.extend(_collect_mesh_descendants(obj))

        if mesh_objects:
            bounds = calculate_bounds_for_objects(mesh_objects)
            if bounds:
                min_x, max_x, min_y, max_y, min_z, max_z = bounds
                center = Vector(
                    (
                        (min_x + max_x) / 2,
                        (min_y + max_y) / 2,
                        (min_z + max_z) / 2,
                    )
                )
                radius = max(max_x - min_x, max_y - min_y, max_z - min_z) / 2
                return center, max(radius, 0.5)

        if not self._target_pairs:
            return None, 0.0

        aggregate = Vector((0.0, 0.0, 0.0))
        for _, obj in self._target_pairs:
            aggregate += Vector(obj.matrix_world.translation)
        center = aggregate / len(self._target_pairs)
        return center, 1.0

    def cleanup(self):
        for name, original_index in self._original_pass_indices.items():
            obj = bpy.data.objects.get(name)
            if obj:
                obj.pass_index = original_index

        if self._view_layer_state is not None:
            bpy.context.view_layer.use_pass_object_index = self._view_layer_state

        for label in list(self._text_objects):
            obj = bpy.data.objects.get(label.name)
            if obj:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data and getattr(data, "users", 0) == 0:
                    bpy.data.curves.remove(data)
        self._text_objects.clear()


def _collect_mesh_descendants(root: bpy.types.Object) -> list[bpy.types.Object]:
    meshes: list[bpy.types.Object] = []

    def _traverse(obj: bpy.types.Object):
        if obj.type == "MESH":
            meshes.append(obj)
        for child in obj.children:
            _traverse(child)

    _traverse(root)
    return meshes


def _create_object_label(
    object_id: str, blender_obj: bpy.types.Object, camera: bpy.types.Object
) -> bpy.types.Object | None:
    center, size = _object_center_and_size(blender_obj)
    if center is None:
        return None

    text_curve = bpy.data.curves.new(name=f"ObjectLabelCurve_{object_id}", type="FONT")
    text_curve.body = object_id
    text_curve.align_x = "CENTER"
    text_curve.align_y = "CENTER"
    text_curve.size = max(size * 0.25, 0.35)

    text_obj = bpy.data.objects.new(f"ObjectLabel_{object_id}", text_curve)
    bpy.context.scene.collection.objects.link(text_obj)

    offset_height = max(size * 0.6, 0.5)
    text_obj.location = center + Vector((0.0, 0.0, offset_height))
    text_obj.parent = blender_obj
    text_obj.matrix_parent_inverse = blender_obj.matrix_world.inverted()
    text_obj.show_in_front = True
    text_obj.hide_select = True

    material = _create_unlit_material(
        f"{OBJECT_LABEL_MATERIAL_NAME}_{object_id}", (1.0, 1.0, 1.0, 1.0)
    )
    if text_obj.data.materials:
        text_obj.data.materials[0] = material
    else:
        text_obj.data.materials.append(material)

    constraint = text_obj.constraints.new(type="TRACK_TO")
    constraint.target = camera
    constraint.track_axis = "TRACK_Z"
    constraint.up_axis = "UP_Y"

    return text_obj


def _object_center_and_size(
    blender_obj: bpy.types.Object,
) -> tuple[Vector | None, float]:
    mesh_objects = _collect_mesh_descendants(blender_obj)
    bounds = calculate_bounds_for_objects(mesh_objects) if mesh_objects else None

    if bounds:
        min_x, max_x, min_y, max_y, min_z, max_z = bounds
        center = Vector(
            (
                (min_x + max_x) / 2,
                (min_y + max_y) / 2,
                (min_z + max_z) / 2,
            )
        )
        size = max(max_x - min_x, max_y - min_y, max_z - min_z)
        return center, max(size, 1.0)

    return Vector(blender_obj.matrix_world.translation), 1.0


def _ensure_preview_camera(scene: bpy.types.Scene) -> bpy.types.Object:
    camera = bpy.data.objects.get(OBJECT_PREVIEW_CAMERA_NAME)

    if not camera or camera.type != "CAMERA":
        if camera and camera.type != "CAMERA":
            bpy.data.objects.remove(camera, do_unlink=True)
        with suppress_blender_logs():
            bpy.ops.object.camera_add(location=(0.0, 0.0, 0.0))
        camera = bpy.context.object
        camera.name = OBJECT_PREVIEW_CAMERA_NAME
        # Spawn with initial rotation: +X 90 degrees (XYZ Euler)
        camera.rotation_euler = (math.radians(90.0), 0.0, 0.0)

    if camera.name not in scene.collection.objects:
        scene.collection.objects.link(camera)

    camera.data.type = "PERSP"
    camera.data.lens = 35
    camera.data.clip_start = 0.05
    camera.data.clip_end = 500.0

    return camera


def _position_preview_camera(
    camera: bpy.types.Object, center: Vector, radius: float, angle_degrees: float
):
    distance = max(radius * 2.2, 2.0)
    height = max(center.z + radius * 0.6, center.z + 0.5)
    angle = math.radians(angle_degrees)

    camera.location = Vector(
        (
            center.x + math.cos(angle) * distance,
            center.y + math.sin(angle) * distance,
            height,
        )
    )

    # NOTE: direction handling is offloaded to `_apply_camera_track()`.
    # If no tracking constraints exist, raise a warning
    if not any(c.type == "LOCKED_TRACK" for c in getattr(camera, "constraints", [])):
        logger.warning("Direction constraint not found for preview camera")


def _render_preview_rotation(
    scene: bpy.types.Scene,
    augmentor: _ObjectAugmentor,
    output_path: Path,
    angles: list[float] = [0, 90, 180, 270],
    image_format: str = "jpg",
) -> Path | None:
    """Render four rotational previews to files using the final renderer.

    Saves individual frames into './tmp' as '<stem>_rot_XXX.<ext>' and returns
    the path of the last rendered frame.
    """
    center, radius = augmentor.get_bounds()
    if center is None or radius <= 0:
        return None

    original_camera = scene.camera
    preview_camera = _ensure_preview_camera(scene)

    saved_paths: list[Path] = []

    scene.camera = preview_camera
    augmentor.update_camera(preview_camera)

    # Track the target object if exists
    if augmentor.has_targets:
        first_target = augmentor._target_pairs[0][1]
        _apply_camera_track(preview_camera, first_target)

    for angle in angles:
        _position_preview_camera(preview_camera, center, radius, angle)
        angle_path = f"{output_path}_rot_{angle:03d}.{image_format.lower()}"
        saved_paths.append(render_to_file(angle_path))

    # Restore camera to original
    scene.camera = original_camera
    augmentor.update_camera(original_camera)

    compose_image_grid([np.array(Image.open(path)) for path in saved_paths], output_path)
    logger.debug(f"Composed rotation preview render -> {output_path} (frames: {len(saved_paths)})")

    return output_path


def create_object_visualization(
    resolution=1024,
    format="jpg",
    filename: str = None,
    output_dir: str = None,
    view: str = "top_down",
    background_color: tuple[float, float, float, float] = BACKGROUND_COLOR,
    show_grid: bool = False,
    augmentations: list[str] | None = None,
    target_objects: list[str] | None = None,
    scene: str | None = None,
) -> Path:
    """Render the scene with object-focused augmentations."""

    augmentations = set(augmentations or [])
    target_objects = target_objects or []

    if not filename:
        filename = "object_render"

    if output_dir is None:
        output_dir = tempfile.gettempdir()

    output_path = get_filename(
        output_dir=output_dir,
        base_name=f"{filename}_{view}",
        extension=format.lower(),
        strategy="increment",
    )

    with SceneSwitcher(scene):
        # Resolve targets early so egocentric camera can track them
        augmentor = _ObjectAugmentor(target_objects, augmentations)
        track_target_obj = (
            augmentor._target_pairs[0][1]
            if (view == "egocentric" and augmentor.has_targets)
            else None
        )

        with suppress_blender_logs():
            # _configure_render_settings()  # OG
            _configure_render_settings(engine="CYCLES")  # ALT
            _configure_output_image(format, resolution)

            if view == "top_down":
                _setup_top_down_camera()
            elif view == "isometric":
                _setup_isometric_camera()
            elif view == "egocentric":
                _setup_egocentric_camera(track_target=track_target_obj)
            else:
                raise ValueError(
                    f"Unsupported view type: {view}. Must be 'top_down', 'isometric', or 'egocentric'."
                )

            _setup_lighting(energy=0.5)

            if show_grid:
                _create_grid()

        scene_obj = bpy.context.scene
        highlight_index = augmentor.prepare_highlight(bpy.context.view_layer)

        with suppress_blender_logs():
            setup_lighting_foundation(scene_obj, background_color=background_color)
            setup_post_processing(scene_obj, highlight_pass_index=highlight_index)

        augmentor.create_labels(scene_obj.camera)

        render_result: Path | None = None

        try:
            if "preview_rotation" in augmentations and augmentor.has_targets:
                preview_path = _render_preview_rotation(
                    scene_obj, augmentor, output_path, image_format=format
                )
                if preview_path:
                    render_result = Path(preview_path)
            if render_result is None:
                render_result = render_to_file(output_path)
        finally:
            augmentor.cleanup()

    return render_result


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


def setup_post_processing(
    scene: bpy.types.Scene,
    highlight_pass_index: int | None = None,
    highlight_color: tuple[float, float, float, float] = (1.0, 0.65, 0.1, 1.0),
    enable_glare: bool = True,
):
    """Configures color management and compositor nodes for the final look.

    Uses an ID Mask + Blur + Subtract + Multiply + Glare chain for object highlights,
    avoiding unsupported Dilate/Erode modes across Blender versions.
    """
    print("Setting up post-processing...")
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"

    # Enable object index pass if highlighting
    view_layer = bpy.context.view_layer
    view_layer.use_pass_object_index = highlight_pass_index is not None
    view_layer.update()

    # Ensure compositing is enabled
    scene.render.use_compositing = True
    # Enable compositor and reset nodes
    scene.use_nodes = True
    tree = scene.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()

    # Base nodes
    rlayers = nodes.new("CompositorNodeRLayers")
    # # Route RLayers to the active scene + view layer to ensure IndexOB is valid
    # try:
    #     rlayers.scene = scene
    # except Exception:
    #     pass
    # try:
    #     rlayers.layer = bpy.context.view_layer.name
    # except Exception:
    #     pass
    comp = nodes.new("CompositorNodeComposite")

    # Optional base glare on the full image
    base_socket = rlayers.outputs["Image"]
    if enable_glare:
        base_glare = nodes.new("CompositorNodeGlare")
        base_glare.glare_type = "FOG_GLOW"
        base_glare.threshold = 1.5
        base_glare.size = 4
        links.new(rlayers.outputs["Image"], base_glare.inputs["Image"])
        base_socket = base_glare.outputs["Image"]

    final_socket = base_socket

    # Highlight chain if requested
    if highlight_pass_index is not None:
        id_mask = nodes.new("CompositorNodeIDMask")
        id_mask.index = int(highlight_pass_index)
        # Slightly cleaner edges
        try:
            id_mask.use_antialiasing = True
        except Exception:
            pass

        blur = nodes.new("CompositorNodeBlur")
        blur.filter_type = "GAUSS"
        blur.size_x = 25
        blur.size_y = 25
        blur.use_relative = False

        sub = nodes.new("CompositorNodeMixRGB")
        sub.blend_type = "SUBTRACT"
        sub.inputs[0].default_value = 1.0

        color_mix = nodes.new("CompositorNodeMixRGB")
        color_mix.blend_type = "MULTIPLY"
        color_mix.inputs[0].default_value = 1.0
        # Tint with provided highlight color
        color_mix.inputs[2].default_value = highlight_color

        glow = nodes.new("CompositorNodeGlare")
        glow.glare_type = "FOG_GLOW"
        glow.quality = "HIGH"
        glow.size = 9
        glow.mix = 0.0

        add_mix = nodes.new("CompositorNodeMixRGB")
        add_mix.blend_type = "ADD"
        add_mix.inputs[0].default_value = 1.0

        # Wire up highlight chain
        links.new(rlayers.outputs["IndexOB"], id_mask.inputs["ID value"])
        links.new(id_mask.outputs["Alpha"], blur.inputs["Image"])
        links.new(blur.outputs["Image"], sub.inputs[1])
        links.new(id_mask.outputs["Alpha"], sub.inputs[2])
        links.new(sub.outputs["Image"], color_mix.inputs[1])
        links.new(color_mix.outputs["Image"], glow.inputs["Image"])

        # Combine glow with base image
        links.new(base_socket, add_mix.inputs[1])
        links.new(glow.outputs["Image"], add_mix.inputs[2])
        final_socket = add_mix.outputs["Image"]

    # To Composite
    links.new(final_socket, comp.inputs["Image"])

    # Also feed a Viewer node so pixel data can be read reliably
    try:
        viewer = nodes.new("CompositorNodeViewer")
        # Use same final image (post effects/highlights) for Viewer output
        links.new(final_socket, viewer.inputs["Image"])
    except Exception:
        # If nodes cannot be created (unlikely), continue without viewer
        pass


def create_room_walls(
    rooms: list[Room],
    wall_height: float = 2.7,
    wall_thickness: float = 0.05,
    door_cutouts: bool = True,
    window_cutouts: bool = True,
    render_doors: bool = False,
    render_windows: bool = False,
    window_height_bottom: float = DEFAULT_WINDOW_HEIGHT_BOTTOM,
    window_height_top: float = DEFAULT_WINDOW_HEIGHT_TOP,
    keep_cutters_visible: bool = False,
    translucent: bool = False,
    debug_save_steps: bool = True,
    debug_output_dir: Optional[
        str
    ] = "/home/jkim3191/NavGoProject/GitHub/test_output/debug_wall_creation",
):
    """Create walls for each room individually (excluding windows and exterior doors).

    Args:
        rooms: List of Room objects with boundary and category data
        wall_height: Height of walls in meters (default: 2.7m)
        wall_thickness: Thickness of walls in meters (default: 0.15m)
        door_cutouts: Whether to create cutouts in walls for doors (default: True)
        window_cutouts: Whether to create cutouts in walls for windows (default: True)
        render_doors: Whether to create actual door objects (default: False)
        render_windows: Whether to create actual window objects (default: False)
        window_height_bottom: Bottom height of window cutouts (default: DEFAULT_WINDOW_HEIGHT_BOTTOM)
        window_height_top: Top height of window cutouts (default: DEFAULT_WINDOW_HEIGHT_TOP)
        keep_cutters_visible: If True, keep cutter objects visible for debugging (default: False)
        translucent: If True, assign a translucent wall material (default: False)
        debug_save_steps: If True, save .blend files at each step for debugging (default: False)
        debug_output_dir: Directory to save debug .blend files (default: None, uses temp dir)

    Returns:
        Number of walls created
    """
    walls_created = 0

    # Setup debug saving
    if debug_save_steps:
        if debug_output_dir is None:
            debug_output_dir = tempfile.gettempdir()
        debug_output_path = Path(debug_output_dir).resolve()
        debug_output_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"🔍 Debug mode enabled: saving wall creation steps to {debug_output_path}")

    window_cutout_polygons: list[tuple[str, list[tuple[float, float]]]] = []

    exterior_door_cutout_polygons: list[tuple[str, list[tuple[float, float]]]] = []

    interior_door_polygons: list[tuple[str, list[tuple[float, float]]]] = []

    # Collect all room boundaries for window positioning
    all_room_boundaries = []
    all_room_polygons = []
    for room in rooms:
        r_category = room.get("category")
        r_boundary = room.get("boundary")
        if r_category not in ["door", "window"] and r_boundary and len(r_boundary) >= 3:
            try:
                boundary_points = []
                for p in r_boundary:
                    if hasattr(p, "x"):
                        boundary_points.append((p.x, p.y))
                    else:
                        boundary_points.append((p["x"], p["y"]))
                room_polygon = Polygon(boundary_points)
                if room_polygon.is_valid and not room_polygon.is_empty:
                    all_room_polygons.append(room_polygon)
                    all_room_boundaries.append(boundary_points)
            except Exception:
                continue

    for r in rooms:
        for s in r.get("structure") or []:
            # s can be pydantic Structure or dict
            s_type = s.get("type")
            s_id = s.get("id")
            s_boundary = s.get("boundary")
            if not s_boundary or len(s_boundary) < 3:
                continue
            boundary_xy: list[tuple[float, float]] = []
            for p in s_boundary:
                if hasattr(p, "x"):
                    boundary_xy.append((p.x, p.y))
                else:
                    boundary_xy.append((p["x"], p["y"]))

            if window_cutouts and s_type == "window":
                window_cutout_polygons.append((str(s_id), boundary_xy))
            elif door_cutouts and s_type == "door":
                try:
                    door_polygon = Polygon(boundary_xy)
                    if door_polygon.is_valid and not door_polygon.is_empty:
                        door_type = classify_door_type(door_polygon, all_room_polygons)
                        is_interior = door_type == "interior"
                    else:
                        is_interior = False
                except Exception:
                    is_interior = False

                if not is_interior:
                    exterior_door_cutout_polygons.append((str(s_id), boundary_xy))
                    logger.debug(f"Door {s_id}: identified as exterior door")
                else:
                    interior_door_polygons.append((str(s_id), boundary_xy))
                    logger.debug(f"Door {s_id}: identified as interior door")

    # Detect adjacent walls to skip
    adjacent_segments = _find_adjacent_wall_segments_from_centers_to_edges(rooms, threshold=0.025)

    for room_idx, room in enumerate(rooms):
        r_category = room.get("category")
        if r_category == "window":
            continue

        if r_category == "door":
            continue

        r_boundary = room.get("boundary")
        if not r_boundary or len(r_boundary) < 3:
            continue

        # Support Vector2 objects or dict-like points
        boundary_points = []
        for p in r_boundary:
            if hasattr(p, "x"):
                boundary_points.append((p.x, p.y))
            else:
                boundary_points.append((p["x"], p["y"]))

        room_id = getattr(room, "id", None)
        if room_id is None and isinstance(room, dict):
            room_id = room.get("id", "unknown")

        mesh = bpy.data.meshes.new(f"Wall_{room_id}")
        obj = bpy.data.objects.new(f"Wall_{room_id}", mesh)
        bpy.context.collection.objects.link(obj)

        bm = bmesh.new()

        bottom_verts = []
        for x, y in boundary_points:
            v = bm.verts.new((x, y, 0))
            bottom_verts.append(v)

        top_verts = []
        for x, y in boundary_points:
            v = bm.verts.new((x, y, wall_height))
            top_verts.append(v)

        num_verts = len(bottom_verts)
        for i in range(num_verts):
            next_i = (i + 1) % num_verts

            # Skip this edge if it's adjacent to another room
            edge_key = (room_idx, i)
            if edge_key in adjacent_segments:
                logger.debug(
                    f"Skipping wall edge {i} for room {room_id} (adjacent to another room)"
                )
                continue

            face = bm.faces.new(
                [bottom_verts[i], bottom_verts[next_i], top_verts[next_i], top_verts[i]]
            )
            face.normal_update()

        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

        solidify = obj.modifiers.new(name="Solidify", type="SOLIDIFY")
        solidify.thickness = wall_thickness
        solidify.offset = -1

        bpy.context.view_layer.objects.active = obj
        with suppress_blender_logs():
            bpy.ops.object.modifier_apply(modifier=solidify.name)

        # Debug save: after wall creation, before cutouts
        if debug_save_steps:
            step_file = debug_output_path / f"step1_wall_created_{room_id}.blend"
            save_scene(str(step_file), exclude_grid=True)
            logger.debug(f"Saved: {step_file}")

        if translucent:
            # Don't create material if it exists already
            mat_name = "TranslucentWallMaterial"
            if mat_name in bpy.data.materials:
                wall_material = bpy.data.materials[mat_name]
            else:
                wall_material = create_translucent_material(name=mat_name)

            # Prevent duplicate material assignment
            if not any(m and m.name == mat_name for m in obj.data.materials):
                obj.data.materials.append(wall_material)

        room_polygon = Polygon(boundary_points)

        if window_cutouts and window_cutout_polygons:
            for idx, (cutout_id, cutout_boundary) in enumerate(window_cutout_polygons):
                if not cutout_boundary:
                    continue

                # Only apply window cutout if it intersects with this room's boundary
                if room_polygon:
                    try:
                        cutout_polygon = Polygon(cutout_boundary)
                        # Check if cutout intersects with room or is very close (within 0.1m)
                        if cutout_polygon.is_valid and (
                            cutout_polygon.intersects(room_polygon)
                            or room_polygon.distance(cutout_polygon) < 0.1
                        ):
                            _create_window_cutout(
                                wall_obj=obj,
                                apt_id=str(cutout_id),
                                window_idx=idx,
                                window_boundary=cutout_boundary,
                                z_bottom=window_height_bottom,
                                z_top=window_height_top,
                                keep_cutter_visible=keep_cutters_visible,
                            )

                            # Create the actual window object at this boundary if rendering is enabled
                            if render_windows:
                                window_result = create_window_from_boundary(
                                    window_boundary=cutout_boundary,
                                    window_id=str(cutout_id),
                                    z_position=window_height_bottom,
                                    window_height_bottom=window_height_bottom,
                                    window_height_top=window_height_top,
                                    room_boundaries=all_room_boundaries,
                                    randomize_type=True,
                                    randomize_material=True,
                                    randomize_colour=False,
                                    colour=(0.8, 0.9, 1.0, 1.0),  # Light blue window
                                )

                    except Exception:
                        continue
                else:
                    _create_window_cutout(
                        wall_obj=obj,
                        apt_id=str(cutout_id),
                        window_idx=idx,
                        window_boundary=cutout_boundary,
                        z_bottom=window_height_bottom,
                        z_top=window_height_top,
                        keep_cutter_visible=keep_cutters_visible,
                    )

                    if render_windows:
                        window_result = create_window_from_boundary(
                            window_boundary=cutout_boundary,
                            window_id=str(cutout_id),
                            z_position=window_height_bottom,
                            window_height_bottom=window_height_bottom,
                            window_height_top=window_height_top,
                            room_boundaries=all_room_boundaries,
                            randomize_type=True,
                            randomize_material=True,
                            randomize_colour=False,
                            colour=(0.8, 0.9, 1.0, 1.0),  # Light blue window
                        )

                        if window_result:
                            logger.debug(
                                f"Successfully created window object: {window_result.get('object')}"
                            )

        # Debug save: after window cutouts
        if debug_save_steps and window_cutouts:
            step_file = debug_output_path / f"step2_windows_applied_{room_id}.blend"
            save_scene(str(step_file), exclude_grid=True)
            logger.debug(f"Saved: {step_file}")

        if door_cutouts and interior_door_polygons:
            for idx, (door_id, door_boundary) in enumerate(interior_door_polygons):
                if not door_boundary:
                    continue

                if room_polygon:
                    try:
                        door_polygon = Polygon(door_boundary)
                        # Check if door is very close (within 0.1m)
                        if door_polygon.is_valid and room_polygon.distance(door_polygon) < 0.1:
                            # Create the cutout in the wall
                            _create_interior_door_cutout(
                                wall_obj=obj,
                                apt_id=str(door_id),
                                door_idx=idx,
                                door_boundary=door_boundary,
                                z_bottom=0.0,
                                z_top=DEFAULT_DOOR_HEIGHT,
                                keep_cutter_visible=keep_cutters_visible,
                            )

                            door_boundary_dicts = [{"x": x, "y": y} for x, y in door_boundary]
                            door_floor_result = _create_floor_mesh(
                                boundary=door_boundary_dicts,
                                room_id=f"interior_door_{door_id}",
                                floor_thickness_m=0.05,  # Thinner than room floors
                                origin="center",
                            )
                            logger.debug(
                                f"Created floor for interior door {door_id}: {door_floor_result['status']}"
                            )

                            # Debug save: after door cutout and floor creation
                            if debug_save_steps:
                                step_file = (
                                    debug_output_path
                                    / f"step3_door_{door_id}_cutout_floor_{room_id}.blend"
                                )
                                save_scene(str(step_file), exclude_grid=True)
                                logger.debug(f"Saved: {step_file}")

                            if render_doors:
                                door_result = create_door_from_boundary(
                                    door_boundary=door_boundary,
                                    door_id=str(door_id),
                                    z_position=0.0,
                                    door_height=DEFAULT_DOOR_HEIGHT,
                                    randomize_type=True,
                                    randomize_handle=True,
                                    randomize_material=True,
                                    randomize_color=False,
                                    paint_color=(1.0, 1.0, 1.0, 1.0),  # White door
                                )

                                if door_result:
                                    logger.debug(
                                        f"Successfully created door object: {door_result.get('object')}"
                                    )
                            else:
                                logger.debug(
                                    f"Skipping door object creation for door {door_id} (render_doors=False)"
                                )
                    except Exception:
                        # Skip this door if polygon creation fails
                        continue

        # Debug save: final state after all cutouts and objects
        if debug_save_steps:
            step_file = debug_output_path / f"step4_final_{room_id}.blend"
            save_scene(str(step_file), exclude_grid=True)
            logger.debug(f"Saved: {step_file}")

        walls_created += 1

    # Debug save: all walls complete
    if debug_save_steps:
        final_file = debug_output_path / "step5_all_walls_complete.blend"
        save_scene(str(final_file), exclude_grid=True)
        logger.debug(f"Saved final: {final_file}")

    return walls_created


def apply_floor_material(
    material_id: str,
    floor_object_name: str,
    uv_scale: Optional[float] = None,
    boundary: Optional[list] = None,
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

    if boundary is not None and uv_scale is None:
        boundary_tuples = []
        for point in boundary:
            if hasattr(point, "x"):
                boundary_tuples.append((point.x, point.y))
            else:
                boundary_tuples.append((point["x"], point["y"]))

        bounds = calculate_bounds_2d(boundary_tuples)
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


def apply_wall_material(
    material_id: str,
    wall_object_name: str,
    uv_scale: float = 1.0,
) -> bool:
    """
    Apply a material to a wall object in Blender.

    Mirrors apply_floor_material but targets the wall mesh ("Wall_<room_id>").
    Performs a simple UV unwrap for reasonable tiling before applying.

    Args:
        material_id: Material UID from Graphics-DB
        wall_object_name: Name of the wall object in Blender (e.g., "Wall_room-01")
        uv_scale: UV scale for texture tiling

    Returns:
        True if successful, False otherwise
    """

    try:
        # Ensure the target object exists
        obj = bpy.data.objects.get(wall_object_name)
        if not obj:
            logger.debug(f"Wall object not found: {wall_object_name}")
            return False

        # Create or refresh UVs for the wall mesh to ensure sane tiling
        try:
            with suppress_blender_logs():
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_all(action="SELECT")
                # Smart project works well for vertical quads
                bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.001)
                bpy.ops.object.mode_set(mode="OBJECT")
        except Exception as uv_err:
            logger.debug(f"UV unwrap failed for {wall_object_name}: {uv_err}")

        # Resolve material texture via database
        material_db = MaterialDatabase()
        texture_path = material_db.download_texture(material_id)
        if not texture_path:
            logger.debug(f"Failed to download texture for wall material: {material_id}")
            return False

        # Reuse the generic texture applicator (works for any mesh)
        material_name = f"Mat_{Path(texture_path).stem}_{wall_object_name}"
        success = texture_floor_mesh(
            floor_object_name=wall_object_name,
            texture_path=texture_path,
            material_name=material_name,
            uv_scale=uv_scale,
        )

        if success:
            logger.debug(f"Applied wall material {material_id} to {wall_object_name}")
        else:
            logger.debug(f"Failed to apply wall material to {wall_object_name}")

        return success
    except Exception as e:
        logger.debug(f"Error applying wall material to {wall_object_name}: {e}")
        return False
