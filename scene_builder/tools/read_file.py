import mimetypes
import os

from pydantic_ai import BinaryContent


def read_media_file(file_path: str) -> BinaryContent:
    """
    Reads a media file from a given path and returns it as a BinaryContent object.

    This tool is a simplified, direct-access version of `read_file` for when
    the content is known to be binary, such as an image or video. It raises
    exceptions on failure.

    Args:
        file_path: The local path to the media file.

    Returns:
        A BinaryContent object containing the binary data.

    Raises:
        FileNotFoundError: If the file does not exist.
        IOError: If the file cannot be read.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found at path: {file_path}")

    try:
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"

        with open(file_path, "rb") as f:
            raw_content = f.read()

        return BinaryContent(data=raw_content, media_type=mime_type)

    except (IOError, OSError) as e:
        raise IOError(f"Could not read file: {e}") from e
