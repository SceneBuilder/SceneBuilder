#!/usr/bin/env python3
"""
MSD FloorPlan Node

Integrates MSD data into SceneBuilder workflow.
Single responsibility: Replace FloorPlan generation with MSD data.
"""

from pydantic_graph import BaseNode, GraphRunContext
from rich.console import Console

from scene_builder.definition.scene import Scene, Room
from scene_builder.workflow.states import MainState
from scene_builder.msd_integration.loader import MSDLoader
from scene_builder.nodes.planning import DesignLoopEntry

console = Console()


class MSDFloorPlanNode(BaseNode[MainState]):
    def __init__(self):
        self.loader = MSDLoader()

    async def run(self, ctx: GraphRunContext[MainState]):
        console.print("[bold cyan] Generating floorplan from MSD data...[/]")

        apartment_id = self.loader.get_random_apartment()
        graph = self.loader.create_graph(apartment_id)
        rooms = self.loader.convert_graph_to_rooms(graph)
        # Add to scene
        ctx.state.scene_definition.rooms.extend(rooms)
        ctx.state.scene_definition.tags.append("msd")

        console.print(
            f"[bold green]✓ Generated {len(rooms)} rooms from MSD apartment {apartment_id[:12]}...[/]"
        )

        return DesignLoopEntry()
