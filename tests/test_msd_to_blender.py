"""
Tests: MSD Building → SceneBuilder → Blender (.blend file)
"""

import sys
from collections import defaultdict
from pathlib import Path

from loguru import logger

from scene_builder.decoder.blender import blender
from scene_builder.importer.msd.loader import MSDLoader
from scene_builder.utils.blender import install_door_it_addon

logger.remove()
logger.add(sys.stderr, level="WARNING")


def test_msd_to_blender(door_cutout=True, window_cutout=True, enable_doors=False, visualize_entities=False, keep_cutters_visible=True):
    # Install Door It! Interior addon if requested and available
    if enable_doors:
        addon_installed = install_door_it_addon()
        if addon_installed:
            print("✓✓✓ Door It! Interior addon enabled - doors will be created")
        else:
            print("✗✗✗ Door It! Interior addon not available - only cutouts will be created")
    
    loader = MSDLoader()

    # building_id = loader.get_random_building()

    # if not building_id:
    #     print("No buildings found in dataset")
    #     return

    # print(f"Loading random building {building_id}...\n")

    # Fixed building ID for debugging
    building_id = 2144

    print(f"Loading building {building_id}...\n")

    # Visualize building entities if requested
    if visualize_entities:
        output_dir = Path(__file__).parent.parent / "test_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        viz_path = output_dir / f"building_{building_id}_entities.png"
        print(f"Visualizing building entities...")
        result = loader.visualize_building_entities(
            building_id=building_id,
            output_path=str(viz_path)
        )
        if result:
            print(f"   ✓ Saved entity visualization: {result}\n")

    # Get all apartments and group by floor
    apartments = loader.get_apartments_in_building(building_id)
    floors = defaultdict(list)

    for apt_id in apartments:
        graph = loader.create_graph(apt_id)
        if graph:
            floor_id = graph.graph.get("floor_id")
            floors[floor_id].append((apt_id, graph))

    print(f"Found {len(apartments)} apartments across {len(floors)} floors\n")

    output_dir = Path(__file__).parent.parent / "test_output"
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
        walls_created = blender.create_room_walls(
            all_rooms, 
            door_cutouts=door_cutout, 
            window_cutouts=window_cutout,
            keep_cutters_visible=keep_cutters_visible
        )
        if walls_created > 0:
            print(f"   ✓ Created {walls_created} room walls (excluding windows and exterior doors)")

        # # Detect and mark interior doors
        # interior_door_count = 0
        # for room in all_rooms:
        #     if room.category == "door":
        #         door_boundary = [(p.x, p.y) for p in room.boundary]
        #         if blender.mark_interior_door(door_boundary, room.id):
        #             interior_door_count += 1
        
        # if interior_door_count > 0:
        #     print(f"   ✓ Marked {interior_door_count} interior doors with yellow cubes")

        output_file = output_dir / f"msd_building_{building_id}_floor_{floor_id}_{door_cutout=}_{window_cutout=}.blend"
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
    # test_msd_to_blender(door_cutout=False)
    # test_msd_to_blender(window_cutout=False)
    # test_msd_to_blender(door_cutout=False, window_cutout=False)
    # test_msd_to_blender(visualize_entities=True)  # Enable entity visualization
