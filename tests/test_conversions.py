import unittest
import yaml
from pathlib import Path
from pydantic import BaseModel

from scene_builder.utils.conversions import pydantic_from_yaml


class TestPydanticFromYaml(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("test_temp")
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        for item in self.test_dir.iterdir():
            item.unlink()
        self.test_dir.rmdir()

    def test_load_simple_model(self):
        class SimpleModel(BaseModel):
            name: str
            value: int

        data = {"name": "test", "value": 123}
        file_path = self.test_dir / "simple.yaml"
        with open(file_path, "w") as f:
            yaml.dump(data, f)

        model_instance = pydantic_from_yaml(file_path, SimpleModel)
        self.assertIsInstance(model_instance, SimpleModel)
        self.assertEqual(model_instance.name, "test")
        self.assertEqual(model_instance.value, 123)


if __name__ == "__main__":
    unittest.main()
