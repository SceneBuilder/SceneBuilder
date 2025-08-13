import asyncio
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from scene_builder.decoder import blender_decoder
from scene_builder.definition.scene import GlobalConfig
from scene_builder.workflow.graph import app, MainState, MetadataAgent


def test_main_workflow():
    console = Console()
    console.print(Panel("[bold green]Running SceneBuilder Workflow[/]", expand=False))
    initial_state = MainState(
        user_input="Create a modern, minimalist living room.",
        global_config=GlobalConfig(debug=True),
    )

    async def run_graph():
        return await app.run(MetadataAgent(), state=initial_state)

    result = asyncio.run(run_graph())

    if result:
        final_scene = result.output
        console.print(Panel("[bold green]Exporting to Blender[/]", expand=False))
        # Convert from BaseModel to dict for blender_decoder
        from scene_builder.utils.conversions import pydantic_to_dict
        scene_dict = pydantic_to_dict(final_scene)

        output_dir = Path("scenes")
        output_dir.mkdir(exist_ok=True)
        blender_decoder.parse_scene_definition(scene_dict)
        blender_decoder.save_scene(str(output_dir / "output.blend"))

        console.print("[bold green]Blender file created successfully.[/]")
