import yaml
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from scene_builder.definition.scene import Config
from scene_builder.utils.conversions import dataclass_to_dict
from scene_builder.workflow.graph import app


def test_scene_generation():
    console = Console()
    console.print(Panel("[bold green]Running SceneBuilder Workflow[/]", expand=False))
    initial_state = {
        "user_input": "Create a modern, minimalist living room.",
        "messages": [("user", "Create a modern, minimalist living room.")],
        "current_room_index": 0,
        "config": Config(debug=True),
    }
    final_scene = None
    for i, event in enumerate(app.stream(initial_state, stream_mode="values")):
        console.print(Panel(f"[bold yellow]Workflow Step {i + 1}[/]", expand=False))
        console.print(event)
        if "scene_definition" in event:
            final_scene = event["scene_definition"]

    if final_scene:
        console.print(Panel("[bold green]Exporting Scene[/]", expand=False))
        scene_dict = dataclass_to_dict(final_scene)

        # Save the scene as a YAML file
        output_dir = Path("scenes")
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "generated_scene.yaml"
        with open(output_path, "w") as f:
            yaml.dump(scene_dict, f, default_flow_style=False, sort_keys=False)

        console.print(f"[bold green]Scene saved to {output_path}[/bold green]")


if __name__ == "__main__":
    test_scene_generation()
