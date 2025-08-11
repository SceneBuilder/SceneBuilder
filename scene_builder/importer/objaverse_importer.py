import objaverse
import tempfile
import os


def import_object(object_uid: str) -> str:
    """
    Imports a 3D object from the Objaverse dataset and returns the path to the downloaded file.

    Args:
        object_uid: The unique identifier of the object to import.

    Returns:
        The path to the downloaded 3D model file, or None if download fails.
    """
    print(f"Importing objaverse object: {object_uid}")

    # Use a consistent temporary directory for caching
    download_dir = os.path.join(tempfile.gettempdir(), "scene_builder_objaverse")
    os.makedirs(download_dir, exist_ok=True)

    # Check if the object is already downloaded
    object_path = os.path.join(download_dir, f"{object_uid}.glb")
    if os.path.exists(object_path):
        print(f"Found cached object at: {object_path}")
        return object_path

    print(f"Downloading object {object_uid} from Objaverse...")
    # load_objects downloads the object to a specific path
    # and returns a dictionary mapping the UID to the path.
    downloaded_objects = objaverse.load_objects(
        uids=[object_uid], download_processes=1
    )

    # The path from the download
    original_path = downloaded_objects.get(object_uid)

    if original_path:
        # Move the file to our consistent cache directory
        try:
            os.rename(original_path, object_path)
            print(f"Object cached successfully to: {object_path}")
            return object_path
        except OSError as e:
            print(f"Error moving object to cache: {e}. Using original path.")
            return original_path
    else:
        print(f"Failed to download object: {object_uid}")
        return None
