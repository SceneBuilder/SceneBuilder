import os
import pytest
from pydantic_ai import BinaryContent
from scene_builder.tools.read_file import read_file, FileContent, read_media_file


@pytest.fixture
def text_file(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    return str(file_path)


@pytest.fixture
def binary_file(tmp_path):
    file_path = tmp_path / "test.bin"
    file_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return str(file_path)


def test_read_text_file(text_file):
    """Tests reading a plain text file."""
    result = read_file(text_file)
    assert isinstance(result, FileContent)
    assert result.file_name == "test.txt"
    assert result.mime_type == "text/plain"
    assert not result.is_binary
    assert result.content == "hello world"
    assert result.error is None


def test_read_binary_file(binary_file):
    """Tests reading a binary file."""
    result = read_file(binary_file)
    assert isinstance(result, FileContent)
    assert result.file_name == "test.bin"
    assert result.mime_type == "application/octet-stream"
    assert result.is_binary
    assert isinstance(result.content, BinaryContent)
    assert result.content.data == b"\x89PNG\r\n\x1a\n"
    assert result.error is None


def test_read_non_existent_file():
    """Tests reading a non-existent file."""
    result = read_file("non_existent_file.txt")
    assert isinstance(result, FileContent)
    assert result.file_name == "non_existent_file.txt"
    assert result.mime_type == "unknown"
    assert not result.is_binary
    assert result.content == ""
    assert "File not found" in result.error


def test_read_media_file(binary_file):
    """Tests reading a media file."""
    result = read_media_file(binary_file)
    assert isinstance(result, BinaryContent)
    assert result.data == b"\x89PNG\r\n\x1a\n"
    assert result.mime_type == "application/octet-stream"

def test_read_media_file_not_found():
    """Tests reading a non-existent media file."""
    with pytest.raises(FileNotFoundError):
        read_media_file("non_existent_file.bin")
