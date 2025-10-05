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

    # Get first building ID
    building_list = loader.get_building_list()
    building_id = building_list[0] if building_list else None
    
    if not building_id:
        print("No buildings found in dataset")
        return
    
    print(f"Loading building {building_id}...\n")

    # Get all apartments in building (all floors)
    apartments = loader.get_apartments_in_building(building_id)
    print(f"Found {len(apartments)} apartments across all floors\n")

    output_dir = (
        Path(__file__).parent.parent / "scene_builder" / "msd_integration" / "output"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process each apartment separately
    for apt_id in apartments:
        graph = loader.create_graph(apt_id)
        if not graph:
            continue
        
        floor_id = graph.graph.get("floor_id")
        print(f"📍 Apartment: {apt_id} (Floor: {floor_id})")
        
        # Convert graph to rooms
        rooms = converter.convert_graph_to_rooms(graph)
        print(f"   {len(rooms)} entities")
        
        # Prepare scene data for this apartment
        scene_data = {
            "category": "residential",
            "tags": ["msd", "apartment"],
            "floorType": "single",
            "metadata": {
                "building_id": building_id,
                "floor_id": floor_id,
                "apartment_id": apt_id,
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
                for room in rooms
            ],
        }

        # Render this apartment
        blender.parse_scene_definition(scene_data)
        
        # Save with apartment ID in filename
        output_file = output_dir / f"msd_apartment_{apt_id}.blend"
        blender.save_scene(str(output_file))
        print(f"   ✓ Saved: {output_file.name}")
        
        render_path = blender.render_top_down(str(output_dir))
        print(f"   ✓ Rendered: {Path(render_path).name}\n")


if __name__ == "__main__":
    test_msd_to_blender()
