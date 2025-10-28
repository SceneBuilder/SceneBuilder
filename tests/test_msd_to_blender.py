"""
Tests: MSD Building → SceneBuilder → Blender (.blend file)
"""

from collections import defaultdict
from pathlib import Path
from typing import Optional

from scene_builder.decoder import blender
from scene_builder.definition.scene import Scene
from scene_builder.msd_integration.loader import MSDLoader
from scene_builder.utils.room import render_structure_links


OUTPUT_DIR = Path("test_output/msd_to_blender")


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
    door_cutout: bool = True,
    window_cutout: bool = True,
    building_id: Optional[int] = None,  # random by default
    floor_id: Optional[str] = None,
    align_rotation: bool = True,
    render_links: bool = False,
):
    loader = MSDLoader()

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

        for apt_id, graph in apt_graphs:
            apt_scene_dict = loader.graph_to_scene_data(graph)
            apt_scene = Scene.model_validate(apt_scene_dict)  # cast to pydantic

            scene_data = blender.floorplan_to_origin(apt_scene, align_rotation=align_rotation)
            rooms_dict = scene_data.get("rooms", [])

            if render_links:
                apt_prefix = str(apt_id)[:8]
                links_img = OUTPUT_DIR / f"msd_building_{building_id}_floor_{floor_id}_apt_{apt_prefix}_structure_links.png"  # fmt:skip
                _render_structure_links_for_rooms(rooms_dict, links_img)

            blender.parse_scene_definition(scene_data)
            walls_created = blender.create_room_walls(rooms_dict, door_cutouts=door_cutout, window_cutouts=window_cutout)  # fmt:skip
            if walls_created > 0:
                print(f"   ✓ Created {walls_created} room walls for {apt_id}")

            # Save file and and create render
            apt_prefix = str(apt_id)[:8]
            output_file = OUTPUT_DIR / f"msd_building_{building_id}_floor_{floor_id}_apt_{apt_prefix}_door_cutouts={door_cutout}_window_cutouts={window_cutout}.blend"  # fmt:skip
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

    test_msd_to_blender(
        door_cutout=True,
        window_cutout=True,
        building_id=2144,
        floor_id=None,
        align_rotation=True,
        render_links=True,
    )
