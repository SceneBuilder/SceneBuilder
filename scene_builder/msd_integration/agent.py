#!/usr/bin/env python3
"""
MSD FloorPlan Agent

Integrates MSD data into SceneBuilder workflow.
Single responsibility: Replace FloorPlanAgent with MSD data.
"""
# NOTE: it's better to keep this MSD Agent seperate? since it's only graph workflow node, not a LLM-powered agent in SceneBuilder agents.py

from pydantic_graph import BaseNode, GraphRunContext
from rich.console import Console

from scene_builder.definition.scene import Scene, Room
from scene_builder.workflow.states import MainState
from scene_builder.msd_integration.loader import MSDLoader
from scene_builder.msd_integration.converter import GraphToSceneConverter

console = Console()


class MSDFloorPlanAgent(BaseNode[MainState]):
    def __init__(self):
        self.loader = MSDLoader()
        self.converter = GraphToSceneConverter()

    async def run(self, ctx: GraphRunContext[MainState]):
        console.print("[bold cyan] Generating floorplan from MSD data...[/]")

        apartment_id = self.loader.get_random_apartment()
        graph = self.loader.create_graph(apartment_id)
        rooms = self.converter.convert_graph_to_rooms(graph)
        # Add to scen
        ctx.state.scene_definition.rooms.extend(rooms)
        ctx.state.scene_definition.tags.append("msd")

        console.print(
            f"[bold green]✓ Generated {len(rooms)} rooms from MSD apartment {apartment_id[:12]}...[/]"
        )

        from scene_builder.workflow.graph import DesignLoopEntry

        return DesignLoopEntry()
