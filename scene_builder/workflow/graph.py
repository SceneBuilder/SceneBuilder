from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage

from rich.console import Console

from scene_builder.decoder import blender_decoder
from scene_builder.database.object import ObjectDatabase
from scene_builder.definition.scene import Scene, Room, Object, Vector3, GlobalConfig
from scene_builder.workflow.agent import (
    floor_plan_agent,
    placement_agent,
    planning_agent,
)
from scene_builder.workflow.state import PlacementState, RoomUpdateState

console = Console()


# --- State Definitions ---
class MainState(BaseModel):
    user_input: str
    scene_definition: Scene | None = None
    plan: str | None = None
    messages: list[ModelMessage] = Field(default_factory=list)
    current_room_index: int = 0
    global_config: GlobalConfig | None = None

    class Config:
        arbitrary_types_allowed = True


# --- Main Graph Nodes ---
class MetadataAgent(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> BuildingPlanAgent:
        console.print("[bold cyan]Executing Agent:[/] Metadata Agent")
        initial_scene = Scene(
            category="residential",
            tags=["modern", "minimalist"],
            floorType="single",
            rooms=[],
        )
        ctx.state.scene_definition = initial_scene
        return BuildingPlanAgent()


class BuildingPlanAgent(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> FloorPlanAgent:
        console.print("[bold cyan]Executing Agent:[/] Scene Planning Agent")
        is_debug = ctx.state.global_config and ctx.state.global_config.debug

        if is_debug:
            console.print("[bold yellow]Debug mode: Using hardcoded scene plan.[/]")
            ctx.state.plan = "1. Create a living room.\n2. Add a sofa."
        else:
            console.print(
                "[bold green]Production mode: Generating scene plan via LLM.[/]"
            )
            response = await planning_agent.run(ctx.state.user_input)
            ctx.state.plan = response.content
            console.print(f"[bold cyan]Generated Plan:[/] {ctx.state.plan}")

        return FloorPlanAgent()


class FloorPlanAgent(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> DesignLoopEntry:
        console.print("[bold cyan]Executing Agent:[/] Floor Plan Agent")
        is_debug = ctx.state.global_config and ctx.state.global_config.debug

        if is_debug:
            console.print("[bold yellow]Debug mode: Using hardcoded floor plan.[/]")
            living_room = Room(
                id="living_room_1", category="living_room", tags=["main"], objects=[]
            )
            ctx.state.scene_definition.rooms.append(living_room)
        else:
            console.print(
                "[bold green]Production mode: Generating floor plan via LLM.[/]"
            )
            generated_rooms = await floor_plan_agent.run(
                f"Create rooms for the following plan: {ctx.state.plan}"
            )
            ctx.state.scene_definition.rooms.extend(generated_rooms)
            console.print(
                f"[bold cyan]Generated Rooms:[/] {[room.id for room in generated_rooms]}"
            )

        return DesignLoopEntry()


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


class RoomDesignAgent(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> UpdateScene:
        console.print("[bold cyan]Executing Node:[/] RoomDesignAgent")
        room_to_design = ctx.state.scene_definition.rooms[ctx.state.current_room_index]
        is_debug = ctx.state.global_config and ctx.state.global_config.debug
        db = ObjectDatabase(debug=is_debug)

        if is_debug:
            console.print("[bold yellow]Debug mode: Using hardcoded object data.[/]")
            sofa_data = db.query("a modern sofa")[0]
            new_object = Object(
                id=sofa_data["id"],
                name=sofa_data["name"],
                description=sofa_data["description"],
                source=sofa_data["source"],
                sourceId=sofa_data["id"],
                position=Vector3(x=0, y=0, z=0),
                rotation=Vector3(x=0, y=0, z=0),
                scale=Vector3(x=1, y=1, z=1),
            )
            room_to_design.objects.append(new_object)
        else:
            console.print(
                "[bold green]Production mode: Designing room via LLM and real data.[/]"
            )
            room_design_agent = Agent(
                "openai:gpt-4o",
                system_prompt="You are a room designer. Your goal is to add objects to the room based on the user's request. Use the provided tools to find appropriate objects.",
                tools=[db.query],
                response_model=list[Object],
            )
            prompt = f"Design the room '{room_to_design.category}' with id '{room_to_design.id}'. The overall user request is: '{ctx.state.user_input}'. The scene plan is: {ctx.state.plan}"
            new_objects = await room_design_agent.run(prompt)
            room_to_design.objects.extend(new_objects)
            console.print(
                f"[bold cyan]Added Objects:[/] {[obj.name for obj in new_objects]}"
            )
            ctx.state.designed_room

        return UpdateScene()


class PlacementAgent(BaseNode[PlacementState]):
    async def run(
        self, ctx: GraphRunContext[PlacementState]
    ) -> VisualFeedback | End[Room]:
        response = await placement_agent.run(ctx.state)

        if response.decision == "finalize":
            return End(ctx.state.room)
        else:
            ctx.state.room = response.placement_action.updated_room
            return VisualFeedback()


class VisualFeedback(BaseNode[PlacementState]):
    async def run(self, ctx: GraphRunContext[PlacementState]) -> PlacementAgent:
        blender_decoder.parse_scene_definition(ctx.state.room)
        renders = blender_decoder.render()
        prev_room = ctx.state.room
        prev_room.viz.append(renders)
        ctx.state.room_history.append(prev_room)
        return PlacementAgent()


class UpdateScene(BaseNode[Scene, RoomUpdateState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> DesignLoopEntry:
        """Merges the result from the room design subgraph back into the main state."""
        console.print("[bold cyan]Executing Node:[/] update_main_state_after_design")
        ctx.state.scene_definition.rooms[ctx.state.current_room_index] = (
            self.designed_room
        )
        ctx.state.current_room_index += 1
        return DesignLoopEntry()


# --- Graph Definition ---
main_graph = Graph(
    nodes=[MetadataAgent, BuildingPlanAgent, FloorPlanAgent, DesignLoopEntry],
    state_type=MainState,
)

room_design_graph = Graph(
    nodes=[
        DesignLoopEntry,
        RoomDesignAgent,
        UpdateScene,
    ],
    state_type=Room,
)

app = main_graph
