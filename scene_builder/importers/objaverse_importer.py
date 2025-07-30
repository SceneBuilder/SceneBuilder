import objaverse
from typing import Dict, Any

def import_object(object_uid: str) -> Dict[str, Any]:
    """
    Imports a 3D object from the Objaverse dataset.

    Args:
        object_uid: The unique identifier of the object to import.

    Returns:
        A dictionary representing the 3D model.
    """
    print(f"Importing object: {object_uid}")
    
    # Load the object from Objaverse
    objects = objaverse.load_objects(uids=[object_uid])
    
    # Return the object data
    return objects.get(object_uid)

if __name__ == "__main__":
    # This is an example of how you might use this script.
    # You would first need to have an object UID from the Objaverse dataset.
    
    # Example object UID:
    example_uid = "a0e6a2b0-b2ad-44a6-8cec-313a7a7c4b94" # A red sofa
    
    # Import the object
    object_data = import_object(example_uid)
    
    if object_data:
        print("\nObject imported successfully:")
        print(object_data)