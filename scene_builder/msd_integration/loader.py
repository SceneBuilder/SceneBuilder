#!/usr/bin/env python3
"""
Loads MSD apartment data from CSV and creates NetworkX graphs.
"""

import pandas as pd
import networkx as nx
from typing import Optional, List
from pathlib import Path

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

    def get_building_list(self) -> List[int]:
        """Get list of building IDs"""
        buildings = self.df["building_id"].dropna().unique().tolist()
        return sorted([int(b) for b in buildings])

    def get_first_floor_id(self, building_id: int) -> Optional[str]:
        """Get the first floor ID for a building"""
        building_data = self.df[self.df["building_id"] == building_id]
        if len(building_data) == 0:
            return None
        return building_data["floor_id"].iloc[0]

    def get_apartments_in_building(
        self, building_id: int, floor_id: Optional[str] = None
    ) -> List[str]:
        """Get list of apartment IDs in a building, optionally filtered by floor_id"""
        building_data = self.df[self.df["building_id"] == building_id]

        # Filter by floor_id if provided
        if floor_id is not None:
            building_data = building_data[building_data["floor_id"] == floor_id]

        # Filter out NaN values
        apartments = building_data["apartment_id"].dropna().unique().tolist()
        return apartments

    def create_graph(self, apartment_id: str) -> Optional[nx.Graph]:
        """Create NetworkX graph for one apartment - includes all entity types"""
        apt_data = self.df[self.df["apartment_id"] == apartment_id]

        if len(apt_data) == 0:
            print(f"No data found for apartment {apartment_id}")
            return None

        # Use first floor first
        floor_id = apt_data["floor_id"].iloc[0]

        # Get all entities for this floor
        floor_data = apt_data[apt_data["floor_id"] == floor_id].reset_index(drop=True)
        
        # Create graph with all entities (not just rooms)
        graph = nx.Graph()
        graph.graph["ID"] = floor_id
        graph.graph["floor_id"] = floor_id
        graph.graph["apartment_id"] = apartment_id
        graph.graph["source"] = "MSD"
        
        # Add each entity as a node
        for idx, row in floor_data.iterrows():
            # Parse geometry
            geom_str = row.get("geom")
            coords = []
            centroid = (0, 0)
            
            if pd.notna(geom_str):
                try:
                    from shapely import wkt
                    geom = wkt.loads(geom_str)
                    if hasattr(geom, 'exterior'):
                        coords = list(geom.exterior.coords)
                    if hasattr(geom, 'centroid'):
                        centroid = (geom.centroid.x, geom.centroid.y)
                except Exception:
                    pass
            
            # Add node with attributes
            graph.add_node(idx, 
                          entity_type=row.get("entity_type"),
                          entity_subtype=row.get("entity_subtype"),
                          geometry=coords,
                          centroid=centroid)

        return graph

    def create_building_graph(self, building_id: int) -> List[nx.Graph]:
        """Create NetworkX graphs for all apartments in a building (first floor only)"""
        # Get first floor
        floor_id = self.get_first_floor_id(building_id)
        if not floor_id:
            print(f"No floor data found for building {building_id}")
            return []

        # Get only apartments on the first floor
        apartments = self.get_apartments_in_building(building_id, floor_id=floor_id)
        graphs = []

        for apt_id in apartments:
            graph = self.create_graph(apt_id)
            if graph:
                graph.graph["building_id"] = building_id
                graph.graph["floor_id"] = floor_id
                graphs.append(graph)

        return graphs

    def get_random_building(self) -> Optional[int]:
        """Get random building ID"""
        import random

        buildings = self.get_building_list()
        return random.choice(buildings) if buildings else None
