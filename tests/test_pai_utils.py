import os
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent

from scene_builder.utils.pai import transform_paths_to_binary


class ImageQuery(BaseModel):
    image_path: Any
    prompt: str


def test_transform_paths_to_binary_with_pydantic_ai(llm_agent: Agent):
    # 1. Setup
    agent = llm_agent

    # Define the query with a path to our dummy image
    image_path = Path("test_assets/images/red_pixel.png")
    query = ImageQuery(
        image_path=image_path,
        prompt="What color is this image?",
    )

    # 2. Transform the model instance
    transformed_query = transform_paths_to_binary(query)

    # 3. Run the agent with the transformed query
    # The agent expects a list of content parts
    agent.run([transformed_query.prompt, transformed_query.image_path])

    # 4. Assertions
    # Check that the image_path is now a BinaryContent object
    assert isinstance(transformed_query.image_path, BinaryContent)
    assert transformed_query.image_path.media_type == "image/png"

    # If using a mock, check that the LLM's run method was called with the correct data
    if isinstance(agent.llm, MagicMock):
        agent.llm.run.assert_called_once()
        call_args = agent.llm.run.call_args[0][0]

        # Verify the content passed to the mock LLM
        assert call_args[0] == "What color is this image?"
        assert isinstance(call_args[1], BinaryContent)
        assert call_args[1].media_type == "image/png"

        # Verify the image data is correct
        with open(image_path, "rb") as f:
            expected_data = f.read()
        assert call_args[1].data == expected_data


if __name__ == "__main__":
    agent = Agent("gpt-5-nano")
    test_transform_paths_to_binary_with_pydantic_ai(agent)
