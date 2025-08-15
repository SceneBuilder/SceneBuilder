from scene_builder.utils.conversions import pydantic_from_yaml
from scene_builder.decoder.blender import parse_scene_definition, save_scene


def test_scene_building():
    scene_data = pydantic_from_yaml("scenes/generated_scene.yaml")
    parse_scene_definition(scene_data)
    save_scene("output.blend")
    print("\nBlender scene created successfully from YAML data.")


if __name__ == "__main__":
    test_scene_building()
