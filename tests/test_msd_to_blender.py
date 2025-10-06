#!/usr/bin/env python3
"""
Tests: MSD Building → SceneBuilder → Blender (.blend file)
"""

import sys
from pathlib import Path
from collections import defaultdict
import bpy
import bmesh

sys.path.append(str(Path(__file__).parent.parent))

from scene_builder.msd_integration.loader import MSDLoader
from scene_builder.msd_integration.converter import GraphToSceneConverter
from scene_builder.decoder import blender


def get_apartment_outline(rooms):
    """Extract outline for a single apartment from its rooms."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    if not rooms:
        return []

    polygons = []
    for room in rooms:
        if len(room.boundary) >= 3:
            coords = [(p.x, p.y) for p in room.boundary]
            try:
                poly = Polygon(coords)
                if poly.is_valid:
                    polygons.append(poly)
            except Exception:
                continue

    if not polygons:
        return []

    unified = unary_union(polygons)

    if hasattr(unified, "exterior"):
        outline = list(unified.exterior.coords[:-1])
    elif hasattr(unified, "geoms"):
        largest = max(unified.geoms, key=lambda p: p.area)
        outline = list(largest.exterior.coords[:-1])
    else:
        return []

    return outline


def create_outline_blend(
    apartment_outlines, output_path, wall_height=2.7, wall_thickness=0.001
):
    """Create a .blend file with extruded walls for all apartments on the floor."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    # Create separate wall object for each apartment
    for apt_idx, (apt_id, outline_points) in enumerate(apartment_outlines):
        if not outline_points:
            continue

        mesh = bpy.data.meshes.new(f"Walls_Apt_{apt_id}")
        obj = bpy.data.objects.new(f"Walls_Apt_{apt_id}", mesh)
        bpy.context.collection.objects.link(obj)

        bm = bmesh.new()

        # bottom vertices
        bottom_verts = []
        for x, y in outline_points:
            v = bm.verts.new((x, y, 0))
            bottom_verts.append(v)

        # top vertices
        top_verts = []
        for x, y in outline_points:
            v = bm.verts.new((x, y, wall_height))
            top_verts.append(v)

        # wall faces
        num_verts = len(bottom_verts)
        for i in range(num_verts):
            next_i = (i + 1) % num_verts

            # outer face
            face = bm.faces.new(
                [bottom_verts[i], bottom_verts[next_i], top_verts[next_i], top_verts[i]]
            )
            face.normal_update()

        # thickness
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

        # solidify modifier for wall thickness
        solidify = obj.modifiers.new(name="Solidify", type="SOLIDIFY")
        solidify.thickness = wall_thickness
        solidify.offset = 0  # Center thickness

        # apply modifier
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier="Solidify")

    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    print(f"   ✓ Saved walls: {output_path.name}")


def test_msd_to_blender():
    loader = MSDLoader()
    converter = GraphToSceneConverter()

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
        print(f"🏢 Floor {floor_id}: {len(apt_graphs)} apartments")

        all_rooms = []
        apartment_rooms = []
        for apt_id, graph in apt_graphs:
            rooms = converter.convert_graph_to_rooms(graph)
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

        blender.parse_scene_definition(scene_data)

        output_file = output_dir / f"msd_building_{building_id}_floor_{floor_id}.blend"
        blender.save_scene(str(output_file))
        print(f"   ✓ Saved: {output_file.name}")

        render_path = blender.render_top_down(str(output_dir))
        print(f"   ✓ Rendered: {Path(render_path).name}")

        apartment_outlines = []
        for apt_id, rooms in apartment_rooms:
            outline = get_apartment_outline(rooms)
            if outline:
                apartment_outlines.append((apt_id, outline))

        if apartment_outlines:
            walls_file = (
                output_dir / f"msd_building_{building_id}_floor_{floor_id}_walls.blend"
            )
            create_outline_blend(apartment_outlines, walls_file)

        print()


if __name__ == "__main__":
    test_msd_to_blender()
