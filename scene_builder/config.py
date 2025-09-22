"""Configuration settings for SceneBuilder."""

import os
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# General
DEBUG: bool = False

# Dependencies
# graphics-db
GDB_API_BASE_URL = "http://localhost:2692/api"

# Logging
# Pydantic Logfire
LOGFIRE_SERVICE_NAME = os.getenv("LOGFIRE_SERVICE_NAME", "scene-builder")
LOGFIRE_TOKEN = os.getenv("LOGFIRE_TOKEN")

class GenerationConfig(BaseModel):
    """Configuration for the generation process."""

    enable_visual_feedback: bool = True
