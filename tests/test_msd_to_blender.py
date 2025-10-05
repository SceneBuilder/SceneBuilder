"""
Tests: MSD Apartment → SceneBuilder → Blender (.blend file)
"""

from scene_builder.decoder import blender
from scene_builder.msd_integration.loader import MSDLoader


def test_msd_to_blender():
    loader = MSDLoader()
    apartment_id = loader.get_random_apartment()
    graph = loader.create_graph(apartment_id)
    floor_plan_img = loader.render_floor_plan(graph)
    floor_plan_img_alt = loader.render_floor_plan(graph, node_size=225, edge_size=0, show_label=True)
    scene_data = loader.graph_to_scene_data(graph)

    # Parse scene definition in Blender
    blender.parse_scene_definition(scene_data)
    blender.save_scene(f"test_output/msd_apartment_{apartment_id[:8]}.blend")
    render_path = blender.render_top_down("test_output")


if __name__ == "__main__":
    test_msd_to_blender()
