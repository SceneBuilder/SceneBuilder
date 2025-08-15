import mimetypes
import os
from pathlib import Path
from typing import Any, List, Optional, Type, TypeVar

from pydantic import BaseModel, Field
from pydantic_ai.messages import BinaryContent

# --- 1. Define constants and the main transformation function ---

# A set of common media file extensions to look for.
MEDIA_EXTENSIONS = {
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg',
    # Video
    '.mp4', '.mov', '.avi', '.mkv', '.webm',
    # Audio
    '.mp3', '.wav', '.ogg', '.flac', '.aac',
    # Documents
    '.pdf', '.doc', '.docx'
}

T = TypeVar('T', bound=BaseModel)

def transform_paths_to_binary(model_instance: T) -> T:
    """
    Recursively transforms file paths in a Pydantic model to BinaryContent.

    This function traverses a Pydantic model instance, including nested models,
    lists, and dictionaries. It identifies string fields that are paths to
    common media files, reads those files, and replaces the path string
    with a BinaryContent object containing the file's data and MIME type.

    Args:
        model_instance: An instance of a Pydantic BaseModel.

    Returns:
        A new Pydantic model instance with file paths replaced by BinaryContent.
    """

    def _recursive_transform(value: Any) -> Any:
        """Helper function to perform the recursive transformation."""
        # Base Case: The value is a string or Path, check if it's a media file path
        if isinstance(value, (str, Path)):
            try:
                # Check if the file extension is in our list of media types
                _, extension = os.path.splitext(str(value).lower())
                if extension in MEDIA_EXTENSIONS and os.path.exists(value):
                    # Read the file in binary mode
                    with open(value, 'rb') as f:
                        content = f.read()

                    # Guess the MIME type from the filename
                    mime_type, _ = mimetypes.guess_type(str(value))

                    return BinaryContent(
                        data=content,
                        media_type=mime_type or 'application/octet-stream'
                    )
            except (IOError, OSError) as e:
                # If file is unreadable, return the original path
                # In a real application, you might want to log this error
                print(f"Warning: Could not read file '{value}': {e}")
                return value
            return value

        # Recursive Step 1: The value is a Pydantic model
        elif isinstance(value, BaseModel):
            # Create a dictionary of updates by transforming each field's value
            updates = {
                field_name: _recursive_transform(field_value)
                for field_name, field_value in value.__iter__()
            }
            # Return a new model instance with the updated fields
            return value.model_copy(update=updates)

        # Recursive Step 2: The value is a list
        elif isinstance(value, list):
            return [_recursive_transform(item) for item in value]

        # Recursive Step 3: The value is a dictionary
        elif isinstance(value, dict):
            return {k: _recursive_transform(v) for k, v in value.items()}

        # If none of the above, return the value as is
        return value

    # Start the transformation on the top-level model instance
    return _recursive_transform(model_instance)

# --- 3. Example Usage ---

if __name__ == "__main__":
    from pathlib import Path

    # Create some dummy media files for the demonstration
    with open("profile_pic.jpg", "wb") as f:
        f.write(b"dummy_jpeg_data")
    with open("intro.mp4", "wb") as f:
        f.write(b"dummy_mp4_data")
    with open("resume.pdf", "wb") as f:
        f.write(b"dummy_pdf_data")

    # Define example Pydantic models, including nested and recursive structures
    class MediaItem(BaseModel):
        description: str
        file_path: str

    class UserProfile(BaseModel):
        username: str
        avatar_path: Any
        other_media: List[MediaItem]
        unrelated_field: int = 42

    class Project(BaseModel):
        project_name: str
        owner: UserProfile
        attachments: dict[str, str]

    # Create an instance of the Pydantic model with file paths
    project_data = Project(
        project_name="AI Agent Demo",
        owner=UserProfile(
            username="testuser",
            avatar_path=Path("profile_pic.jpg"),
            other_media=[
                MediaItem(description="My introduction video", file_path="intro.mp4"),
                MediaItem(description="A non-existent file", file_path="missing.png"),
            ]
        ),
        attachments={
            "main_resume": "resume.pdf",
            "cover_letter": "letter.txt" # This will not be transformed
        }
    )

    print("--- Original Pydantic Model ---")
    print(project_data.model_dump_json(indent=2))

    # Run the transformation function
    transformed_project = transform_paths_to_binary(project_data)

    print("\n--- Transformed Pydantic Model ---")
    # Note: The output will now show BinaryContent objects instead of paths.
    # Pydantic's default __repr__ for the model will be used.
    print(transformed_project)

    print("\n--- Verifying Transformed Content ---")
    print(f"Owner's Avatar: {transformed_project.owner.avatar_path}")
    print(f"First Media Item: {transformed_project.owner.other_media[0].file_path}")
    print(f"Resume Attachment: {transformed_project.attachments['main_resume']}")
    print(f"Untouched text file: {transformed_project.attachments['cover_letter']}")


    # Clean up the dummy files
    os.remove("profile_pic.jpg")
    os.remove("intro.mp4")
    os.remove("resume.pdf")
