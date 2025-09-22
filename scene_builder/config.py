"""Configuration settings for SceneBuilder."""

from pydantic import BaseModel

# General
DEBUG: bool = False

# Dependencies
# graphics-db
GDB_API_BASE_URL = "http://localhost:2692/api"

# Logging
# Pydantic Logfire
LOGFIRE_SERVICE_NAME = "scene-builder"

class GenerationConfig(BaseModel):
    """Configuration for the generation process."""

    enable_visual_feedback: bool = True
