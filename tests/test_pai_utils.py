import os
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent

from scene_builder.config import TEST_ASSET_DIR
from scene_builder.utils.pai import (
    transform_paths_to_binary,
    transform_markdown_to_messages,
)


class ImageQuery(BaseModel):
    image_path: Any
    prompt: str


def test_transform_paths_to_binary_with_pydantic_ai(llm_agent: Agent):
    # Setup
    agent = llm_agent

    # Define the query with a path to our dummy image
    image_path = Path(f"{TEST_ASSET_DIR}/images/red_pixel.png")
    query = ImageQuery(
        image_path=image_path,
        prompt="What color is this image?",
    )

    # Transform the model instance
    transformed_query = transform_paths_to_binary(query)

    # Run the agent with the transformed query
    # The agent expects a list of content parts
    agent.run([transformed_query.prompt, transformed_query.image_path])

    # Assertions
    # Check that the image_path is now a BinaryContent object
    assert isinstance(transformed_query.image_path, BinaryContent)
    assert transformed_query.image_path.media_type == "image/png"

    # If using a mock, check that the LLM's run method was called with the correct data
    if isinstance(agent, MagicMock):
        agent.run.assert_called_once()
        call_args = agent.run.call_args[0][0]

        # Verify the content passed to the mock LLM
        assert call_args[0] == "What color is this image?"
        assert isinstance(call_args[1], BinaryContent)
        assert call_args[1].media_type == "image/png"

        # Verify the image data is correct
        with open(image_path, "rb") as f:
            expected_data = f.read()
        assert call_args[1].data == expected_data


def test_transform_paths_to_binary_basic():
    """Basic test for transform_paths_to_binary with temporary files."""
    # Create some dummy media files for the demonstration
    with open("profile_pic.jpg", "wb") as f:
        f.write(b"dummy_jpeg_data")
    with open("intro.mp4", "wb") as f:
        f.write(b"dummy_mp4_data")
    with open("resume.pdf", "wb") as f:
        f.write(b"dummy_pdf_data")

    try:
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
                    MediaItem(
                        description="My introduction video", file_path="intro.mp4"
                    ),
                    MediaItem(
                        description="A non-existent file", file_path="missing.png"
                    ),
                ],
            ),
            attachments={
                "main_resume": "resume.pdf",
                "cover_letter": "letter.txt",  # This will not be transformed
            },
        )

        # Run the transformation function
        transformed_project = transform_paths_to_binary(project_data)

        # Verify transformations
        assert isinstance(transformed_project.owner.avatar_path, BinaryContent)
        assert transformed_project.owner.avatar_path.media_type == "image/jpeg"

        assert isinstance(
            transformed_project.owner.other_media[0].file_path, BinaryContent
        )
        assert (
            transformed_project.owner.other_media[0].file_path.media_type == "video/mp4"
        )

        # Non-existent file should remain as string
        assert isinstance(transformed_project.owner.other_media[1].file_path, str)

        assert isinstance(transformed_project.attachments["main_resume"], BinaryContent)
        assert (
            transformed_project.attachments["main_resume"].media_type
            == "application/pdf"
        )

        # Text file should remain as string
        assert isinstance(transformed_project.attachments["cover_letter"], str)

    finally:
        # Clean up the dummy files
        for file in ["profile_pic.jpg", "intro.mp4", "resume.pdf"]:
            if os.path.exists(file):
                os.remove(file)


