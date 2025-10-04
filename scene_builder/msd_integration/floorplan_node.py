#!/usr/bin/env python3
"""
MSD FloorPlan Node

Integrates MSD data into SceneBuilder workflow.
Building-level rendering: loads entire building with all apartments.
"""

from typing import Optional
from pydantic_graph import BaseNode, GraphRunContext
from rich.console import Console

from scene_builder.workflow.states import MainState
from scene_builder.msd_integration.loader import MSDLoader
from scene_builder.msd_integration.converter import GraphToSceneConverter
from scene_builder.nodes.planning import DesignLoopEntry

console = Console()


class MSDFloorPlanNode(BaseNode[MainState]):
    def __init__(self, building_id: Optional[int] = None):
        """
        Initialize MSD FloorPlan Node.

        Args:
            building_id: Specific building ID to render. If None, selects random building.
        """
        self.loader = MSDLoader()
        self.converter = GraphToSceneConverter()
        self.building_id = building_id

    async def run(self, ctx: GraphRunContext[MainState]):
        console.print("[bold cyan]Generating floorplan from MSD data...[/]")

        building_id = self.building_id or self.loader.get_random_building()

        if not building_id:
            console.print("[bold red]✗ No building found[/]")
            return DesignLoopEntry()

        graphs = self.loader.create_building_graph(building_id)

        if not graphs:
            console.print(f"[bold red]✗ No data found for building {building_id}[/]")
            return DesignLoopEntry()

        all_rooms = []
        for graph in graphs:
            rooms = self.converter.convert_graph_to_rooms(graph)
            all_rooms.extend(rooms)

        ctx.state.scene_definition.rooms.extend(all_rooms)
        ctx.state.scene_definition.tags.extend(["msd", "building"])

        console.print(
            f"[bold green]✓ Generated {len(all_rooms)} rooms from {len(graphs)} apartments in building {building_id}[/]"
        )

        return DesignLoopEntry()
