#!/usr/bin/env python3
"""
Tests: MSD Building → SceneBuilder → Blender (.blend file)
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from scene_builder.msd_integration.loader import MSDLoader
from scene_builder.msd_integration.converter import GraphToSceneConverter
from scene_builder.decoder import blender


def test_msd_to_blender():
    loader = MSDLoader()
    converter = GraphToSceneConverter()

    building_id = loader.get_random_building()
    print(f"Loading building {building_id}...")

    graphs = loader.create_building_graph(building_id)
    print(f"Found {len(graphs)} apartments in building")

    scene_data = {
        "category": "residential",
        "tags": ["msd", "building"],
        "floorType": "multi",
        "metadata": {
            "building_id": building_id,
            "apartment_count": len(graphs),
            "source": "MSD",
        },
        "rooms": [],
    }

    for graph in graphs:
        rooms = converter.convert_graph_to_rooms(graph)
        scene_data["rooms"].extend(rooms)

    # Convert Room objects to dictionaries
    blender_scene_data = {
        "category": scene_data["category"],
        "tags": scene_data["tags"],
        "floorType": scene_data["floorType"],
        "metadata": scene_data["metadata"],
        "rooms": [],
    }

    for i, room in enumerate(scene_data["rooms"]):
        print(
            f"🔍 Room {i}: {room.id}, category={room.category}, boundary_points={len(room.boundary)}"
        )

        room_dict = {
            "id": room.id,
            "category": room.category,
            "tags": room.tags,
            "boundary": [{"x": p.x, "y": p.y} for p in room.boundary],
            "objects": room.objects,
        }
        blender_scene_data["rooms"].append(room_dict)

    print(f"✓ Prepared {len(blender_scene_data['rooms'])} rooms for Blender")

    # Parse scene definition in Blender
    blender.parse_scene_definition(blender_scene_data)

    output_dir = (
        Path(__file__).parent.parent / "scene_builder" / "msd_integration" / "output"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"msd_building_{building_id}.blend"
    blender.save_scene(str(output_file))
    print(f"✓ Blender file saved: {output_file}")

    render_path = blender.render_top_down(str(output_dir) + "/")
    print(f"✓ Rendered image saved: {render_path}")


if __name__ == "__main__":
    test_msd_to_blender()
