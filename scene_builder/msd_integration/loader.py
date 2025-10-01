#!/usr/bin/env python3
"""
Loads MSD apartment data from CSV and creates NetworkX graphs.
"""

import pandas as pd
import networkx as nx
from typing import Optional, List, Dict, Any
from pathlib import Path
import sys

MSD_PATH = Path(__file__).parent.parent.parent.parent / "msd"
sys.path.append(str(MSD_PATH))

from graphs import get_geometries_from_id, extract_access_graph
from constants import ROOM_NAMES
from scene_builder.config import MSD_CSV_PATH


class MSDLoader:
    def __init__(self, csv_path: Optional[str] = None):
        if csv_path is None:
            csv_path = MSD_CSV_PATH

        self.csv_path = Path(csv_path)
        self._df = None

    @property
    def df(self) -> pd.DataFrame:
        """load CSV data"""
        if self._df is None:
            self._df = pd.read_csv(self.csv_path)
        return self._df

    def get_apartment_list(self, min_rooms: int = 5, max_rooms: int = 30) -> List[str]:
        """Get list of apartment IDs"""
        # Count actual rooms per apartment
        room_counts = (
            self.df[self.df["entity_type"] == "area"].groupby("apartment_id").size()
        )

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

        geoms, geom_types = get_geometries_from_id(
            apt_data, floor_id, column="roomtype"
        )
        graph = extract_access_graph(geoms, geom_types, ROOM_NAMES, floor_id)

        # Add metadata
        graph.graph["apartment_id"] = apartment_id
        graph.graph["source"] = "MSD"

        return graph

    def get_random_apartment(self) -> Optional[str]:
        """Get random suitable apartment ID"""
        import random

        apartments = self.get_apartment_list()
        return random.choice(apartments) if apartments else None
