import asyncio
import yaml
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from scene_builder.definition.scene import GlobalConfig
from scene_builder.workflow.graph import app, MainState, MetadataAgent


def test_scene_generation():
    console = Console()
    console.print(Panel("[bold green]Running SceneBuilder Workflow[/]", expand=False))
    initial_state = MainState(
        user_input="Create a modern, minimalist living room.",
        config=GlobalConfig(debug=True),
    )

    async def run_graph():
        return await app.run(MetadataAgent(), state=initial_state)

    result = asyncio.run(run_graph())

    if result:
        final_scene = result.output
        console.print(Panel("[bold green]Exporting Scene[/]", expand=False))
        scene_dict = final_scene  # TODO: convert from BaseModel into dict

        # Save the scene as a YAML file
        output_dir = Path("scenes")
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "generated_scene.yaml"
        with open(output_path, "w") as f:
            yaml.dump(scene_dict, f, default_flow_style=False, sort_keys=False)

        console.print(f"[bold green]Scene saved to {output_path}[/bold green]")


if __name__ == "__main__":
    test_scene_generation()
