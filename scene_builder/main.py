import argparse
import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from scene_builder.decoder import blender_decoder
from scene_builder.workflow.graph import app, MainState
from scene_builder.utils.conversions import pydantic_to_dict
from scene_builder.definition.scene import GlobalConfig
import yaml

console = Console()


def main():
    """
    Main entry point for the Scene Builder application.
    """
    parser = argparse.ArgumentParser(description="Generate 3D scenes using AI.")
    parser.add_argument(
        "prompt",
        type=str,
        help="The user's prompt describing the scene to generate.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode to use mock data and hardcoded plans.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="scenes/generated_scene.yaml",
        help="Path to save the generated scene definition YAML file.",
    )
    args = parser.parse_args()

    console.print(
        Panel(
            f"[bold]Starting Scene Builder...[/]\nPrompt: [italic]'{args.prompt}'[/italic]\nDebug Mode: {'[bold green]On[/]' if args.debug else '[bold red]Off[/]'}",
            title="Scene Builder Configuration",
            expand=False,
        )
    )

    # Initial state for the graph
    initial_state = MainState(
        user_input=args.prompt,
        config=GlobalConfig(debug=args.debug),
    )

    # Run the graph asynchronously
    final_scene = asyncio.run(app.run(initial_state))

    # Convert the final scene Pydantic model to a dictionary for serialization
    scene_dict = pydantic_to_dict(final_scene)

    # Save the scene definition to a YAML file
    with open(args.output, "w") as f:
        yaml.dump(scene_dict, f, default_flow_style=False, sort_keys=False)

    console.print(
        Panel(
            f"Scene generation complete. Definition saved to [bold cyan]{args.output}[/bold cyan]",
            title="Success",
            expand=False,
        )
    )

    # Print the generated YAML to the console
    console.print(Panel("Generated Scene YAML:", expand=False))
    console.print(
        Syntax(yaml.dump(scene_dict), "yaml", theme="monokai", line_numbers=True)
    )


if __name__ == "__main__":
    main()
