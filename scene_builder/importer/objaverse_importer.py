import requests
from pathlib import Path

import objaverse

from scene_builder.config import GDB_API_BASE_URL
from scene_builder.logging import logger

def import_object(object_uid: str, source="cache") -> str:
    """
    Imports a 3D object from the Objaverse dataset and returns the path to the downloaded file.

    Args:
        object_uid: The unique identifier of the object to import.

    Returns:
        The path to the downloaded 3D model file, or None if download fails.
    """
    print(f"Importing objaverse object: {object_uid}")

    if source == "cache":
        response = requests.get(
            f"{GDB_API_BASE_URL}/v0/assets/locate/{object_uid}/glb",
        )
        path = response.json()["path"]
        assert Path(path).exists()
        # logger.debug(f"[importer/objaverse]: located asset at {path}")
        return path

    elif source == "objaverse":
        print(f"Downloading object {object_uid} from Objaverse...")
        downloaded_objects: dict[str, str] = objaverse.load_objects(
            uids=[object_uid], download_processes=1
        )

        # The path from the download
        original_path = downloaded_objects.get(object_uid)
        return original_path
    else:
        print(f"Failed to download object: {object_uid}")
        return None
