from __future__ import annotations
from dataclasses import dataclass, field
from typing import Annotated

from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage

from rich.console import Console

from scene_builder.tools.object_database import query_object_database
from scene_builder.definition.scene import Scene, Room, Object, Vector3, Config

console = Console()


# --- State Definitions ---
@dataclass
class MainState:
    user_input: str
    scene_definition: Scene | None = None
    plan: str | None = None
    messages: list[ModelMessage] = field(default_factory=list)
    current_room_index: int = 0
    config: Config | None = None


# --- Room Design Agent ---
room_design_agent = Agent(
    "openai:gpt-4o",
    system_prompt="You are a room designer. Your goal is to add objects to the room based on the user's request.",
    tools=[query_object_database],
)


# --- Main Graph Nodes ---
@dataclass
class MetadataAgent(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> ScenePlanningAgent:
        console.print("[bold cyan]Executing Agent:[/] Metadata Agent")
        initial_scene = Scene(
            category="residential",
            tags=["modern", "minimalist"],
            floorType="single",
            rooms=[],
        )
        ctx.state.scene_definition = initial_scene
        # ctx.state.messages.append(("assistant", "Scene metadata created."))
        return ScenePlanningAgent()


@dataclass
class ScenePlanningAgent(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> FloorPlanAgent:
        console.print("[bold cyan]Executing Agent:[/] Scene Planning Agent")
        ctx.state.plan = "1. Create a living room.\n2. Add a sofa."
        # ctx.state.messages.append(("assistant", "Scene plan created."))
        return FloorPlanAgent()


@dataclass
class FloorPlanAgent(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> DesignLoopEntry:
        console.print("[bold cyan]Executing Agent:[/] Floor Plan Agent")
        living_room = Room(
            id="living_room_1", category="living_room", tags=["main"], objects=[]
        )
        ctx.state.scene_definition.rooms.append(living_room)
        # ctx.state.messages.append(("assistant", "Floor plan created."))
        return DesignLoopEntry()


@dataclass
class DesignLoopEntry(BaseNode[MainState]):
    async def run(
        self, ctx: GraphRunContext[MainState]
    ) -> RoomDesignAgent | End[Scene]:
        console.print("[bold yellow]Entering room design loop...[/]")
        if ctx.state.current_room_index < len(ctx.state.scene_definition.rooms):
            console.print("[magenta]Decision:[/] Design next room.")
            return RoomDesignAgent()
        else:
            console.print("[magenta]Decision:[/] Finish.")
            return End(ctx.state.scene_definition)


@dataclass
class RoomDesignAgent(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> UpdateMainStateAfterDesign:
        console.print("[bold cyan]Executing Node:[/] RoomDesignAgent")
        room_to_design = ctx.state.scene_definition.rooms[
            ctx.state.current_room_index
        ]

        if ctx.state.config and ctx.state.config.debug:
            # In debug mode, use hardcoded data
            sofa_data = query_object_database("a modern sofa")[0]
            new_object = Object(
                id=sofa_data["id"],
                name=sofa_data["name"],
                description=sofa_data["description"],
                source=sofa_data["source"],
                sourceId=sofa_data["id"],
                position=Vector3(0, 0, 0),
                rotation=Vector3(0, 0, 0),
                scale=Vector3(1, 1, 1),
            )
            room_to_design.objects.append(new_object)
            # messages = [("assistant", f"Added object {new_object.name} to room.")]
        else:
            # In a real implementation, this would be an LLM call.
            # For now, we'll just return an empty response.
            console.print("[bold yellow]Non-debug mode: LLM call not implemented.[/]")
            # messages = [("assistant", "LLM call not implemented.")]

        return UpdateMainStateAfterDesign(room_to_design)


@dataclass
class UpdateMainStateAfterDesign(BaseNode[MainState]):
    designed_room: Room

    async def run(self, ctx: GraphRunContext[MainState]) -> DesignLoopEntry:
        """Merges the result from the room design subgraph back into the main state."""
        console.print("[bold cyan]Executing Node:[/] update_main_state_after_design")
        ctx.state.scene_definition.rooms[
            ctx.state.current_room_index
        ] = self.designed_room
        ctx.state.current_room_index += 1
        return DesignLoopEntry()


# --- Graph Definition ---
workflow_builder = Graph(
    nodes=[
        MetadataAgent,
        ScenePlanningAgent,
        FloorPlanAgent,
        DesignLoopEntry,
        RoomDesignAgent,
        UpdateMainStateAfterDesign,
    ],
    state_type=MainState,
)

app = workflow_builder
