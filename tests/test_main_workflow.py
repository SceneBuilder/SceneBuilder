from rich.console import Console
from rich.panel import Panel

from scene_builder.decoder import blender_importer
from scene_builder.workflow.graph import app
from scene_builder.utils.conversions import dataclass_to_dict

def test_main_workflow():
    console = Console()
    console.print(Panel("[bold green]Running SceneBuilder Workflow[/]", expand=False))
    initial_state = {
        "user_input": "Create a modern, minimalist living room.",
        "messages": [("user", "Create a modern, minimalist living room.")],
        "current_room_index": 0,
    }
    final_scene = None
    for i, event in enumerate(app.stream(initial_state, stream_mode="values")):
        console.print(Panel(f"[bold yellow]Workflow Step {i + 1}[/]", expand=False))
        console.print(event)
        if "scene_definition" in event:
            final_scene = event["scene_definition"]

    if final_scene:
        console.print(Panel("[bold green]Exporting to Blender[/]", expand=False))
        scene_dict = dataclass_to_dict(final_scene)
        blender_importer.parse_scene_definition(scene_dict)
        blender_importer.save_scene("output.blend")
        console.print(
            "[bold green]Blender file 'output.blend' created successfully.[/]"
        )


