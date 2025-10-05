#!/usr/bin/env python3
"""
Tests: MSD Building → SceneBuilder → Blender (.blend file)
"""

import sys
from pathlib import Path
from collections import defaultdict

sys.path.append(str(Path(__file__).parent.parent))

from scene_builder.msd_integration.loader import MSDLoader
from scene_builder.msd_integration.converter import GraphToSceneConverter
from scene_builder.decoder import blender


def test_msd_to_blender():
    loader = MSDLoader()
    converter = GraphToSceneConverter()

    building_id = loader.get_random_building()

    if not building_id:
        print("No buildings found in dataset")
        return

    print(f"Loading random building {building_id}...\n")

    # Get all apartments and group by floor
    apartments = loader.get_apartments_in_building(building_id)
    floors = defaultdict(list)

    for apt_id in apartments:
        graph = loader.create_graph(apt_id)
        if graph:
            floor_id = graph.graph.get("floor_id")
            floors[floor_id].append((apt_id, graph))

    print(f"Found {len(apartments)} apartments across {len(floors)} floors\n")

    output_dir = Path(__file__).parent.parent / "scene_builder/msd_integration/output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process each floor
    for floor_id, apt_graphs in floors.items():
        print(f"🏢 Floor {floor_id}: {len(apt_graphs)} apartments")

        all_rooms = []
        for apt_id, graph in apt_graphs:
            rooms = converter.convert_graph_to_rooms(graph)
            all_rooms.extend(rooms)
            print(f"    {apt_id}: {len(rooms)} entities")

        # Prepare scene data for this floor
        scene_data = {
            "category": "residential",
            "tags": ["msd", "floor"],
            "floorType": "single",
            "metadata": {
                "building_id": building_id,
                "floor_id": floor_id,
                "apartment_count": len(apt_graphs),
                "source": "MSD",
            },
            "rooms": [
                {
                    "id": room.id,
                    "category": room.category,
                    "tags": room.tags,
                    "boundary": [{"x": p.x, "y": p.y} for p in room.boundary],
                    "objects": room.objects,
                }
                for room in all_rooms
            ],
        }

        blender.parse_scene_definition(scene_data)

        output_file = output_dir / f"msd_building_{building_id}_floor_{floor_id}.blend"
        blender.save_scene(str(output_file))
        print(f"   ✓ Saved: {output_file.name}")

        render_path = blender.render_top_down(str(output_dir))
        print(f"   ✓ Rendered: {Path(render_path).name}\n")


if __name__ == "__main__":
    test_msd_to_blender()
