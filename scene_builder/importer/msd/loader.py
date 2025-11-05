"""
Loads MSD apartment data from CSV, creates NetworkX graphs, and converts into SceneBuilder format.

NOTE (yunho-c): This script is hardly stateful and will probably be cleaner if it is not class-based.

TODO: add rounding (safe-rounding) to boundary, to keep scene def files clean and lightweight
"""

import io
import math
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import List, Optional

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from msd.constants import ROOM_NAMES
from msd.graphs import extract_access_graph, get_geometries_from_id
from msd.plot import plot_floor, set_figure
from PIL import Image
from rich.console import Console
from shapely import wkt
from shapely import affinity
from shapely.geometry import Polygon

from scene_builder.config import MSD_CSV_PATH
from scene_builder.definition.scene import Room, Scene, Structure, Vector2
from scene_builder.utils.floorplan import (
    normalize_floor_plan_orientation,
    scale_floor_plan,
    get_dominant_angle,
)
from scene_builder.utils.geometry import round_vector2, get_longest_edge_angle
from scene_builder.utils.room import assign_structures_to_rooms


# Entity subtype mapping (MSD entity_subtype → SceneBuilder category)
# Comment or uncomment to add or remove entities
ENTITY_SUBTYPE_MAP = {
    "BEDROOM": "bedroom",
    "ROOM": "room",
    "LIVING_ROOM": "living_room",
    "LIVING_DINING": "living_dining",
    "KITCHEN": "kitchen",
    "KITCHEN_DINING": "kitchen_dining",
    "DINING": "dining",
    "BATHROOM": "bathroom",
    "CORRIDOR": "corridor",
    # "CORRIDORS_AND_HALLS": "corridors_and_halls",
    # "STAIRCASE": "staircase",
    # "STOREROOM": "storeroom",
    # "BALCONY": "balcony",
    # "TERRACE": "terrace",
    # "ELEVATOR": "elevator",
    # "SHAFT": "shaft",
    # "VOID": "void",
    # "WALL": "wall",
    # "COLUMN": "column",
    # "RAILING": "railing",
    # "ENTRANCE_DOOR": "entrance_door",
    "DOOR": "door",
    "WINDOW": "window",
}


console = Console()


def parse_polygon(geom_string: str) -> list[Vector2]:
    """Parse POLYGON string to Vector2 list"""
    if not geom_string:
        return []

    # Extract coordinates from "POLYGON ((...))"
    pattern = r"POLYGON\s*\(\(\s*(.*?)\s*\)\)"
    match = re.search(pattern, geom_string)

    if not match:
        return []

    coords = []
    try:
        for pair in match.group(1).split(","):
            x_str, y_str = pair.strip().split()
            coords.append(round_vector2(Vector2(x=float(x_str), y=float(y_str)), ndigits=2))
    except Exception as e:
        print(f"ERROR: Failed to parse coordinates from: '{match.group(1)}' - {str(e)}")
        return []

    return coords


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
    """
    Rotate a room boundary by a given angle around an origin point.

    Args:
        boundary: List of Vector2 points defining the room boundary
        angle_degrees: Rotation angle in degrees (positive = counter-clockwise)
        origin: (x, y) tuple of rotation origin (default: (0, 0))

    Returns:
        Rotated boundary as list[Vector2]
    """
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
    """
    Calculate the centroid of all boundaries for use as rotation origin.

    Args:
        boundaries: List of room boundaries

    Returns:
        (x, y) tuple of centroid coordinates
    """
    all_x = []
    all_y = []

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
    """
    Scale a room boundary by a given factor around an origin point.

    Args:
        boundary: List of Vector2 points defining the room boundary
        scale_factor: Scaling factor (e.g., 2.0 for 2x, 0.5 for half)
        origin: (x, y) tuple of scaling origin (default: (0, 0))

    Returns:
        Scaled boundary as list[Vector2]
    """
    if not boundary:
        return boundary

    ox, oy = origin

    scaled = []
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
    """
    Scale a floor plan by a given factor.

    Args:
        rooms: List of Room objects with boundaries to scale
        scale_factor: Scaling factor (e.g., 2.0 for 2x, 0.5 for half)
        origin: (x, y) tuple of scaling origin. If None, uses floor plan centroid (default: None)

    Returns:
        List of Room objects with scaled boundaries
    """
    if not rooms or scale_factor == 1.0:
        return rooms

    # Calculate centroid if origin not provided
    if origin is None:
        room_boundaries = [room.boundary for room in rooms]
        origin = calculate_floor_plan_centroid(room_boundaries)

    # Scale each room's boundary
    for room in rooms:
        room.boundary = scale_boundary(room.boundary, scale_factor, origin=origin)

    return rooms


