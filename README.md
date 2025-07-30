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
```

### Running the Workflow

To run the agentic workflow, execute the `main.py` script:

```bash
python3 scene_builder/workflows/main.py
```

This will run the workflow with mock data and print the execution steps to the console.

### Importing to Blender

The generated scene definition can be imported into Blender by running the `blender_importer.py` script from within Blender's Python environment.

## Next Steps

* Replace placeholder logic in the agents with real LLM calls.
* Connect to a real 3D object database (e.g., Objaverse).
* Implement a YAML-to-Python compilation step to automatically generate the data classes.
* Expand the capabilities of the Blender importer to handle real 3D models.
* Add validation logic to the workflow.
* Write unit tests for the agent tools.
