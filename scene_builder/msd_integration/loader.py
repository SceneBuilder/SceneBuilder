"""
Loads MSD apartment data from CSV, creates NetworkX graphs, and converts into SceneBuilder format.

NOTE (yunho-c): This script is hardly stateful and will probably be cleaner if it is not class-based.

TODO: add rounding (safe-rounding) to boundary, to keep scene def files clean and lightweight
"""

import io
import random
import re
from pathlib import Path
from typing import Optional

import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from msd.graphs import get_geometries_from_id, extract_access_graph
from msd.constants import ROOM_NAMES
from msd.plot import plot_floor, set_figure
from PIL import Image
from shapely.geometry import Polygon

from scene_builder.config import MSD_CSV_PATH
from scene_builder.definition.scene import Room, Vector2
from scene_builder.utils.geometry import round_vector2


# Room type mapping (MSD index → SceneBuilder category)
# Based on ROOM_NAMES order from msd.constants
ROOM_TYPE_MAP = {
    0: "bedroom",
    1: "living_room",
    2: "kitchen",
    3: "dining",
    4: "corridor",
    5: "stairs",
    6: "storeroom",
    7: "bathroom",
    8: "balcony",
}


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


def calculate_polygon_metrics(coords: list[Vector2]) -> dict:
    """Calculate actual polygon metrics using shoelace formula and geometric analysis"""
    if len(coords) < 3:
        return {
            "area": 0.0,
            "perimeter": 0.0,
            "vertices": len(coords),
            "complexity": "invalid",
        }

    # Calculate area using shoelace formula
    area = 0.0
    for i in range(len(coords)):
        j = (i + 1) % len(coords)
        area += coords[i].x * coords[j].y
        area -= coords[j].x * coords[i].y
    area = abs(area) / 2.0

    # Calculate bounding box for reference
    min_x = min(c.x for c in coords)
    max_x = max(c.x for c in coords)
    min_y = min(c.y for c in coords)
    max_y = max(c.y for c in coords)
    bbox_width = abs(max_x - min_x)
    bbox_height = abs(max_y - min_y)

    return {
        "area": area,
        "vertices": len(coords),
        "bbox_width": bbox_width,
        "bbox_height": bbox_height,
    }


def get_dominant_angle(polygons: list[Polygon] | list[list[Vector2]], strategy: str = 'length_weighted') -> float:
    """
    Calculate the dominant angle of a set of polygons for orientation normalization.

    Args:
        polygons: List of shapely Polygon objects or list of list[Vector2] boundaries
        strategy: 'length_weighted' (robust to segmentation) or 'count' (equal weight)

    Returns:
        Correction angle in degrees to rotate for axis alignment
    """
    angles = []
    edge_lengths = []

    for poly in polygons:
        # Convert to numpy array based on input type
        if isinstance(poly, Polygon):
            coords = np.array(poly.exterior.coords)
        elif isinstance(poly, list) and isinstance(poly[0], Vector2) :
            coords = np.array([(v.x, v.y) for v in poly])
        else:
            raise TypeError()

        vectors = np.diff(coords, axis=0)
        edge_angles = np.arctan2(vectors[:, 1], vectors[:, 0])
        edge_angles_deg = np.rad2deg(edge_angles) % 180
        lengths = np.linalg.norm(vectors, axis=1)

        angles.extend(edge_angles_deg)
        edge_lengths.extend(lengths)

    # Normalize to [0, 90) to treat parallel/perpendicular lines the same
    normalized_angles = [angle % 90 for angle in angles]

    # Compute histogram with optional weighting
    if strategy == 'length_weighted':
        hist, bin_edges = np.histogram(normalized_angles, bins=90, range=(0, 90), weights=edge_lengths)
    else:
        hist, bin_edges = np.histogram(normalized_angles, bins=90, range=(0, 90))

    # Find dominant angle
    dominant_angle_bin = np.argmax(hist)
    dominant_angle = bin_edges[dominant_angle_bin] + 0.5

    # Choose smallest rotation to align to 0° or 90°
    if dominant_angle > 45:
        correction_angle = -(dominant_angle - 90)
    else:
        correction_angle = -dominant_angle

    return correction_angle


