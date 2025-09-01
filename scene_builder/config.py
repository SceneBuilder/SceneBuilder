"""Configuration settings for SceneBuilder."""

from pydantic import BaseModel

# General
DEBUG: bool = False

# Logfire
LOGFIRE_SERVICE_NAME = "scene-builder"


class GenerationConfig(BaseModel):
    """Configuration for the generation process."""

    enable_visual_feedback: bool = True
