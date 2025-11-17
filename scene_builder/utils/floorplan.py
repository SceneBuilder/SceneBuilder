"""Floorplan-level transforms and orientation utilities."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import bpy
import matplotlib.pyplot as plt
import numpy as np
from mathutils import Vector
from PIL import Image
from shapely import affinity
from shapely.geometry import Point, Polygon

from scene_builder.definition.scene import Room, Vector2
from scene_builder.utils.geometry import are_boundaries_close


def classify_door_type(
    door_polygon: Polygon,
    all_entity_polygons: list[Polygon],
    proximity_threshold: float = 0.01,
) -> str:
    """
    Classify a door as interior or exterior based on proximity to other entities.

    A door is interior if more than 1 entity is within the proximity threshold;
    otherwise it's exterior (0 or 1 entity nearby).

    Args:
        door_polygon: The door boundary as a shapely Polygon
        all_entity_polygons: List of all other entity polygons (excluding doors)
        proximity_threshold: Distance threshold in meters (default: 0.01m = 1cm)

    Returns:
        "interior" if more than 1 entity is within threshold distance
        "exterior" if 0 or 1 entity is within threshold distance
    """
    if not door_polygon or door_polygon.is_empty or not door_polygon.is_valid:
        return "exterior"

    if not all_entity_polygons:
        return "exterior"

    # Count entities within proximity threshold
    nearby_count = 0
    for entity_polygon in all_entity_polygons:
        if not entity_polygon or entity_polygon.is_empty or not entity_polygon.is_valid:
            continue

        try:
            distance = door_polygon.distance(entity_polygon)
            if distance <= proximity_threshold:
                nearby_count += 1
        except Exception:
            # Skip if distance calculation fails
            continue

    # Classify: more than 1 nearby entity = interior, otherwise exterior
    if nearby_count > 1:
        return "interior"
    else:
        return "exterior"

################## debug temporarily ##################
# this is centers to edges, not edges to edges
def _find_adjacent_wall_segments_from_centers_to_edges(rooms: list[Room], threshold: float = 0.025):
    """Find segments of room walls that are adjacent to other room walls.
    
    Args:
        rooms: List of Room objects or dicts with boundary data
        threshold: Distance threshold for considering walls adjacent (in meters)
    
    Returns:
        Dictionary mapping (room_idx, edge_idx) to list of touching segments [(start, end), ...]
    """
    from shapely.geometry import LineString
    
    adjacent_segments = {}
    
    for i, room1 in enumerate(rooms):

        r1_boundary = room1.get("boundary") if isinstance(room1, dict) else getattr(room1, "boundary", None)
        if not r1_boundary or len(r1_boundary) < 3:
            continue
            
        for edge_idx in range(len(r1_boundary)):
            p1 = r1_boundary[edge_idx]
            p2 = r1_boundary[(edge_idx + 1) % len(r1_boundary)]
            
            # Convert to Vector2 if dict
            if isinstance(p1, dict):
                p1 = Vector2(x=p1["x"], y=p1["y"])
            if isinstance(p2, dict):
                p2 = Vector2(x=p2["x"], y=p2["y"])
            
            touching_portions = []
            
            # Compare with all other rooms
            for j, room2 in enumerate(rooms):
                if i == j:  # Skip same room
                    continue
                
                r2_boundary = room2.get("boundary") if isinstance(room2, dict) else getattr(room2, "boundary", None)
                if not r2_boundary or len(r2_boundary) < 3:
                    continue
                
                # Convert to Vector2 if needed for are_boundaries_close
                r1_boundary_vec2 = [Vector2(x=v["x"], y=v["y"]) if isinstance(v, dict) else v for v in r1_boundary]
                r2_boundary_vec2 = [Vector2(x=v["x"], y=v["y"]) if isinstance(v, dict) else v for v in r2_boundary]
                if not are_boundaries_close(r1_boundary_vec2, r2_boundary_vec2, threshold):
                    continue
                
                for edge2_idx in range(len(r2_boundary)):
                    q1 = r2_boundary[edge2_idx]
                    q2 = r2_boundary[(edge2_idx + 1) % len(r2_boundary)]
                    
                    # Convert to Vector2 if dict
                    if isinstance(q1, dict):
                        q1 = Vector2(x=q1["x"], y=q1["y"])
                    if isinstance(q2, dict):
                        q2 = Vector2(x=q2["x"], y=q2["y"])
                    
                    edge2 = LineString([(q1.x, q1.y), (q2.x, q2.y)])
                    
                    # Calculate center point of edge1
                    center1_x = (p1.x + p2.x) / 2
                    center1_y = (p1.y + p2.y) / 2
                    center1_point = Point(center1_x, center1_y)
                    
                    # Check if edge1's center is close to edge2
                    distance = center1_point.distance(edge2)
                    
                    if distance <= threshold:
                        # edge1's center is close to edge2 - mark entire edge1 as touching
                        touching_portions.append((p1, p2))
                        break  # No need to check other edges of room2
            
            if touching_portions:
                adjacent_segments[(i, edge_idx)] = touching_portions
    
    return adjacent_segments


def plot_floor_plan(
    rooms: list[Room], 
    output_path: str = "floor_plan.png",
    show_doors: bool = False,
    show_windows: bool = False,
    show_adjacent_walls: bool = True,
    adjacency_threshold: float = 0.05
):
    """Plot floor plan showing room boundaries with adjacent wall segments in green.
    
    Note: Adjacent wall detection only considers room boundaries, NOT door/window structures.
    
    Args:
        rooms: List of Room objects to plot
        output_path: Path to save the plot image
        show_doors: If True, show interior doors in red
        show_windows: If True, show windows in yellow
        show_adjacent_walls: If True, show adjacent wall segments in green
        adjacency_threshold: Distance threshold for considering walls adjacent (default: 0.05m)
    """
    fig, ax = plt.subplots(figsize=(12, 12))
    
    # Find adjacent wall segments if enabled
    adjacent_segments = []
    if show_adjacent_walls:
        adjacent_segments = _find_adjacent_wall_segments_from_centers_to_edges(rooms, adjacency_threshold)
    
    # Plot rooms
    for room_idx, room in enumerate(rooms):
        if room.boundary and len(room.boundary) >= 3:
            # Plot each edge segment
            for i in range(len(room.boundary)):
                p1 = room.boundary[i]
                p2 = room.boundary[(i + 1) % len(room.boundary)]
                
                # Check if this segment has adjacent portions
                edge_key = (room_idx, i)
                if edge_key in adjacent_segments:
                    # This edge has adjacent portions - plot them separately
                    touching_portions = adjacent_segments[edge_key]
                    
                    # Plot the entire edge first in blue
                    ax.plot([p1.x, p2.x], [p1.y, p2.y], 'b-', linewidth=1)
                    
                    # Then overlay green for touching portions
                    for seg_start, seg_end in touching_portions:
                        ax.plot([seg_start.x, seg_end.x], [seg_start.y, seg_end.y], 
                               'g-', linewidth=2, zorder=10)
                else:
                    # No adjacent walls, just plot in blue
                    ax.plot([p1.x, p2.x], [p1.y, p2.y], 'b-', linewidth=1)
            
            # Fill the room
            x = [v.x for v in room.boundary] + [room.boundary[0].x]
            y = [v.y for v in room.boundary] + [room.boundary[0].y]
            ax.fill(x, y, color='lightblue', alpha=0.3)
    
    # Plot interior doors and windows if enabled
    if show_doors or show_windows:
        # Build list of all room polygons for door classification (only if needed)
        all_room_polygons = []
        if show_doors:
            for room in rooms:
                if room.boundary and len(room.boundary) >= 3:
                    try:
                        boundary_xy = [(v.x, v.y) for v in room.boundary]
                        room_polygon = Polygon(boundary_xy)
                        if room_polygon.is_valid and not room_polygon.is_empty:
                            all_room_polygons.append(room_polygon)
                    except Exception:
                        continue
        
        # Plot interior doors and windows
        for room in rooms:
            if room.structure:
                for struct in room.structure:
                    if struct.boundary and len(struct.boundary) >= 3:
                        x = [v.x for v in struct.boundary] + [struct.boundary[0].x]
                        y = [v.y for v in struct.boundary] + [struct.boundary[0].y]
                        
                        # Only plot interior doors (red) if enabled
                        if show_doors and struct.type == "door":
                            try:
                                boundary_xy = [(v.x, v.y) for v in struct.boundary]
                                door_polygon = Polygon(boundary_xy)
                                if door_polygon.is_valid and not door_polygon.is_empty:
                                    door_type = classify_door_type(door_polygon, all_room_polygons)
                                    if door_type == "interior":
                                        ax.plot(x, y, color='red', linewidth=2)
                                        ax.fill(x, y, color='red', alpha=0.7)
                            except Exception:
                                continue
                        # Plot all windows (yellow) if enabled
                        elif show_windows and struct.type == "window":
                            ax.plot(x, y, color='yellow', linewidth=2)
                            ax.fill(x, y, color='yellow', alpha=0.7)
    
    ax.set_aspect('equal')
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved floor plan to {output_path}")

################## debug temporarily ##################
def find_nearest_wall_point(window_center: Vector2, room_boundaries: list) -> Optional[Vector2]:
    """Find the nearest point on any room boundary (wall) from window center.
    
    Args:
        window_center: Center point of the window
        room_boundaries: List of room boundary polygons (each as list of Vector2 or tuples)
        
    Returns:
        Nearest point on wall as Vector2, or None if no boundaries found
    """
    nearest_point = None
    min_distance = float('inf')
    
    for boundary in room_boundaries:
        if not boundary or len(boundary) < 3:
            continue
            
        # Check each edge of the boundary
        for i in range(len(boundary)):
            # Handle both Vector2 and tuple formats
            p1 = boundary[i]
            p2 = boundary[(i + 1) % len(boundary)]
            
            if isinstance(p1, (list, tuple)):
                p1 = Vector2(x=p1[0], y=p1[1])
            if isinstance(p2, (list, tuple)):
                p2 = Vector2(x=p2[0], y=p2[1])
            
            # Calculate closest point on this edge
            dx = p2.x - p1.x
            dy = p2.y - p1.y
            
            if dx == 0 and dy == 0:
                closest = p1
            else:
                t = ((window_center.x - p1.x) * dx + (window_center.y - p1.y) * dy) / (dx * dx + dy * dy)
                t = max(0, min(1, t))
                closest = Vector2(x=p1.x + t * dx, y=p1.y + t * dy)
            
            distance = math.sqrt((closest.x - window_center.x)**2 + (closest.y - window_center.y)**2)
            
            if distance < min_distance:
                min_distance = distance
                nearest_point = closest
    
    return nearest_point

def scale_boundary_for_cutout(
    boundary: list,
    scale_short_factor: float = 2.00,
    scale_short_axis: bool = True,
    scale_long_axis: bool = True,
    scale_long_factor: float = 0.98,
    debug: bool = False,
    debug_prefix: str = "window",
    debug_id: str = "",
) -> list:
    """
    Scale a boundary polygon for cutout operations (windows, doors, etc.).

    Uses anisotropic scaling along the short axis (orthogonal to dominant direction)
    and/or longer axis for better cutout geometry. Pure geometry operation - no Blender dependencies.

    Args:
        boundary: List of (x, y) tuples defining polygon
        scale_short_factor: Factor to scale the shorter axis (default: 2.00)
        scale_short_axis: If True, scale along axis orthogonal to dominant direction (default: True)
        scale_long_axis: If True, scale along the dominant (longer) direction (default: True)
        scale_long_factor: Factor to scale the longer axis (default: 0.99)
        debug: If True, saves debug visualization (default: False)
        debug_prefix: Prefix for debug filename (e.g., "window" or "door")
        debug_id: ID to include in debug filename (e.g., apt_id_index)

    Returns:
        List of (x, y) tuples of scaled boundary
    """
    try:
        boundary_poly = Polygon(boundary)
        rotation_angle = get_dominant_angle([boundary_poly], strategy="complex_sum")
        centroid = boundary_poly.centroid
        centroid_coords = (centroid.x, centroid.y)

        aligned_poly = affinity.rotate(
            boundary_poly, rotation_angle, origin=centroid_coords, use_radians=False
        )
        minx, miny, maxx, maxy = aligned_poly.bounds
        width = maxx - minx
        height = maxy - miny
        is_width_dominant = width >= height

        scaled_poly = boundary_poly
        scale_axis_vector = np.array([0.0, 0.0])
        arrow_points = None
        boundary_centroid = np.array(centroid_coords)

        if scale_short_axis and width > 0 and height > 0:
            # Start with base factors
            if is_width_dominant:
                x_factor = scale_long_factor  # Width is longer - always scale it
                y_factor = scale_short_factor  # Height is shorter
            else:
                x_factor = scale_short_factor  # Width is shorter
                y_factor = scale_long_factor  # Height is longer - always scale it

            scaled_aligned_poly = affinity.scale(
                aligned_poly, xfact=x_factor, yfact=y_factor, origin=centroid_coords
            )
            scaled_poly = affinity.rotate(
                scaled_aligned_poly, -rotation_angle, origin=centroid_coords, use_radians=False
            )

            theta = np.radians(-rotation_angle)
            rotation_matrix = np.array(
                [[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]]
            )
            scale_axis_local = np.array([0.0, 1.0]) if is_width_dominant else np.array([1.0, 0.0])
            scale_axis_vector = rotation_matrix @ scale_axis_local

            if np.linalg.norm(scale_axis_vector) > 0:
                minor_extent = height if is_width_dominant else width
                direction_length = 0.5 * max(minor_extent, 1.0)
                direction = scale_axis_vector / np.linalg.norm(scale_axis_vector)
                arrow_points = np.vstack(
                    [
                        boundary_centroid - direction * direction_length,
                        boundary_centroid + direction * direction_length,
                    ]
                )
        elif scale_long_axis and width > 0 and height > 0:
            # Only scale long axis, not short axis
            if is_width_dominant:
                x_factor = scale_long_factor  # Width is longer
                y_factor = 1.0  # Height is shorter
            else:
                x_factor = 1.0  # Width is shorter
                y_factor = scale_long_factor  # Height is longer

            scaled_aligned_poly = affinity.scale(
                aligned_poly, xfact=x_factor, yfact=y_factor, origin=centroid_coords
            )
            scaled_poly = affinity.rotate(
                scaled_aligned_poly, -rotation_angle, origin=centroid_coords, use_radians=False
            )
        elif not scale_short_axis and not scale_long_axis:
            # Uniform scaling if neither axis-specific scaling is requested
            scaled_poly = affinity.scale(
                boundary_poly, xfact=scale_short_factor, yfact=scale_short_factor, origin=centroid_coords
            )

        # TEMP: visualization for debugging orthogonal scaling
        if debug:
            x, y = boundary_poly.exterior.xy
            sx, sy = scaled_poly.exterior.xy

            fig, ax = plt.subplots()
            ax.plot(
                x,
                y,
                color="#6699cc",
                alpha=0.7,
                linewidth=1,
                solid_capstyle="round",
                zorder=2,
                label="original",
            )
            ax.plot(
                sx,
                sy,
                color="#f44",
                alpha=0.7,
                linewidth=1,
                solid_capstyle="round",
                zorder=2,
                label=(
                    "scaled (short + long axis)" if (scale_short_axis and scale_long_axis)
                    else "scaled (short axis)" if scale_short_axis
                    else "scaled (long axis)" if scale_long_axis
                    else "scaled (uniform)"
                ),
            )

            if arrow_points is not None:
                ax.plot(
                    arrow_points[:, 0],
                    arrow_points[:, 1],
                    color="#0f0",
                    linewidth=1.5,
                    label="scale axis",
                )

            ax.set_aspect("equal")
            ax.legend()

            debug_dir = Path(__file__).resolve().parents[1] / "importer" / "msd" / "image_save"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_filename = f"{debug_prefix}_{debug_id}.png" if debug_id else f"{debug_prefix}_debug.png"
            debug_path = debug_dir / debug_filename

            plt.savefig(debug_path, format="png", dpi=150)
            plt.close(fig)

            with Image.open(debug_path) as debug_image:
                print(
                    f"Saved {debug_prefix} scaling debug visualization to {debug_path} "
                    f"(size={debug_image.size}, anisotropic={scale_short_axis})"
                )

        if scaled_poly.is_valid and not scaled_poly.is_empty:
            expanded_boundary = list(scaled_poly.exterior.coords[:-1])
        else:
            expanded_boundary = boundary
    except Exception as e:
        print(f"Failed to scale boundary: {e}")
        expanded_boundary = boundary

    return expanded_boundary


def get_longest_edge_angle(polygon: Polygon | list[Vector2]) -> float:
    """
    Calculate the angle of the longest edge in a polygon.
    Useful for determining the orientation of rectangular features like doors or windows.

    Args:
        polygon: Shapely Polygon object or list of Vector2 points

    Returns:
        Angle in degrees (from X-axis, counterclockwise) of the longest edge
    """
    # Convert to coordinate list
    if isinstance(polygon, Polygon):
        coords = list(polygon.exterior.coords[:-1])  # Exclude duplicate last point
    elif isinstance(polygon, list) and isinstance(polygon[0], Vector2):
        coords = [(v.x, v.y) for v in polygon]
    else:
        raise TypeError("Expected shapely Polygon or list[Vector2]")

    max_length = 0
    angle = 0.0

    for i in range(len(coords)):
        p1 = coords[i]
        p2 = coords[(i + 1) % len(coords)]

        # Calculate edge vector and length
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.sqrt(dx**2 + dy**2)

        # Track the longest edge and its angle
        if length > max_length:
            max_length = length
            # Calculate angle in degrees (from X-axis, counterclockwise)
            angle = math.degrees(math.atan2(dy, dx))

    return angle


def get_dominant_angle(
    polygons: list[Polygon] | list[list[Vector2]], strategy: str = "length_weighted"
) -> float:
    """
    Calculate the dominant angle of a set of polygons for orientation normalization.

    Args:
        polygons: List of shapely Polygon objects or list of list[Vector2] boundaries
        strategy: 'length_weighted' (robust to segmentation), 'count', or 'complex_sum' (length-weighted; more precise)

    Returns:
        Correction angle in degrees to rotate for axis alignment
    """
    angles = []
    edge_lengths = []

    for poly in polygons:
        # Convert to numpy array based on input type
        if isinstance(poly, Polygon):
            coords = np.array(poly.exterior.coords)
        elif isinstance(poly, list) and isinstance(poly[0], Vector2):
            coords = np.array([(v.x, v.y) for v in poly])
        else:
            raise TypeError("Expected shapely Polygon or list[Vector2]")

        vectors = np.diff(coords, axis=0)
        edge_angles = np.arctan2(vectors[:, 1], vectors[:, 0])
        edge_angles_deg = np.rad2deg(edge_angles) % 180
        lengths = np.linalg.norm(vectors, axis=1)

        angles.extend(edge_angles_deg)
        edge_lengths.extend(lengths)

    # Normalize to [0, 90) to treat parallel/perpendicular lines the same
    normalized_angles = np.array([angle % 90 for angle in angles])
    normalized_angles_rad = np.radians(normalized_angles)

    # Compute histogram with optional weighting
    if strategy == "length_weighted":
        hist, bin_edges = np.histogram(
            normalized_angles, bins=90, range=(0, 90), weights=edge_lengths
        )
        dominant_angle_bin = np.argmax(hist)
        dominant_angle = bin_edges[dominant_angle_bin] + 0.5
    elif strategy == "complex_sum":
        # NOTE: based on `length_weighted`, but applies averaging afterwards to
        #       combat histogram-induced bin truncation.
        weights = np.array(edge_lengths)
        hist, bin_edges = np.histogram(normalized_angles, bins=90, range=(0, 90), weights=weights)
        dominant_angle_bin = int(np.argmax(hist))
        bin_indices = np.digitize(normalized_angles, bin_edges, right=False) - 1
        bin_indices = np.clip(bin_indices, 0, len(hist) - 1)
        bin_mask = bin_indices == dominant_angle_bin
        if not np.any(bin_mask):
            bin_mask = np.ones_like(normalized_angles, dtype=bool)

        masked_weights = weights[bin_mask]
        masked_angles = normalized_angles_rad[bin_mask]

        if masked_angles.size == 0:
            dominant_angle = bin_edges[dominant_angle_bin] + 0.5
        else:
            double_angles = 2.0 * masked_angles
            sum_cos = np.sum(masked_weights * np.cos(double_angles))
            sum_sin = np.sum(masked_weights * np.sin(double_angles))

            if np.isclose(sum_cos, 0.0) and np.isclose(sum_sin, 0.0):
                dominant_angle = bin_edges[dominant_angle_bin] + 0.5
            else:
                dominant_angle_rad = 0.5 * np.arctan2(sum_sin, sum_cos)
                dominant_angle = np.rad2deg(dominant_angle_rad)
                dominant_angle = abs(dominant_angle) % 180
                if dominant_angle > 90:
                    dominant_angle = 180 - dominant_angle
    elif strategy == "count":
        hist, bin_edges = np.histogram(normalized_angles, bins=90, range=(0, 90))
        dominant_angle_bin = np.argmax(hist)
        dominant_angle = bin_edges[dominant_angle_bin] + 0.5
    else:
        raise ValueError("Unknown strategy. Use 'length_weighted', 'count', or 'complex_sum'.")

    # Choose smallest rotation to align to 0° or 90°
    if dominant_angle > 45:
        correction_angle = -(dominant_angle - 90)
    else:
        correction_angle = -dominant_angle

    return correction_angle


def rotate_boundary(
    boundary: list[Vector2], angle_degrees: float, origin: tuple[float, float] = (0.0, 0.0)
) -> list[Vector2]:
    """Rotate a room boundary by a given angle around an origin point."""
    if not boundary:
        return boundary

    # Convert to radians
    angle_rad = np.deg2rad(angle_degrees)
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)

    # Rotation matrix
    ox, oy = origin

    rotated = []
    for v in boundary:
        # Translate to origin
        x = v.x - ox
        y = v.y - oy

        # Rotate
        x_new = x * cos_a - y * sin_a
        y_new = x * sin_a + y * cos_a

        # Translate back
        rotated.append(Vector2(x=x_new + ox, y=y_new + oy))

    return rotated


def calculate_floor_plan_centroid(boundaries: list[list[Vector2]]) -> tuple[float, float]:
    """Calculate the centroid of all boundaries for use as rotation/scaling origin."""
    all_x: list[float] = []
    all_y: list[float] = []

    for boundary in boundaries:
        for v in boundary:
            all_x.append(v.x)
            all_y.append(v.y)

    if not all_x:
        return (0.0, 0.0)

    return (sum(all_x) / len(all_x), sum(all_y) / len(all_y))


def scale_boundary(
    boundary: list[Vector2], scale_factor: float, origin: tuple[float, float] = (0.0, 0.0)
) -> list[Vector2]:
    """Scale a room boundary by a given factor around an origin point."""
    if not boundary:
        return boundary

    ox, oy = origin

    scaled: list[Vector2] = []
    for v in boundary:
        # Translate to origin
        x = v.x - ox
        y = v.y - oy

        # Scale
        x_new = x * scale_factor
        y_new = y * scale_factor

        # Translate back
        scaled.append(Vector2(x=x_new + ox, y=y_new + oy))

    return scaled


def scale_floor_plan(
    rooms: list[Room], scale_factor: float, origin: Optional[tuple[float, float]] = None
) -> list[Room]:
    """Scale a floor plan by a given factor.

    Scales each room's boundary and any attached structure boundaries around the
    provided origin (or the global centroid if origin is None).
    """
    if not rooms or scale_factor == 1.0:
        return rooms

    # Calculate centroid if origin not provided
    if origin is None:
        room_boundaries = [room.boundary for room in rooms]
        origin = calculate_floor_plan_centroid(room_boundaries)

    # Scale each room's boundary and structures
    for room in rooms:
        room.boundary = scale_boundary(room.boundary, scale_factor, origin=origin)
        if room.structure:
            for s in room.structure:
                if s.boundary:
                    s.boundary = scale_boundary(s.boundary, scale_factor, origin=origin)

    return rooms


def normalize_floor_plan_orientation(
    rooms: list[Room], strategy: str = "complex_sum", angle_threshold: float = 0.1
) -> tuple[list[Room], float]:
    """
    Normalize the orientation of a floor plan by rotating all rooms to be axis-aligned.

    Rotates each room's boundary and any attached structure boundaries around the
    global centroid used for normalization.

    Returns a tuple of (normalized_rooms, correction_angle).
    """
    if not rooms:
        return rooms, 0.0

    # Calculate orientation correction angle
    room_boundaries = [room.boundary for room in rooms]
    correction_angle = get_dominant_angle(room_boundaries, strategy=strategy)

    # Apply rotation if angle is significant
    if abs(correction_angle) > angle_threshold:
        centroid = calculate_floor_plan_centroid(room_boundaries)

        # Rotate each room's boundary and structures
        for room in rooms:
            room.boundary = rotate_boundary(room.boundary, correction_angle, origin=centroid)
            if room.structure:
                for s in room.structure:
                    if s.boundary:
                        s.boundary = rotate_boundary(s.boundary, correction_angle, origin=centroid)

    return rooms, correction_angle


def calculate_bounds_for_objects(objects: list) -> tuple[float, float, float, float, float, float] | None:
    """Calculate bounding box for a list of Blender objects.

    Args:
        objects: List of Blender objects

    Returns:
        Tuple of (min_x, max_x, min_y, max_y, min_z, max_z) or None if no valid objects
    """
    if not objects:
        return None

    valid_objects = [obj for obj in objects if getattr(obj, "bound_box", None)]
    if not valid_objects:
        return None

    first_obj = valid_objects[0]
    bbox_corners = [first_obj.matrix_world @ Vector(corner) for corner in first_obj.bound_box]

    min_x = min(v.x for v in bbox_corners)
    max_x = max(v.x for v in bbox_corners)
    min_y = min(v.y for v in bbox_corners)
    max_y = max(v.y for v in bbox_corners)
    min_z = min(v.z for v in bbox_corners)
    max_z = max(v.z for v in bbox_corners)

    for obj in valid_objects[1:]:
        bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        min_x = min(min_x, min(v.x for v in bbox_corners))
        max_x = max(max_x, max(v.x for v in bbox_corners))
        min_y = min(min_y, min(v.y for v in bbox_corners))
        max_y = max(max_y, max(v.y for v in bbox_corners))
        min_z = min(min_z, min(v.z for v in bbox_corners))
        max_z = max(max_z, max(v.z for v in bbox_corners))

    return (min_x, max_x, min_y, max_y, min_z, max_z)


def get_world_bounds_2d(obj):
    """Get 2D bounding box (X/Y only) of an object in world space.

    Args:
        obj: Blender object

    Returns:
        Tuple of (min_corner, max_corner) as Vector objects with x, y components
    """
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_corner = Vector(
        (
            min(v.x for v in corners),
            min(v.y for v in corners),
        )
    )
    max_corner = Vector(
        (
            max(v.x for v in corners),
            max(v.y for v in corners),
        )
    )
    return min_corner, max_corner


def push_window_to_wall(window_obj, search_radius: float = 0.1) -> bool:
    """Push a window to the nearest wall face by moving its empty controller.

    Searches for the biggest nearby mesh object (wall) within search_radius and
    moves the window's empty controller to align with the nearest wall face.

    Args:
        window_obj: The window Blender object
        search_radius: Search radius in meters (default: 0.5m)

    Returns:
        True if successfully pushed to wall, False otherwise
    """
    from scene_builder.logging import logger
    from scene_builder.utils.geometry import distance_to_box_2d, get_object_volume

    if window_obj is None:
        logger.warning("Cannot push window to wall: window object is None")
        return False

    # Find the window's empty controller (parent object)
    controller_obj = window_obj.parent
    if controller_obj is None:
        logger.warning(
            f"Cannot push window '{window_obj.name}' to wall: no parent controller found"
        )
        return False

    # Get window's world origin position
    window_origin = window_obj.matrix_world.translation

    # Find biggest nearby mesh object (wall)
    biggest_wall = None
    max_volume = 0.0

    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.name != window_obj.name:
            min_c, max_c = get_world_bounds_2d(obj)
            dist = distance_to_box_2d(window_origin, min_c, max_c)

            if dist <= search_radius:
                vol = get_object_volume(obj)
                if vol > max_volume:
                    max_volume = vol
                    biggest_wall = obj

    if not biggest_wall:
        logger.debug(
            f"No nearby wall found within {search_radius}m of window '{window_obj.name}'. "
            f"Window remains at original position."
        )
        return False

    # Find nearest X/Y side of the wall
    min_corner_wall, max_corner_wall = get_world_bounds_2d(biggest_wall)

    distances = {
        "X+": abs(window_origin.x - max_corner_wall.x),
        "X-": abs(window_origin.x - min_corner_wall.x),
        "Y+": abs(window_origin.y - max_corner_wall.y),
        "Y-": abs(window_origin.y - min_corner_wall.y),
    }

    nearest_side = min(distances, key=distances.get)

    # Move empty controller to align with nearest wall face (keep Z same)
    target_loc = controller_obj.location.copy()
    if nearest_side == "X+":
        target_loc.x = max_corner_wall.x
    elif nearest_side == "X-":
        target_loc.x = min_corner_wall.x
    elif nearest_side == "Y+":
        target_loc.y = max_corner_wall.y
    elif nearest_side == "Y-":
        target_loc.y = min_corner_wall.y
    # Z coordinate remains unchanged

    controller_obj.location = target_loc
    bpy.context.view_layer.update()

    logger.debug(
        f"Pushed window '{window_obj.name}' to {nearest_side} face of wall '{biggest_wall.name}'. "
        f"Controller moved to {target_loc}"
    )

    return True
