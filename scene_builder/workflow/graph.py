from __future__ import annotations
from dataclasses import dataclass, field

from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage

from rich.console import Console

from scene_builder.database.object import ObjectDatabase
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
        return ScenePlanningAgent()


@dataclass
class ScenePlanningAgent(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> FloorPlanAgent:
        console.print("[bold cyan]Executing Agent:[/] Scene Planning Agent")
        is_debug = ctx.state.config and ctx.state.config.debug

        if is_debug:
            console.print("[bold yellow]Debug mode: Using hardcoded scene plan.[/]")
            ctx.state.plan = "1. Create a living room.\n2. Add a sofa."
        else:
            console.print("[bold green]Production mode: Generating scene plan via LLM.[/]")
            planning_agent = Agent(
                "openai:gpt-4o",
                system_prompt="You are a scene planner. Your goal is to create a plan to build a 3D scene based on the user's request. The plan should be a short, numbered list of steps.",
            )
            response = await planning_agent.run(ctx.state.user_input)
            ctx.state.plan = response.content
            console.print(f"[bold cyan]Generated Plan:[/] {ctx.state.plan}")

        return FloorPlanAgent()


@dataclass
class FloorPlanAgent(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> DesignLoopEntry:
        console.print("[bold cyan]Executing Agent:[/] Floor Plan Agent")
        is_debug = ctx.state.config and ctx.state.config.debug

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
            floor_plan_agent = Agent(
                "openai:gpt-4o",
                system_prompt="You are a floor plan designer. Your goal is to define the rooms for a scene based on a plan. You should return a list of Room objects.",
                response_model=list[Room],
            )
            generated_rooms = await floor_plan_agent.run(
                f"Create rooms for the following plan: {ctx.state.plan}"
            )
            ctx.state.scene_definition.rooms.extend(generated_rooms)
            console.print(
                f"[bold cyan]Generated Rooms:[/] {[room.id for room in generated_rooms]}"
            )

        return DesignLoopEntry()


@dataclass
class DesignLoopEntry(BaseNode[MainState]):
    async def run(
        self,
        ctx: GraphRunContext[MainState]
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
        is_debug = ctx.state.config and ctx.state.config.debug
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
                position=Vector3(0, 0, 0),
                rotation=Vector3(0, 0, 0),
                scale=Vector3(1, 1, 1),
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
