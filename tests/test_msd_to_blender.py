"""
Tests: MSD Building → SceneBuilder → Blender (.blend file)
"""

from collections import defaultdict
from pathlib import Path
from typing import Optional

from scene_builder.decoder.blender import blender
from scene_builder.definition.scene import Scene
from scene_builder.importer.msd.loader import MSDLoader
from scene_builder.logging import configure_logging
from scene_builder.utils.blender import install_door_it_addon, install_window_it_addon
from scene_builder.utils.room import render_structure_links
from scene_builder.utils.scene import recenter_scene

# Configure logging level (DEBUG shows all logs, INFO shows less)
# configure_logging(level="DEBUG")
# configure_logging(level="INFO")
# configure_logging(level="WARNING")
configure_logging(level="ERROR")


OUTPUT_DIR = Path("test_output/msd_to_blender")


def _enable_addons(enable_doors=True, enable_windows=True):
    """Enable Blender addons for doors and windows."""
    if enable_doors:
        addon_installed = install_door_it_addon()
        if addon_installed:
            print("✅ Door It! Interior addon enabled - doors will be created")
        else:
            print("⛔️ Door It! Interior addon not available - only cutouts will be created")
    if enable_windows:
        addon_installed = install_window_it_addon()
        if addon_installed:
            print("✅ Window It! addon enabled - windows will be created")
        else:
            print("⛔️ Window It! addon not available - only cutouts will be created")


def _collect_building_floors(
    loader: MSDLoader, building_id: int, floor_filter: Optional[str] = None
):
    apartments = loader.get_apartments_in_building(building_id, floor_id=floor_filter)
    floors: dict[str, list[tuple[str, object]]] = defaultdict(list)

    for apt_id in apartments:
        graph = loader.create_graph(apt_id, format="sb")
        floor_id = graph.graph.get("floor_id")
        floors[floor_id].append((apt_id, graph))
    return floors


def _render_structure_links_for_rooms(rooms_dict: list, output_path: Path) -> bool:
    """Extract structures/attachments from dict rooms and render links image.

    Returns True if an image was rendered, False if there were no structures.
    """
    structures: list = []
    attachments: list[tuple[str, str]] = []
    for room in rooms_dict or []:
        r_structs = room.get("structure") if isinstance(room, dict) else None
        if not r_structs:
            continue
        for s in r_structs:
            structures.append(s)
            attachments.append((s.get("id"), room.get("id")))

    if not structures:
        return False

    render_structure_links(rooms_dict, structures, attachments, output_path)
    print(f"   ✓ Saved structure links viz: {output_path.name}")
    return True


