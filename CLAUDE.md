# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

This is a NavGoProject repository containing:

- **SceneBuilder/**: A Python library for generating 3D scenes using AI agents and vision-language models

## Development Commands

### SceneBuilder Development

The repository is already the SceneBuilder directory - run commands from the repository root.

#### Installation
```bash
pip install .
# For development dependencies:
pip install .[dev]
```

#### Running the Application
```bash
# Debug mode with mock data (recommended for development)
python3 scene_builder/main.py "Create a modern living room" --debug

# Production mode with real LLM calls (requires GOOGLE_API_KEY environment variable)
python3 scene_builder/main.py "Create a modern living room" --output scenes/my_scene.yaml

# Custom output path
python3 scene_builder/main.py "Your prompt here" -o path/to/output.yaml

# Note: A prompt argument is required - there is no default run mode
```

#### Testing
```bash
# Run all tests
pytest tests/

# Run specific test files (standalone test functions)
python3 tests/test_main_workflow.py
python3 tests/test_scene_generation.py
python3 tests/test_graph_visualization.py
python3 tests/test_render.py
python3 tests/test_room_design_workflow.py

# Run with pytest for more control
pytest tests/ -v
pytest tests/test_main_workflow.py::test_specific_function -v
```

#### Blender Integration
```bash
# Import generated YAML scene into Blender (run from within Blender's Python console)
import sys
sys.path.append('/path/to/SceneBuilder')
from scene_builder.decoder.blender_decoder import parse_scene_definition
parse_scene_definition('scenes/generated_scene.yaml')
```

## Architecture Overview

SceneBuilder is a Python library that utilizes vision-language models and agentic AI workflows to create 3D scenes. It converts natural language prompts into structured 3D scene definitions using AI agents in a `pydantic-graph`-based workflow, which can then be imported into Blender for visualization. The system operates in two modes:

- **Debug mode** (`--debug`): Uses hardcoded mock data for rapid development and testing
- **Production mode**: Makes real LLM calls using Google Gemini 2.5 Flash and connects to Objaverse object database

### Core Workflow Graph (scene_builder/workflow/graph.py)

The main workflow is implemented as a `pydantic-graph` with sequential agents that progressively build scene definitions:

1. **MetadataAgent**: Creates initial scene metadata (residential/commercial, style tags, floor type)
2. **BuildingPlanAgent**: Generates detailed textual scene plan using LLM or mock data
3. **FloorPlanAgent**: Creates room layout and boundaries with LLM-analyzed floor dimensions
4. **Room Design Loop**: Iteratively designs each room
   - **DesignLoopEntry**: Controls iteration over rooms list  
   - **RoomDesignAgent**: Populates rooms with 3D objects using ObjectDatabase queries
   - **UpdateScene**: Merges designed room back into main state and advances to next room

**Additional Specialized Graphs:**
- **placement_graph**: Handles precise object placement within rooms with visual feedback
  - **PlacementAgent**: Uses LLM to determine object positioning and placement decisions
  - **VisualFeedback**: Generates Blender renders for iterative placement refinement

### Key Data Structures (scene_builder/definition/)

- **Scene**: Top-level container with category, tags, floorType, and rooms list
- **Room**: Contains id, category, tags, boundary info, floor_dimensions, and child objects/sections
- **Object**: 3D objects with position, rotation, scale vectors and source metadata
- **Vector3/Vector2**: 3D and 2D coordinate representations
- **FloorDimensions**: LLM-analyzed floor metadata with width, height, shape, and confidence
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
4. **Blender Import**: Use `scene_builder/decoder/blender_decoder.py` functions to import generated scenes into Blender

### State Management Pattern

The workflow uses a single `MainState` dataclass that flows through all agents, containing:
- User input prompt
- Current scene definition being built
- Generated plan text
- Current room being designed (`current_room_index` tracks progress)
- Global configuration settings (`GlobalConfig` with debug flag)

**Additional State Types:**
- **PlacementState**: Used in placement subgraph for object positioning with room history tracking
- **RoomUpdateState**: Handles room modifications during design iterations

### Dependencies and Integration

- **`pydantic-ai`**: LLM integration with structured outputs (Google Gemini by default)
- **`pydantic-graph`**: Graph-based workflow execution framework  
- **`objaverse`**: Large-scale 3D object database access
- **`rich`**: Enhanced console output and progress display
- **`pyyaml`**: Scene definition serialization to YAML format

**Development Dependencies:**
- **`pytest`**: Test framework (install with `pip install .[dev]`)

### Environment Variables

- `GOOGLE_API_KEY`: Required for production mode LLM calls to Google Gemini 2.5 Flash

## Development Tips

- **Debug Mode**: Use `--debug` flag during development to avoid LLM API costs and enable faster iteration with hardcoded mock data
- **State Debugging**: The workflow state is preserved between agents - examine `MainState.current_room_index`, `MainState.plan`, and `MainState.scene_definition` at various points for debugging
- **Schema Validation**: Scene definitions are validated using Pydantic dataclasses before YAML serialization
- **Graph Structure**: Main graph consists of sequential agents, while placement graph uses iterative feedback loops
- **Test Execution**: Most test files contain standalone functions that can be run directly with Python (not just pytest)
- **Object Database**: In debug mode, `ObjectDatabase` returns hardcoded mock objects; in production it queries Objaverse LVIS annotations
- **Blender Integration**: Generated YAML scenes can be imported into Blender via `blender_decoder.py` functions
- **Rich Console**: All workflow output uses Rich library for formatted console display with color coding
- **Async Execution**: The entire workflow runs asynchronously using `asyncio.run()` - agents are async functions

### Troubleshooting

- **Missing Dependencies**: Production mode requires `GOOGLE_API_KEY` environment variable for LLM calls
- **Blender Import Errors**: Verify YAML structure matches dataclass schema in `scene_builder/definition/`
- **Graph Execution Issues**: Check `MainState.current_room_index` bounds against `MainState.scene_definition.rooms` length
- **Object Placement**: Placement graph uses iterative visual feedback - check render output for debugging placement issues
- **LLM Floor Analysis**: FloorPlanAgent uses language models for dimension estimation - verify floor_dimensions are populated correctly