def rotate_boundary(boundary: list[Vector2], angle_degrees: float, origin: tuple[float, float] = (0.0, 0.0)) -> list[Vector2]:
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


def scale_boundary(boundary: list[Vector2], scale_factor: float, origin: tuple[float, float] = (0.0, 0.0)) -> list[Vector2]:
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


def scale_floor_plan(rooms: list[Room], scale_factor: float, origin: Optional[tuple[float, float]] = None) -> list[Room]:
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
    rooms: list[Room],
    strategy: str = 'length_weighted',
    angle_threshold: float = 0.1
) -> tuple[list[Room], float]:
    """
    Normalize the orientation of a floor plan by rotating all rooms to be axis-aligned.

    Args:
        rooms: List of Room objects with boundaries to normalize
        strategy: 'length_weighted' (robust to segmentation) or 'count' (equal weight)
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
        suitable = room_counts[
            (room_counts >= min_rooms) & (room_counts <= max_rooms)
        ].index.tolist()

        return suitable

    def create_graph(self, apartment_id: str) -> Optional[nx.Graph]:
        """Create NetworkX graph for one apartment"""
        apt_data = self.df[self.df["apartment_id"] == apartment_id]

        if len(apt_data) == 0:
            print(f"No data found for apartment {apartment_id}")
            return None

        # Use first floor first
        floor_id = apt_data["floor_id"].iloc[0]

        geoms, geom_types = get_geometries_from_id(apt_data, floor_id, column="roomtype")
        graph = extract_access_graph(geoms, geom_types, ROOM_NAMES, floor_id)

        # Add metadata
        graph.graph["apartment_id"] = apartment_id
        graph.graph["source"] = "MSD"

        return graph

    def convert_graph_to_rooms(self, graph: nx.Graph) -> list[Room]:
        """Convert NetworkX graph nodes to SceneBuilder Room objects"""
        rooms = []

        for node_id, attrs in graph.nodes(data=True):
            # Skip nodes without geometry
            if "geometry" not in attrs:
                continue

            # Parse geometry
            geometry_data = attrs["geometry"]
            if isinstance(geometry_data, list):
                # Already parsed coordinates
                coords = [round_vector2(Vector2(x=float(p[0]), y=float(p[1])), ndigits=2) for p in geometry_data]
            else:
                coords = []

            if not coords:
                continue

            room_type_idx = attrs.get("room_type", 0)
            category = ROOM_TYPE_MAP.get(room_type_idx, "room")

            room = Room(
                id=f"msd_room_{node_id}",
                category=category,
                tags=["msd"],
                boundary=coords,
                objects=[],
            )

            rooms.append(room)

        return rooms

    def graph_to_scene_data(self, graph: nx.Graph) -> dict:
        """Convert graph to scene data dict"""
        rooms = self.convert_graph_to_rooms(graph)

        return {
            "category": "residential",
            "tags": ["msd", "apartment"],
            "height_class": "multi",
            "rooms": rooms,
            "metadata": {
                "apartment_id": graph.graph.get("apartment_id", "unknown"),
                "room_count": len(rooms),
                "source": "MSD",
            },
        }

    def get_scene(self, apartment_id: str) -> Optional[dict]:
        """Create graph and convert to scene data in one step"""
        graph = self.create_graph(apartment_id)
        if graph is None:
            return None
        return self.graph_to_scene_data(graph)

    def get_random_apartment(self) -> Optional[str]:
        """Get random suitable apartment ID"""
        apartments = self.get_apartment_list()
        return random.choice(apartments) if apartments else None

    def render_floor_plan(
        self,
        graph: nx.Graph,
        output_path: Optional[str] = None,
        node_size: int = 50,
        edge_size: int = 3,
        show: bool = False,
        show_label=False
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