def normalize_floor_plan_orientation(
    rooms: list[Room], strategy: str = "length_weighted", angle_threshold: float = 0.1
) -> tuple[list[Room], float]:
    """
    Normalize the orientation of a floor plan by rotating all rooms to be axis-aligned.

    Args:
        rooms: List of Room objects with boundaries to normalize
        strategy: 'length_weighted' (robust to segmentation), 'count' (equal weight),
                  or 'complex_sum' (length-weighted complex sum)
        angle_threshold: Minimum angle (degrees) to apply rotation (default: 0.1)

    Returns:
        Tuple of (normalized_rooms, correction_angle):
            - normalized_rooms: List of Room objects with rotated boundaries
            - correction_angle: The angle (in degrees) that was applied
    """
    if not rooms:
        return rooms, 0.0

    # Calculate orientation correction angle
    room_boundaries = [room.boundary for room in rooms]
    correction_angle = get_dominant_angle(room_boundaries, strategy=strategy)

    # Apply rotation if angle is significant
    if abs(correction_angle) > angle_threshold:
        centroid = calculate_floor_plan_centroid(room_boundaries)

        # Rotate each room's boundary
        for room in rooms:
            room.boundary = rotate_boundary(room.boundary, correction_angle, origin=centroid)

    return rooms, correction_angle


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


