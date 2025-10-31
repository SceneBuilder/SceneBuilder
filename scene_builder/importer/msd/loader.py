"""
Loads MSD apartment data from CSV, creates NetworkX graphs, and converts into SceneBuilder format.

NOTE (yunho-c): This script is hardly stateful and will probably be cleaner if it is not class-based.

TODO: add rounding (safe-rounding) to boundary, to keep scene def files clean and lightweight
"""

import io
import math
import random
import re
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
