"""
Tests: MSD Building → SceneBuilder → Blender (.blend file)
"""

import sys
from collections import defaultdict
from pathlib import Path

from loguru import logger

from scene_builder.decoder import blender
from scene_builder.msd_integration.loader import MSDLoader

logger.remove()
logger.add(sys.stderr, level="WARNING")


def test_msd_to_blender():
    loader = MSDLoader()

    # building_id = loader.get_random_building()

    # if not building_id:
    #     print("No buildings found in dataset")
    #     return

    # print(f"Loading random building {building_id}...\n")

    # Fixed building ID for debugging
    building_id = 2144

    print(f"Loading building {building_id}...\n")

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
        print(f"Floor {floor_id}: {len(apt_graphs)} apartments")

        all_rooms = []
        apartment_rooms = []
        for apt_id, graph in apt_graphs:
            rooms = loader.convert_graph_to_rooms(graph)
            all_rooms.extend(rooms)
            apartment_rooms.append((apt_id, rooms))
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

        # Align floor plan 
        scene_data = blender.floorplan_to_origin(
            scene_data, 
            rooms_by_apartment=apartment_rooms,
            align_rotation=True
        )

        blender.parse_scene_definition(scene_data)

        # Create walls for each room (excluding windows and exterior doors)
        walls_created = blender.create_room_walls(all_rooms)
        if walls_created > 0:
            print(f"   ✓ Created {walls_created} room walls (excluding windows and exterior doors)")

        # Detect and mark interior doors
        interior_door_count = 0
        for room in all_rooms:
            if room.category == "door":
                door_boundary = [(p.x, p.y) for p in room.boundary]
                if blender.mark_interior_door(door_boundary, room.id):
                    interior_door_count += 1
        
        if interior_door_count > 0:
            print(f"   ✓ Marked {interior_door_count} interior doors with yellow cubes")

        output_file = output_dir / f"msd_building_{building_id}_floor_{floor_id}.blend"
        blender.save_scene(str(output_file))
        print(f"   ✓ Saved: {output_file.name}")

        render_file = output_dir / f"msd_building_{building_id}_floor_{floor_id}_topdown.png"
        blender._configure_render_settings()
        blender._configure_output_image("PNG", 1024)
        blender._setup_top_down_camera()
        blender._setup_lighting(energy=0.5)
        render_path = blender.render_to_file(str(render_file))
        print(f"   ✓ Rendered: {render_path.name}")

        print()


if __name__ == "__main__":
    test_msd_to_blender()
