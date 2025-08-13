import os
import random
import tempfile
from typing import Any, Dict, List

from scene_builder.definition.scene import ObjectBlueprint

# Mock database of assets available for testing.
TEST_ASSETS: Dict[str, List[Dict[str, Any]]] = {
    "sofa": [
        {
            "id": "000074a334c541878360457c672b6c2e",
            "name": "Modern Red Sofa",
            "description": "A comfortable red sofa with a modern design.",
            "source": "objaverse",
            "tags": ["sofa", "red", "modern"],
        }
    ],
    "table": [
        {
            "id": "objaverse-table-456",
            "name": "Wooden Coffee Table",
            "description": "A rustic wooden coffee table.",
            "source": "objaverse",
            "tags": ["table", "wood", "rustic"],
        }
    ],
    "classroom_table": [
        {
            "id": "00aacefe3ffc4934981bb2d1e9b5a076",
            "name": "Classroom Table-Chair",
            "description": "",
            "source": "objaverse",
            "tags": ["table", "chair", "classroom"],
        }
    ],
    "computer": [
        {
            "id": "419558f3e8694b6d98e6dcb6743528b6",
            "name": "Computer, Keyboard, Mouse",
            "description": "",
            "source": "objaverse",
            "tags": ["computer", "desktop furniture", "retro"],
        }
    ],
    "drawer": [
        {
            "id": "032547718b454e1ba79d502eaf49e0f9",
            "name": "Multi-part drawer",
            "description": "",
            "source": "objaverse",
            "tags": ["antique"],
        }
    ],
    "bookcase": [
        {
            "id": "d48a42e91c5d4716a8c254addf8c9d99",
            "name": "Bookcase",
            "description": "",
            "source": "objaverse",
            "tags": [],
        }
    ],
}


def import_test_asset(object_category: str) -> ObjectBlueprint:
    """
    Imports a 3D object from the test assets.

    Args:
        object_uid: The id of the object to import.

    Returns:
        The path to the dummy 3D model file.
    """
    relevant_objects = TEST_ASSETS[object_category]
    random_index = random.randint(0, len(relevant_objects)-1)
    object = relevant_objects[random_index]

    return ObjectBlueprint(
        id=object["id"],
        name=object["name"],
        description=object["description"],
        source=object["source"],
    )
