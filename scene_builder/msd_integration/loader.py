"""
Loads MSD apartment data from CSV, creates NetworkX graphs, and converts into SceneBuilder format.

NOTE (yunho-c): This script is hardly stateful and will probably be cleaner if it is not class-based.

TODO: add rounding (safe-rounding) to boundary, to keep scene def files clean and lightweight
"""

import io
import random
import re
from pathlib import Path
from typing import Optional, Union

import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from msd.graphs import get_geometries_from_id, extract_access_graph
from msd.constants import ROOM_NAMES
from msd.plot import plot_floor, set_figure
from PIL import Image

from scene_builder.config import MSD_CSV_PATH
from scene_builder.definition.scene import Room, Vector2


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
            coords.append(Vector2(x=float(x_str), y=float(y_str)))
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
                coords = [Vector2(x=float(p[0]), y=float(p[1])) for p in geometry_data]
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
    ) -> Union[np.ndarray, str, None]:
        """
        Render a floor plan graph to an image file or numpy array.

        Args:
            graph: NetworkX graph with floor plan data (from create_graph)
            output_path: Path to save the image. If None, returns numpy array instead
            node_size: Size of room centroid nodes (default: 50)
            edge_size: Width of connection edges (default: 3)
            show: If True, display the plot interactively (default: False)

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
        plot_floor(graph, ax, node_size=node_size, edge_size=edge_size)

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