def test_transform_markdown_to_messages():
    """Test transform_markdown_to_messages function with real objaverse thumbnail data."""
    # Test markdown content with the provided objaverse thumbnail
    markdown_content = """### 7bbfc196af03445fa335aa1160672a53

**Thumbnails**:

Isometric:

![thumbnail_for_7bbfc196af03445fa335aa1160672a53](/media/ycho358/Expansion/.cache/huggingface/datasets/datasets--allenai--objaverse/snapshots/21e4e142159e2153706c23a3a02e55cec5591cea/glbs/000-141/7bbfc196af03445fa335aa1160672a53_scaled.png)

**Metadata**:

{'uid': '7bbfc196af03445fa335aa1160672a53', 'dimensions': {'x': 2.08, 'y': 0.82, 'z': 0.9}}"""

    # Convert markdown to messages
    messages = transform_markdown_to_messages(markdown_content)

    # Verify the result
    assert isinstance(messages, list)
    assert len(messages) != 0

    # Check that the image line was converted to BinaryContent
    image_line_index = 6  # The line with the image markdown
    assert isinstance(messages[image_line_index], BinaryContent)
    assert messages[image_line_index].media_type == "image/png"
    assert (
        messages[image_line_index].identifier
        == "thumbnail_for_7bbfc196af03445fa335aa1160672a53"
    )

    # Check that other lines remain as strings
    assert isinstance(messages[0], str)  # Title line
    assert isinstance(messages[2], str)  # "**Thumbnails**:" line
    assert isinstance(messages[8], str)  # Metadata line

    # Test with markdown that has no images
    text_only_markdown = "This is just text\nWith no images"
    text_messages = transform_markdown_to_messages(text_only_markdown)
    assert len(text_messages) == 2
    assert all(isinstance(msg, str) for msg in text_messages)


def test_vlm_object_description_with_markdown(llm_agent: Agent):
    """Test using VLM to describe an object from objaverse thumbnail via markdown conversion."""
    # Create a VLM agent for object description
    agent = llm_agent

    prompt = "Please describe this 3D object. What type of object is this? What are its key visual features?:"
    
    # Markdown content with the objaverse thumbnail
    markdown_content = """### 7bbfc196af03445fa335aa1160672a53

**Thumbnails**:

Isometric:

![thumbnail_for_7bbfc196af03445fa335aa1160672a53](/media/ycho358/Expansion/.cache/huggingface/datasets/datasets--allenai--objaverse/snapshots/21e4e142159e2153706c23a3a02e55cec5591cea/glbs/000-141/7bbfc196af03445fa335aa1160672a53_scaled.png)

**Metadata**:

{'uid': '7bbfc196af03445fa335aa1160672a53', 'dimensions': {'x': 2.08, 'y': 0.82, 'z': 0.9}}

"""

    # Convert markdown to messages with BinaryContent
    messages = transform_markdown_to_messages(prompt + markdown_content)

    # Verify the image was converted to BinaryContent
    image_message = messages[6]  # The image line
    assert isinstance(image_message, BinaryContent)
    assert image_message.media_type == "image/png"

    # Run the VLM agent with the converted messages
    result = agent.run_sync(messages)

    print(f"Result: {result.output}")

    # Verify the agent was called with the correct multimodal content
    if isinstance(agent, MagicMock):
        agent.run.assert_called_once()
        call_args = agent.run.call_args[0][0]

        # Check that we have text and image content
        text_parts = [msg for msg in call_args if isinstance(msg, str)]
        binary_parts = [msg for msg in call_args if isinstance(msg, BinaryContent)]

        assert len(text_parts) >= 1  # At least the description prompt
        assert len(binary_parts) == 1  # Exactly one image
        assert binary_parts[0].media_type == "image/png"

        # Verify the image data matches the original file
        image_path = "/media/ycho358/Expansion/.cache/huggingface/datasets/datasets--allenai--objaverse/snapshots/21e4e142159e2153706c23a3a02e55cec5591cea/glbs/000-141/7bbfc196af03445fa335aa1160672a53_scaled.png"
        if os.path.exists(image_path):
            with open(image_path, "rb") as f:
                expected_data = f.read()
            assert binary_parts[0].data == expected_data


if __name__ == "__main__":
    agent = Agent("gpt-5-nano")
    # test_transform_paths_to_binary_with_pydantic_ai(agent)
    # test_transform_paths_to_binary_basic()
    test_transform_markdown_to_messages()
    test_vlm_object_description_with_markdown(agent)
