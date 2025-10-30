from scene_builder.decoder.blender.blender import parse_scene_definition, save_scene
from scene_builder.definition.scene import Scene
from scene_builder.utils.conversions import pydantic_from_yaml


def test_scene_building():
    scene_data = pydantic_from_yaml("scenes/generated_scene.yaml", Scene)
    parse_scene_definition(scene_data)
    save_scene("output.blend")
    print("\nBlender scene created successfully from YAML data.")


if __name__ == "__main__":
    test_scene_building()

# NOTE: The test currently fails because some parts of the codebase use
#       dict as main state representation while others use Pydantic BaseModel.
# TODO: Make a decision on what to use primarily.
