import mimetypes
import os
import re
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent


# A set of common media file extensions to look for.
MEDIA_EXTENSIONS = {
    # Images
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tiff",
    ".webp",
    ".svg",
    # Video
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    # Audio
    ".mp3",
    ".wav",
    ".ogg",
    ".flac",
    ".aac",
    # Documents
    ".pdf",
    ".doc",
    ".docx",
}

T = TypeVar("T", bound=BaseModel)


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
                    with open(value, "rb") as f:
                        content = f.read()

                    # Guess the MIME type from the filename
                    mime_type, _ = mimetypes.guess_type(str(value))

                    return BinaryContent(
                        data=content, media_type=mime_type or "application/octet-stream"
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


def transform_markdown_to_messages(markdown: str) -> list[str | BinaryContent]:
    """
    Converts markdown text to a list of messages, replacing image references with BinaryContent.

    Parses markdown text line by line, detecting image references in the format
    ![alt_text](file_path) and converting them to BinaryContent objects when the
    referenced file exists and is a supported media type. Non-image lines are
    returned as strings unchanged.

    Args:
        markdown (str): Markdown text containing potential image references

    Returns:
        list[str | BinaryContent]: List where image references are replaced with
        BinaryContent objects and other lines remain as strings
    """
    lines = markdown.split("\n")

    for i, line in enumerate(lines):
        match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line)
        if match:
            alt_text, path = match.groups()
            # Get file extension from the actual path
            _, extension = os.path.splitext(path.lower())
            if extension in MEDIA_EXTENSIONS and os.path.exists(path):
                # Read the file in binary mode
                with open(path, "rb") as f:
                    content = f.read()
                mime_type, _ = mimetypes.guess_type(path)
                lines[i] = BinaryContent(
                    data=content,
                    media_type=mime_type or "application/octet-stream",
                    identifier=alt_text,
                )

    return lines


def extract_media_from_value(value: Any, identifier_prefix: str = "") -> list[BinaryContent]:
    """
    Recursively extract media files from a value and convert them to BinaryContent.

    Reuses the logic from transform_paths_to_binary but collects BinaryContent objects
    instead of transforming in place. This is useful for putting media in user prompts
    rather than system prompts.

    Args:
        value: The value to extract media from (typically a Pydantic model)
        identifier_prefix: Prefix for BinaryContent identifiers

    Returns:
        List of BinaryContent objects for all media files found
    """
    media_content = []

    def _recursive_extract(val: Any, prefix: str = "") -> None:
        # Base Case: The value is a string or Path, check if it's a media file path
        if isinstance(val, (str, Path)):
            try:
                # Check if the file extension is in our list of media types
                _, extension = os.path.splitext(str(val).lower())
                if extension in MEDIA_EXTENSIONS and os.path.exists(val):
                    # Read the file in binary mode
                    with open(val, "rb") as f:
                        content = f.read()

                    # Guess the MIME type from the filename
                    mime_type, _ = mimetypes.guess_type(str(val))

                    # Create identifier from path
                    identifier = f"{prefix}_{Path(val).name}" if prefix else Path(val).name

                    media_content.append(BinaryContent(
                        data=content,
                        media_type=mime_type or "application/octet-stream",
                        identifier=identifier
                    ))
            except (IOError, OSError) as e:
                print(f"Warning: Could not read file '{val}': {e}")

        # Recursive Step 1: The value is a Pydantic model
        elif isinstance(val, BaseModel):
            for field_name, field_value in val.__iter__():
                new_prefix = f"{prefix}_{field_name}" if prefix else field_name
                _recursive_extract(field_value, new_prefix)

        # Recursive Step 2: The value is a list
        elif isinstance(val, list):
            for i, item in enumerate(val):
                new_prefix = f"{prefix}_{i}" if prefix else str(i)
                _recursive_extract(item, new_prefix)

        # Recursive Step 3: The value is a dictionary
        elif isinstance(val, dict):
            for k, v in val.items():
                new_prefix = f"{prefix}_{k}" if prefix else str(k)
                _recursive_extract(v, new_prefix)

    _recursive_extract(value, identifier_prefix)
    return media_content


async def run_agent_multimodal(
    agent: Agent,
    prompt: str | list,
    *,
    deps: T | None = None,
    **kwargs
) -> Any:
    """
    Run an agent with automatic extraction of media files into user prompts.

    This function extracts media files (like viz images) from dependencies and
    includes them in the user prompt, which is the correct way to handle binary
    content according to Pydantic AI documentation.

    Args:
        agent: The Pydantic AI agent to run
        prompt: The prompt to send to the agent
        deps: Optional dependencies (Pydantic model) that may contain media paths
        **kwargs: Additional arguments to pass to agent.run()

    Returns:
        The agent's response
    """
    if deps is None:
        return await agent.run(prompt, **kwargs)

    # Extract all media from deps using the same logic as transform_paths_to_binary
    media_content = extract_media_from_value(deps, "deps")

    if media_content:
        # Combine text prompt with media - ensure prompt is a list
        if isinstance(prompt, str):
            user_prompt_parts = [prompt] + media_content
        else:
            user_prompt_parts = list(prompt) + media_content
        # Pass original deps since media is now in prompt
        return await agent.run(user_prompt_parts, deps=deps, **kwargs)
    else:
        return await agent.run(prompt, deps=deps, **kwargs)
