import objaverse
import tempfile
from typing import Dict, Any


def import_object(object_uid: str) -> str:
    """
    Imports a 3D object from the Objaverse dataset and returns the path to the downloaded file.

    Args:
        object_uid: The unique identifier of the object to import.

    Returns:
        The path to the downloaded 3D model file.
    """
    print(f"Importing object: {object_uid}")

    # Create a temporary directory to store the downloaded object
    download_dir = tempfile.mkdtemp()

    # Load the object from Objaverse, which will also download it
    objects = objaverse.load_objects(uids=[object_uid], download_path=download_dir)

    # Get the path to the downloaded object
    object_path = objects.get(object_uid)

    # Return the object path
    return object_path


if __name__ == "__main__":
    # This is an example of how you might use this script.
    # You would first need to have an object UID from the Objaverse dataset.

    # Example object UID:
    example_uid = "a0e6a2b0-b2ad-44a6-8cec-313a7a7c4b94"  # A red sofa

    # Import the object
    object_path = import_object(example_uid)

    if object_path:
        print(f"\nObject downloaded successfully to: {object_path}")
