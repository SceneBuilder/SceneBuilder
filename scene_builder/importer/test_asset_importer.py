import os
from pathlib import Path
import random
import tempfile
from typing import Any, Dict, List

from scene_builder.definition.scene import ObjectBlueprint

# Mock database of assets available for testing.
TEST_ASSETS: Dict[str, List[Dict[str, Any]]] = {
    "sofa": [
        {
            "source_id": "602ed4eef5844908960e33f0d86e80b4",
            "name": "Red Sofa",
            "description": "A comfortable red sofa.",
            "source": "test_asset",
            "tags": ["sofa", "red"],
        }
    ],
    "table": [
        {
            "source_id": "67cc4558a0e74bb6be61a1af1eb13b66",
            "name": "A wooden table",
            "description": "An antique table with drawers",
            "source": "test_asset",
            "tags": ["table", "wooden", "drawers"],
        }
    ],
    "classroom_table": [
        {
            "source_id": "00aacefe3ffc4934981bb2d1e9b5a076",
            "name": "Classroom Table-Chair",
            "description": "A table-chair combo suitable for classrooms.",
            "source": "test_asset",
            "tags": ["table", "chair", "classroom"],
        }
    ],
    "computer": [
        {
            "source_id": "419558f3e8694b6d98e6dcb6743528b6",
            "name": "Computer, Keyboard, Mouse",
            "description": "",
            "source": "test_asset",
            "tags": ["computer", "desktop furniture", "retro"],
        }
    ],
    "drawer": [
        {
            "source_id": "032547718b454e1ba79d502eaf49e0f9",
            "name": "Multi-part drawer",
            "description": "",
            "source": "test_asset",
            "tags": ["antique"],
        }
    ],
    "bookcase": [
        {
            "source_id": "d48a42e91c5d4716a8c254addf8c9d99",
            "name": "Bookcase",
            "description": "",
            "source": "test_asset",
            "tags": [],
        }
    ],
}


def search_test_asset(object_category: str) -> ObjectBlueprint:
    """
    Imports a 3D object from the test assets.

    Args:
        object_uid: The id of the object to import.

    Returns:
        The path to the dummy 3D model file.
    """
    relevant_objects = TEST_ASSETS[object_category]
    random_index = random.randint(0, len(relevant_objects) - 1)
    object = relevant_objects[random_index]

    return ObjectBlueprint(
        source_id=object["source_id"],
        name=object["name"],
        description=object["description"],
        source=object["source"],
    )


def import_test_asset(id: str) -> str:
    return str(Path(f"test_assets/objects/{id}.glb"))