class MSDLoader:
    def __init__(self, csv_path: Optional[str] = None):
        self.csv_path = Path(csv_path or MSD_CSV_PATH)
        self._df = None

    @property
    def df(self) -> pd.DataFrame:
        """load CSV data"""
        if self._df is None:
            self._df = pd.read_csv(self.csv_path)
        return self._df

    def get_apartment_list(self, min_rooms: int = 5, max_rooms: int = 30) -> list[str]:
        """Get list of apartment IDs"""
        # Count actual rooms per apartment
        room_counts = self.df[self.df["entity_type"] == "area"].groupby("apartment_id").size()

        # Filter by room count
        suitable = room_counts[(room_counts >= min_rooms) & (room_counts <= max_rooms)].index.tolist()  # fmt:skip
        return suitable

    def get_building_list(self) -> List[int]:
        """Get list of building IDs"""
        buildings = self.df["building_id"].dropna().unique().tolist()
        return sorted([int(b) for b in buildings])

    def get_apartments_in_building(
        self, building_id: int, floor_id: Optional[str] = None
    ) -> List[str]:
        """Get list of apartment IDs in a building, optionally filtered by floor_id"""
        building_data = self.df[self.df["building_id"] == building_id]

        if floor_id is not None:
            building_data = building_data[building_data["floor_id"] == floor_id]

        # Filter out NaN
        apartments = building_data["apartment_id"].dropna().unique().tolist()
        return apartments

    def create_graph(self, apartment_id: str, format="msd") -> Optional[nx.Graph]:
        """Create NetworkX graph for one apartment - includes all entity types"""
        apt_data = self.df[self.df["apartment_id"] == apartment_id]

        if len(apt_data) == 0:
            print(f"No data found for apartment {apartment_id}")
            return None

        # Use first floor first
        floor_id = apt_data["floor_id"].iloc[0]

        if format == "msd":
            geoms, geom_types = get_geometries_from_id(apt_data, floor_id, column="roomtype")
            graph = extract_access_graph(geoms, geom_types, ROOM_NAMES, floor_id)

        elif format == "sb":  # SceneBuilder
            # Get all entities for this apartment on this floor
            floor_data = apt_data[apt_data["floor_id"] == floor_id].reset_index(drop=True)

            graph = nx.Graph()
            graph.graph["ID"] = floor_id
            graph.graph["floor_id"] = floor_id

            for idx, row in floor_data.iterrows():
                geom_str = row.get("geom")
                coords = []
                centroid = (0, 0)

                if pd.notna(geom_str):
                    try:
                        geom = wkt.loads(geom_str)
                        if hasattr(geom, "exterior"):
                            coords = list(geom.exterior.coords)
                        if hasattr(geom, "centroid"):
                            centroid = (geom.centroid.x, geom.centroid.y)
                    except Exception:
                        pass

                    graph.add_node(
                        idx,
                        entity_subtype=row.get("entity_subtype"),
                        geometry=coords,
                        centroid=centroid,
                    )

        # Add metadata
        graph.graph["apartment_id"] = apartment_id
        graph.graph["source"] = "MSD"

        return graph

    def get_random_apartment(self) -> Optional[str]:
        """Get random suitable apartment ID"""
        apartments = self.get_apartment_list()
        return random.choice(apartments) if apartments else None

    def get_random_building(self) -> Optional[int]:
        """Get random building ID"""
        buildings = self.get_building_list()
        return random.choice(buildings) if buildings else None

    def convert_graph_to_rooms(
        self,
        graph: nx.Graph,
        *,
        include_structure: bool = True,
        distance_threshold: float = 0.05,
    ) -> list[Room]:
        # NOTE: This is not compatible with 'msd' format `nx.graph`s anymore, for some reason.
        # Let's look into https://github.com/SceneBuilder/SceneBuilder/tree/50bbf93ee1bc1562b4aa67357ae602dd338dd31d/scene_builder to find out.
        """Convert NetworkX graph nodes to SceneBuilder Room objects using entity_subtype.

        This method uses ENTITY_SUBTYPE_MAP which filters entities based on their
        entity_subtype attribute (e.g., "BEDROOM", "LIVING_ROOM"). More selective
        """
        # Collect rooms and structural elements separately
        rooms: list[Room] = []
        structures: list[Structure] = []

        apartment_id = graph.graph.get("apartment_id", "unknown")
        apt_prefix = apartment_id[:8] if len(apartment_id) >= 8 else apartment_id

        for node_id, attrs in graph.nodes(data=True):
            if "geometry" not in attrs:
                continue

            # Parse geometry
            geometry_data = attrs["geometry"]
            if isinstance(geometry_data, list) and len(geometry_data) > 0:
                # Already parsed coordinates
                coords = [
                    round_vector2(Vector2(x=float(p[0]), y=float(p[1])), ndigits=2)
                    for p in geometry_data
                ]
            else:
                coords = []

            if not coords:
                continue

            entity_subtype = attrs.get("entity_subtype")
            category = ENTITY_SUBTYPE_MAP.get(entity_subtype)

            if category is None:
                continue

            uid = f"msd_{apt_prefix}_{node_id}"  # NOTE: ensures unique id; future-proof

            # Detect structural elements
            if category in ("window", "door") and coords:
                structures.append(Structure(id=uid, type=category, boundary=coords))

            else:
                # Regular room
                room = Room(
                    id=uid,
                    category=category,
                    tags=["msd"],
                    boundary=coords,
                    objects=[],
                )
                rooms.append(room)

        if not rooms:
            return rooms

        # Attach structural elements to connected rooms
        if include_structure and structures:
            assign_structures_to_rooms(rooms, structures, distance_threshold)

        return rooms

    def apt_graph_to_scene(self, graph: nx.Graph) -> Scene:
        """Convert a single-apartment graph to a Scene (pydantic) object.

        Returns a Scene; apartment-specific metadata (e.g., apartment_id) is not
        embedded in the Scene model, but remains available from the graph if
        needed by callers.
        """
        rooms = self.convert_graph_to_rooms(graph)
        return Scene(
            category="residential",
            tags=["msd", "apartment"],
            height_class="single_story",
            rooms=rooms,
        )

    def floor_graph_to_scene(self, graph: nx.Graph) -> Scene:
        """Convert a floor-level graph (multiple apartments) to a Scene.

        Returns a Scene; building/floor/apartment metadata is not embedded in
        the Scene model and should be tracked separately by callers if needed.
        """
        rooms = self.convert_graph_to_rooms(graph)
        return Scene(
            category="residential",
            tags=["msd", "floor"],
            height_class="single_story",
            rooms=rooms,
        )

    # NOTE: Only used in `test_floor_plan_postprocessing.py`; TODO: refactor out.
    def get_scene(self, apartment_id: str) -> Optional[Scene]:
        """Create graph and convert to a Scene in one step."""
        graph = self.create_graph(apartment_id)
        if graph is None:
            return None
        return self.apt_graph_to_scene(graph)

    def render_floor_plan(
        self,
        graph: nx.Graph,
        output_path: Optional[str] = None,
        node_size: int = 50,
        edge_size: int = 3,
        show: bool = False,
        show_label=False,
    ) -> np.ndarray | str | None:
        """
        Render a floor plan graph to an image file or numpy array.

        Args:
            graph: NetworkX graph with floor plan data (from create_graph)
            output_path: Path to save the image. If None, returns numpy array instead
            node_size: Size of room centroid nodes (default: 50)
            edge_size: Width of connection edges (default: 3)
            show: If True, display the plot interactively (default: False)
            show_label: If True, shows room label

        Returns:
            - If output_path is provided: Path to the saved image file
            - If output_path is None and show is False: numpy array (H, W, 4) RGBA image
            - If show is True: None

        Example:
            >>> loader = MSDLoader()
            >>> graph = loader.create_graph('apartment_123')
            >>> # Save to file
            >>> loader.render_floor_plan(graph, 'floor_plan.png')
            >>> # Get as numpy array
            >>> img_array = loader.render_floor_plan(graph)
        """
        # Create figure
        fig, ax = set_figure(nc=1, nr=1)

        # Plot floor plan with access graph
        plot_floor(graph, ax, node_size=node_size, edge_size=edge_size, show_labels=show_label)

        # Set aspect ratio and remove axes
        ax.set_aspect("equal")
        ax.axis("off")

        if show:
            plt.show()
            plt.close(fig)
            return None
        elif output_path is None:
            # Return as numpy array
            buf = io.BytesIO()
            plt.savefig(buf, format="png", bbox_inches="tight", dpi=150)
            buf.seek(0)

            # Convert to numpy array
            img = Image.open(buf)
            img_array = np.array(img)

            buf.close()
            plt.close(fig)
            return img_array
        else:
            # Save to file
            plt.savefig(output_path, bbox_inches="tight", dpi=150)
            plt.close(fig)
            return output_path

    def visualize_building_entities(
        self,
        building_id: int,
        floor_id: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Visualize all entities from ENTITY_SUBTYPE_MAP for a building's floor plan.
        Processes at the same scale as test_msd_to_blender.py - one floor at a time,
        combining all apartments on each floor.

        Args:
            building_id: The building ID to visualize (e.g., 2144)
            floor_id: If provided, visualize only this floor; otherwise visualize all floors
            output_path: Path to save the image. If None, saves to default location

        Returns:
            Path to the saved image file, or None if no entities found

        Example:
            >>> loader = MSDLoader()
            >>> loader.visualize_building_entities(2144, output_path='building_2144.png')
        """
        # Get all apartments in the building
        apartments = self.get_apartments_in_building(building_id, floor_id)

        # Group apartments by floor 
        floors = defaultdict(list)
        for apt_id in apartments:
            graph = self.create_graph(apt_id)
            if graph:
                apt_floor_id = graph.graph.get("floor_id")
                floors[apt_floor_id].append((apt_id, graph))

        # Create color mapping for entity subtypes
        entity_subtypes = list(ENTITY_SUBTYPE_MAP.keys())
        num_subtypes = len(entity_subtypes)
        # Use matplotlib colormap - handle both old and new API
        try:
            cmap = plt.colormaps["tab20"]
        except (AttributeError, KeyError):
            cmap = plt.cm.get_cmap("tab20")
        subtype_colors = {
            subtype: cmap(i / max(num_subtypes, 1)) for i, subtype in enumerate(entity_subtypes)
        }

        # Process each floor separately
        for floor_id_key, apt_graphs in floors.items():
            # First pass: collect all non-door entities
            non_door_entities = []
            door_entities = []

            for apt_id, graph in apt_graphs:
                for node_id, attrs in graph.nodes(data=True):
                    entity_subtype = attrs.get("entity_subtype")
                    geometry_data = attrs.get("geometry", [])

                    # Filter by ENTITY_SUBTYPE_MAP
                    if entity_subtype not in ENTITY_SUBTYPE_MAP:
                        continue

                    # Skip if no valid geometry
                    if not geometry_data or len(geometry_data) < 3:
                        continue

                    # Create Polygon from geometry
                    try:
                        polygon = Polygon(geometry_data)
                        if polygon.is_valid and not polygon.is_empty:
                            entity_data = {
                                "polygon": polygon,
                                "entity_subtype": entity_subtype,
                                "category": ENTITY_SUBTYPE_MAP[entity_subtype],
                            }
                            
                            # Separate doors from other entities
                            if entity_subtype == "DOOR":
                                door_entities.append(entity_data)
                            else:
                                non_door_entities.append(entity_data)
                    except Exception:
                        continue

            # Second pass: classify doors based on proximity to non-door entities
            non_door_polygons = [e["polygon"] for e in non_door_entities]
            entities_to_plot = non_door_entities.copy()

            for door_entity in door_entities:
                door_type = classify_door_type(door_entity["polygon"], non_door_polygons)
                door_entity["door_type"] = door_type
                door_entity["display_label"] = f"DOOR ({door_type})"
                entities_to_plot.append(door_entity)

            if not entities_to_plot:
                print(f"No entities found for floor {floor_id_key}")
                continue

            # Create figure for this floor
            fig, ax = plt.subplots(figsize=(12, 12))

            # Define colors for interior and exterior doors
            interior_door_color = (0.0, 0.8, 0.0, 0.8)  # Green for interior
            exterior_door_color = (0.8, 0.0, 0.0, 0.8)  # Red for exterior

            # Plot all entities
            for entity in entities_to_plot:
                polygon = entity["polygon"]
                entity_subtype = entity["entity_subtype"]
                
                # Use special colors for doors based on classification
                if entity_subtype == "DOOR":
                    door_type = entity.get("door_type", "exterior")
                    color = interior_door_color if door_type == "interior" else exterior_door_color
                else:
                    color = subtype_colors.get(entity_subtype, (0.5, 0.5, 0.5, 0.5))

                x, y = polygon.exterior.xy
                ax.fill(x, y, color=color, alpha=0.6, edgecolor="black", linewidth=0.5)

            # Set up plot
            ax.set_aspect("equal")
            ax.set_title(
                f"Building {building_id} - Floor {floor_id_key}\n"
                f"{len(apt_graphs)} apartments, {len(entities_to_plot)} entities"
            )
            ax.grid(True, alpha=0.3)

            # Create legend
            legend_elements = []
            
            # Add non-door entities to legend
            for subtype in entity_subtypes:
                if subtype != "DOOR":
                    if any(e["entity_subtype"] == subtype for e in entities_to_plot):
                        legend_elements.append(
                            plt.Rectangle(
                                (0, 0),
                                1,
                                1,
                                facecolor=subtype_colors.get(subtype, (0.5, 0.5, 0.5, 0.5)),
                                label=f"{subtype} → {ENTITY_SUBTYPE_MAP[subtype]}",
                            )
                        )
            
            # Add door types separately (interior and exterior)
            has_interior_door = any(
                e.get("entity_subtype") == "DOOR" and e.get("door_type") == "interior"
                for e in entities_to_plot
            )
            has_exterior_door = any(
                e.get("entity_subtype") == "DOOR" and e.get("door_type") == "exterior"
                for e in entities_to_plot
            )
            
            if has_interior_door:
                legend_elements.append(
                    plt.Rectangle(
                        (0, 0),
                        1,
                        1,
                        facecolor=interior_door_color,
                        label="DOOR (interior)",
                    )
                )
            
            if has_exterior_door:
                legend_elements.append(
                    plt.Rectangle(
                        (0, 0),
                        1,
                        1,
                        facecolor=exterior_door_color,
                        label="DOOR (exterior)",
                    )
                )
            
            ax.legend(handles=legend_elements, loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8)

            # Determine output path
            if output_path:
                # If multiple floors, append floor_id to filename
                if len(floors) > 1:
                    path_obj = Path(output_path)
                    output_file = path_obj.parent / f"{path_obj.stem}_floor_{floor_id_key}{path_obj.suffix}"
                else:
                    output_file = Path(output_path)
            else:
                # Default output path
                output_file = Path(f"building_{building_id}_floor_{floor_id_key}_entities.png")

            # Save figure
            output_file.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(output_file, bbox_inches="tight", dpi=150)
            plt.close(fig)

            print(f"Saved visualization: {output_file} ({len(entities_to_plot)} entities)")

        # Return the output path for the last floor processed (or first if multiple)
        if output_path:
            if len(floors) > 1:
                last_floor_id = list(floors.keys())[-1]
                path_obj = Path(output_path)
                return str(path_obj.parent / f"{path_obj.stem}_floor_{last_floor_id}{path_obj.suffix}")
            else:
                return output_path
        else:
            last_floor_id = list(floors.keys())[-1]
            return str(Path(f"building_{building_id}_floor_{last_floor_id}_entities.png"))
