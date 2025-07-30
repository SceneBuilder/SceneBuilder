import objaverse
import tempfile
from typing import Dict, Any, List


def search_and_import_object(query: str, count: int = 1) -> List[str]:
    """
    Searches for and imports 3D objects from the Objaverse dataset based on a semantic query.

    Args:
        query: The semantic query to search for (e.g., "a red sofa").
        count: The number of objects to import.

    Returns:
        A list of paths to the downloaded 3D model files.
    """
    print(f"Searching for {count} object(s) matching: {query}")

    # Load LVIS annotations for all objects
    annotations = objaverse.load_lvis_annotations()

    # Find objects that match the query
    matching_uids = []
    for category, uids in annotations.items():
        if query in category:
            matching_uids.extend(uids)

    if not matching_uids:
        print(f"No objects found matching the query: {query}")
        return []

    # Import the first `count` matching objects
    imported_object_paths = []
    for uid in matching_uids[:count]:
        object_path = import_object(uid)
        if object_path:
            imported_object_paths.append(object_path)

    return imported_object_paths


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
    objects = objaverse.load_objects(uids=[object_uid])

    # Get the path to the downloaded object
    object_path = objects.get(object_uid)

    # Return the object path
    return object_path


if __name__ == "__main__":
    # This is an example of how you might use this script.

    # Example semantic query:
    search_query = "sofa"

    # Search for and import the object
    object_paths = search_and_import_object(search_query, count=1)

    if object_paths:
        for object_path in object_paths:
            print(f"\nObject downloaded successfully to: {object_path}")
