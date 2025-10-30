import asyncio
from pathlib import Path

import bpy
import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from scene_builder.decoder.blender import blender
from scene_builder.definition.scene import Room, Scene
from scene_builder.workflow.graphs import main_graph
from scene_builder.workflow.states import MainState
from scene_builder.utils.blender import SceneSwitcher
from scene_builder.utils.conversions import pydantic_to_dict, pydantic_from_yaml

console = Console()
app = typer.Typer(help="SceneBuilder: Generate 3D scenes using AI")

# Create subcommand for decode tools
decode_app = typer.Typer(help="Tools for decoding scene/room YAML files to Blender")
app.add_typer(decode_app, name="decode")


@app.command("generate")
def generate(
    prompt: str = typer.Argument(..., help="The user's prompt describing the scene to generate"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode with mock data"),
    output: str = typer.Option(
        "scenes/generated_scene.yaml",
        "-o",
        "--output",
        help="Path to save the generated scene definition YAML file",
    ),
):
    """
    Generate a 3D scene from a natural language prompt.
    """
    console.print(
        Panel(
            f"[bold]Starting Scene Builder...[/]\nPrompt: [italic]'{prompt}'[/italic]\nDebug Mode: {'[bold green]On[/]' if debug else '[bold red]Off[/]'}",
            title="Scene Builder Configuration",
            expand=False,
        )
    )

    # Initial state for the graph
    initial_state = MainState(
        user_input=prompt,
    )

    # Run the graph asynchronously
    final_scene = asyncio.run(main_graph.run(initial_state))

    # Convert the final scene Pydantic model to a dictionary for serialization
    scene_dict = pydantic_to_dict(final_scene)

    # Save the scene definition to a YAML file
    with open(output, "w") as f:
        yaml.dump(scene_dict, f, default_flow_style=False, sort_keys=False)

    console.print(
        Panel(
            f"Scene generation complete. Definition saved to [bold cyan]{output}[/bold cyan]",
            title="Success",
            expand=False,
        )
    )

    # Print the generated YAML to the console
    console.print(Panel("Generated Scene YAML:", expand=False))
    console.print(
        Syntax(yaml.dump(scene_dict), "yaml", theme="monokai", line_numbers=True)
    )


@decode_app.command("room")
def decode_room(
    yaml_path: Path = typer.Argument(..., help="Path to room definition YAML file"),
    output: Path = typer.Option(None, "-o", "--output", help="Path to save the output file (.blend, .gltf, or .glb). Defaults to input filename with .blend extension"),
    exclude_grid: bool = typer.Option(
        True, "--exclude-grid/--include-grid", help="Exclude grid from exported file"
    ),
    with_walls: bool = typer.Option(
        True, "--with-walls/--no-walls", help="Add walls around room boundary"
    ),
):
    """
    Decode a room definition YAML file and save as a Blender scene.
    Supports .blend, .gltf, and .glb output formats.
    """
    if not yaml_path.exists():
        console.print(f"[bold red]Error:[/] File not found: {yaml_path}")
        raise typer.Exit(1)

    # Default output to input filename with .blend extension if not specified
    if output is None:
        output = yaml_path.with_suffix('.blend')

    console.print(f"[bold]Loading room definition from:[/] {yaml_path}")

    # Load YAML file as Pydantic model
    room: Room = pydantic_from_yaml(yaml_path, Room)

    # Parse and create Blender scene
    blender.parse_room_definition(room, clear=True)
    with SceneSwitcher(room.id) as active_scene:
        # Add walls with structural cutouts if requested
        if with_walls:
            walls_created = blender.create_room_walls([room])
            if walls_created > 0:
                console.print(f"[bold green]✓[/] Created {walls_created} wall(s) with structural cutouts")
            else:
                console.print("[bold yellow]•[/] No walls created (missing or invalid boundary)")

        blender.setup_lighting_foundation(bpy.context.scene)
        blender.setup_post_processing(bpy.context.scene)
        blender._configure_render_settings()  # HACK

    # Export based on file extension
    output_suffix = output.suffix.lower()
    if output_suffix in ['.gltf', '.glb']:
        blender.export_to_gltf(str(output), scene=room.id, exclude_grid=exclude_grid)
        console.print(
            Panel(
                f"Room scene exported to GLTF: [bold cyan]{output}[/bold cyan]",
                title="Success",
                expand=False,
            )
        )
    else:
        # blender._configure_render_settings()  # HACK
        blender.save_scene(str(output), exclude_grid=exclude_grid)
        console.print(
            Panel(
                f"Room scene saved to [bold cyan]{output}[/bold cyan]",
                title="Success",
                expand=False,
            )
        )


@decode_app.command("scene")
def decode_scene(
    yaml_path: Path = typer.Argument(..., help="Path to scene definition YAML file"),
    output: Path = typer.Option(None, "-o", "--output", help="Path to save the output file (.blend, .gltf, or .glb). Defaults to input filename with .blend extension"),
    exclude_grid: bool = typer.Option(
        True, "--exclude-grid/--include-grid", help="Exclude grid from exported file"
    ),
    with_walls: bool = typer.Option(
        True, "--with-walls/--no-walls", help="Add walls around each room boundary"
    ),
):
    """
    Decode a full scene definition YAML file and save as a Blender scene.
    Supports .blend, .gltf, and .glb output formats.
    """
    if not yaml_path.exists():
        console.print(f"[bold red]Error:[/] File not found: {yaml_path}")
        raise typer.Exit(1)

    # Default output to input filename with .blend extension if not specified
    if output is None:
        output = yaml_path.with_suffix('.blend')

    console.print(f"[bold]Loading scene definition from:[/] {yaml_path}")

    # Load YAML file as Pydantic model
    scene: Scene = pydantic_from_yaml(yaml_path, Scene)

    # Parse and create Blender scene
    blender.parse_scene_definition(scene)

    # Add walls with structural cutouts if requested
    if with_walls:
        walls_created = blender.create_room_walls(scene.rooms)
        if walls_created > 0:
            console.print(f"[bold green]✓[/] Created walls for {walls_created} room(s) with structural cutouts")
        else:
            console.print("[bold yellow]•[/] No walls created (missing or invalid boundaries)")

    blender.setup_lighting_foundation(bpy.context.scene)
    blender.setup_post_processing(bpy.context.scene)
    blender._configure_render_settings()  # HACK

    # Export based on file extension
    output_suffix = output.suffix.lower()
    if output_suffix in ['.gltf', '.glb']:
        blender.export_to_gltf(str(output), exclude_grid=exclude_grid)
        console.print(
            Panel(
                f"Scene exported to GLTF: [bold cyan]{output}[/bold cyan]",
                title="Success",
                expand=False,
            )
        )
    else:
        blender.save_scene(str(output), exclude_grid=exclude_grid)
        console.print(
            Panel(
                f"Scene saved to [bold cyan]{output}[/bold cyan]",
                title="Success",
                expand=False,
            )
        )


def main():
    """
    Main entry point for the Scene Builder application.
    """
    app()


if __name__ == "__main__":
    main()
