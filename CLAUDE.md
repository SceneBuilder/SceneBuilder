# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Installation
```bash
pip install .
# For development dependencies:
pip install .[dev]
```

### Running the Main Application
```bash
# Debug mode with mock data (recommended for development)
python3 scene_builder/main.py "Create a modern living room" --debug

# Production mode with real LLM calls
python3 scene_builder/main.py "Create a modern living room" --output scenes/my_scene.yaml

# Custom output path
python3 scene_builder/main.py "Your prompt here" -o path/to/output.yaml

# Basic run with default settings (as shown in README)
python3 scene_builder/main.py
```

### Testing
```bash
# Run all tests
pytest tests/

# Run specific test files
python3 tests/test_main_workflow.py
python3 tests/test_scene_generation.py
python3 tests/test_graph_visualization.py

# Run tests in verbose mode
pytest tests/ -v

# Run single test function
pytest tests/test_main_workflow.py::test_specific_function -v
```

## Architecture Overview

SceneBuilder is a Python library that utilizes vision-language models and agentic AI workflows to create 3D scenes. It converts natural language prompts into structured 3D scene definitions using AI agents in a graph-based workflow, which can then be imported into Blender for visualization. The system operates in two modes:

- **Debug mode** (`--debug`): Uses hardcoded mock data for rapid development and testing
- **Production mode**: Makes real LLM calls using OpenAI GPT-4o and connects to Objaverse object database

### Core Workflow Graph (scene_builder/workflow/graph.py)

The main workflow is implemented as a `pydantic-graph` with sequential agents that progressively build scene definitions:

1. **MetadataAgent**: Creates initial scene metadata (residential/commercial, style tags, floor type)
2. **BuildingPlanAgent**: Generates detailed textual scene plan using LLM or mock data
3. **FloorPlanAgent**: Creates room layout and boundaries based on the plan
4. **Room Design Loop**: Iteratively designs each room
   - **DesignLoopEntry**: Controls iteration over rooms list
   - **RoomDesignAgent**: Populates rooms with 3D objects using ObjectDatabase queries
   - **UpdateMainStateAfterDesign**: Merges designed room back into main state

### Key Data Structures (scene_builder/definition/)

- **Scene**: Top-level container with category, tags, floorType, and rooms list
- **Room**: Contains id, category, tags, boundary info, and child objects/sections
- **Object**: 3D objects with position, rotation, scale vectors and source metadata
- **Vector3/Vector2**: 3D and 2D coordinate representations
- **MainState**: Workflow state tracking user input, scene, plan, current room, and config

### Object Database System (scene_builder/database/object.py + scene_builder/importer/)

- **ObjectDatabase**: Abstraction layer for 3D object discovery and queries
- **Debug mode**: Returns hardcoded mock objects for development
- **Production mode**: Interfaces with Objaverse LVIS annotations for semantic search
- **objaverse_importer.py**: Handles downloading and caching of 3D models from Objaverse

### Output Pipeline

1. **YAML Serialization**: Uses `scene_builder/utils/conversions.py` to convert dataclasses to dict
2. **Blender Import**: `scene_builder/decoder/blender_decoder.py` converts YAML to .blend files
3. **Default output**: `scenes/generated_scene.yaml`
4. **Blender Import Script**: Use `scenes/import_scene_to_blender.py` within Blender's Python environment to import generated scenes

### State Management Pattern

The workflow uses a single `MainState` dataclass that flows through all agents, containing:
- User input prompt
- Current scene definition being built
- Generated plan text
- Current room being designed
- Global configuration settings

### Dependencies and Integration

- `pydantic-ai`: LLM integration with structured outputs
- `pydantic-graph`: Graph-based workflow execution framework
- `objaverse`: Large-scale 3D object database access
- `rich`: Enhanced console output and progress display
- `pyyaml`: Scene definition serialization to YAML format

### Development Tips

- Use `--debug` mode during development to avoid LLM API costs and for faster iteration
- The workflow state is preserved between agents, so debugging can be done by examining `MainState` at various points
- Scene definitions are validated using Pydantic dataclasses before serialization
- For Blender import issues, check that the generated YAML structure matches the expected schema in `scene_builder/definition/`