def test_msd_to_blender(
    enable_addons: bool = True,
    door_cutout: bool = True,
    window_cutout: bool = True,
    entire_floor: bool = False,
    building_id: Optional[int] = None,  # random by default
    floor_id: Optional[str] = None,
    align_rotation: bool = True,
    render_links: bool = False,
    enable_doors: bool = True,
    enable_windows: bool = True,
    render_doors: bool = False,
    render_windows: bool = False,
    keep_cutters_visible: bool = False,
):
    loader = MSDLoader()

    if enable_addons:
        _enable_addons(enable_doors=enable_doors, enable_windows=enable_windows)

    # Load the specified or a random building from MSD
    if building_id is None:
        building_id = loader.get_random_building()
    print(f"Loading building {building_id}...\n")

    # Get apartments for each floor
    floors = _collect_building_floors(loader, building_id, floor_filter=floor_id)
    print(f"Found {sum(len(v) for v in floors.values())} apartments across {len(floors)} floors\n")

    # Process each floor
    for floor_id, apt_graphs in floors.items():
        print(f"Floor {floor_id}: {len(apt_graphs)} apartments")

        if entire_floor:
            # Aggregate all rooms across apartments into a single floor-level scene
            all_rooms = []
            for _, graph in apt_graphs:
                apt_scene = loader.apt_graph_to_scene(graph)
                all_rooms.extend(apt_scene.rooms)

            # Build a combined floor Scene, normalize, and decode once
            floor_scene = Scene(
                category="residential",
                tags=["msd", "floor"],
                height_class="single_story",
                rooms=all_rooms,
            )

            scene_data = recenter_scene(floor_scene, rotate=align_rotation)
            rooms_dict = scene_data.get("rooms", [])

            if render_links:
                links_img = OUTPUT_DIR / f"msd_building_{building_id}_floor_{floor_id}_structure_links.png"
                _render_structure_links_for_rooms(rooms_dict, links_img)

            blender.parse_scene_definition(scene_data)

            # Create walls for entire floorplan at once
            walls_created_total = blender.create_room_walls(
                rooms_dict,
                door_cutouts=door_cutout,
                window_cutouts=window_cutout,
                render_doors=render_doors,
                render_windows=render_windows,
                keep_cutters_visible=keep_cutters_visible,
            )
            if walls_created_total > 0:
                print(f"   ✓ Created {walls_created_total} room walls for floor {floor_id}")

            # Save floor-level file and render once
            output_file = OUTPUT_DIR / (
                f"msd_building_{building_id}_floor_{floor_id}_"
                f"door_cutouts={door_cutout}_window_cutouts={window_cutout}.blend"
            )
            blender.save_scene(str(output_file))
            print(f"   ✓ Saved: {output_file.name}")

            render_path = blender.create_scene_visualization(
                resolution=1024,
                format="PNG",
                filename=f"msd_building_{building_id}_floor_{floor_id}",
                output_dir=str(OUTPUT_DIR),
                view="top_down",
                show_grid=False,
            )
            print(f"   ✓ Rendered: {render_path.name}")

        else:
            # Default: apartment-per-file workflow (existing behavior)
            for apt_id, graph in apt_graphs:
                apt_scene = loader.apt_graph_to_scene(graph)

                scene_data = recenter_scene(apt_scene, rotate=align_rotation)
                rooms_dict = scene_data.get("rooms", [])

                if render_links:
                    apt_prefix = str(apt_id)[:8]
                    links_img = OUTPUT_DIR / (
                        f"msd_building_{building_id}_floor_{floor_id}_apt_{apt_prefix}_structure_links.png"
                    )
                    _render_structure_links_for_rooms(rooms_dict, links_img)

                blender.parse_scene_definition(scene_data)
                walls_created = blender.create_room_walls(
                    rooms_dict,
                    door_cutouts=door_cutout,
                    window_cutouts=window_cutout,
                    render_doors=render_doors,
                    render_windows=render_windows,
                    keep_cutters_visible=keep_cutters_visible,
                )
                if walls_created > 0:
                    print(f"   ✓ Created {walls_created} room walls for {apt_id}")

                # Save file and and create render
                apt_prefix = str(apt_id)[:8]
                output_file = OUTPUT_DIR / (
                    f"msd_building_{building_id}_floor_{floor_id}_apt_{apt_prefix}_"
                    f"door_cutouts={door_cutout}_window_cutouts={window_cutout}.blend"
                )
                blender.save_scene(str(output_file))
                print(f"   ✓ Saved: {output_file.name}")

                render_path = blender.create_scene_visualization(
                    resolution=1024,
                    format="PNG",
                    filename=f"msd_building_{building_id}_floor_{floor_id}_apt_{apt_prefix}",
                    output_dir=str(OUTPUT_DIR),
                    view="top_down",
                    show_grid=False,
                )
                print(f"   ✓ Rendered: {render_path.name}")


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Example: Test with window rendering enabled
    test_msd_to_blender(
        enable_addons=True,
        door_cutout=True,
        window_cutout=True,
        entire_floor=True,
        building_id=2801,
        # building_id=2144,
        # building_id=1421,
        # building_id=2802,
        floor_id=None,
        align_rotation=True,
        render_links=False,
        enable_doors=False,
        enable_windows=True,
        render_doors=False,
        render_windows=True,
        keep_cutters_visible=True,
    )
    # Uncomment to test other configurations:
    # test_msd_to_blender(render_windows=True)
    # test_msd_to_blender(door_cutout=False)
    # test_msd_to_blender(window_cutout=False)
    # test_msd_to_blender(door_cutout=False, window_cutout=False)
    # test_msd_to_blender(render_doors=True, render_windows=True)  # Enable both doors and windows
