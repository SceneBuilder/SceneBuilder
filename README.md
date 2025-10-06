# SceneBuilder

SceneBuilder is a Python library that utilizes vision-language models and agentic AI workflows to create 3D scenes.

## Architecture

The system is built around a `langgraph`-based agentic workflow that progressively builds a 3D scene definition. The workflow is divided into the following agents:

1. **Metadata Agent:** Creates the initial metadata for the scene based on high-level user input.
2. **Scene Planning Agent:** Generates a high-level plan for the scene's contents.
3. **Floor Plan Agent:** Creates the layout of rooms in the scene.
4. **Room Design Agent:** A subgraph that designs each room, using tools to query for and place objects.

The scene definition is based on a schema defined in YAML format, which is then translated into Python dataclasses for use in the workflow.

## Getting Started

### Installation

To install the necessary dependencies, run:

```bash
pip install .
# For development dependencies:
pip install .[dev]
```

### CLI Usage

SceneBuilder provides a Typer-based CLI with two main functionalities:

#### 1. Generate Scenes (TODO)

Generate a 3D scene from a natural language prompt:

```bash
python3 -m scene_builder.main generate "Create a modern living room" --output scenes/my_scene.yaml
```

Options:
- `--debug`: Enable debug mode with mock data (no API calls)
- `-o, --output`: Path to save the generated scene YAML (default: `scenes/generated_scene.yaml`)

#### 2. Decode YAML to Blender

Convert scene or room definition YAML files to Blender `.blend` files:

**Decode a room:**
```bash
python3 -m scene_builder.main decode room <yaml_path> <output.blend>
```

**Decode a full scene:**
```bash
python3 -m scene_builder.main decode scene <yaml_path> <output.blend>
```

Options:
- `--exclude-grid` / `--include-grid`: Control whether grid objects are included in exported .blend file (default: excluded)

**Examples:**
```bash
# Decode a room with grid excluded (default)
python3 -m scene_builder.main decode room scenes/room_definition.yaml output/room.blend

# Decode a scene with grid included
python3 -m scene_builder.main decode scene scenes/generated_scene.yaml output/scene.blend --include-grid
```

### Importing to Blender

The generated `.blend` files can be opened directly in Blender. Alternatively, you can import YAML definitions programmatically from within Blender's Python console:

```python
import sys
sys.path.append('/path/to/SceneBuilder')
from scene_builder.decoder.blender import parse_scene_definition, parse_room_definition

# For a full scene
parse_scene_definition(scene_data_dict)

# For a single room
parse_room_definition(room_data_dict)
```

## Next Steps

* Replace placeholder logic in the agents with real LLM calls.
* Connect to a real 3D object database (e.g., Objaverse).
* Implement a YAML-to-Python compilation step to automatically generate the data classes.
* Expand the capabilities of the Blender importer to handle real 3D models.
* Add validation logic to the workflow.
* Write unit tests for the agent tools.
