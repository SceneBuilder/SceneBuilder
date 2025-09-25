#!/usr/bin/env python3
"""
Converts NetworkX graphs to SceneBuilder Room objects.
Graph → Scene conversion
"""

import networkx as nx
from typing import List
import re

from scene_builder.definition.scene import Room, Vector2, FloorDimensions


def parse_polygon(geom_string: str) -> List[Vector2]:
    """Parse POLYGON string to Vector2 list"""
    if not geom_string:
        return []

    # Extract coordinates from "POLYGON ((...)))"
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


def calculate_polygon_metrics(coords: List[Vector2]) -> dict:
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


def calculate_dimensions(coords: List[Vector2]) -> FloorDimensions:
    """Calculate room dimensions from coordinates"""
    if not coords:
        return FloorDimensions()

    metrics = calculate_polygon_metrics(coords)

    # Use bounding box for width/length for compatibility, but add area
    return FloorDimensions(
        width=metrics["bbox_width"],
        length=metrics["bbox_height"],
        area_sqm=metrics["area"],
        ceiling_height=2.6,
        shape="polygon",
    )


class GraphToSceneConverter:
    """Convert MSD graph to SceneBuilder format"""

    # Room type mapping (MSD index → SceneBuilder category)
    ROOM_TYPE_MAP = {
        0: "bedroom",  # Bedroom
        1: "living_room",  # Livingroom
        2: "kitchen",  # Kitchen
        3: "dining",  # Dining
        4: "corridor",  # Corridor
        5: "stairs",  # Stairs
        6: "storeroom",  # Storeroom
        7: "bathroom",  # Bathroom
        8: "balcony",  # Balcony
    }

    def convert_graph_to_rooms(self, graph: nx.Graph) -> List[Room]:
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
            category = self.ROOM_TYPE_MAP.get(room_type_idx, "room")

            room = Room(
                id=f"msd_room_{node_id}",
                category=category,
                tags=["msd"],
                boundary=coords,
                floor_dimensions=calculate_dimensions(coords),
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
            "floorType": "multi",
            "rooms": rooms,
            "metadata": {
                "apartment_id": graph.graph.get("apartment_id", "unknown"),
                "room_count": len(rooms),
                "source": "MSD",
            },
        }
