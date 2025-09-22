from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage

from rich.console import Console

from scene_builder.decoder import blender
from scene_builder.database.object import ObjectDatabase
from scene_builder.definition.scene import Scene, Room, Object, Vector3, GlobalConfig
from scene_builder.utils.conversions import pydantic_to_dict
from scene_builder.workflow.agents import (
    floor_plan_agent,
    floor_size_agent,
    placement_agent,
    planning_agent,
)
from scene_builder.workflow.states import PlacementState, RoomUpdateState

DEBUG = True

console = Console()


# --- State Definitions ---
class MainState(BaseModel):
    user_input: str
    scene_definition: Scene | None = None
    plan: str | None = None
    messages: list[ModelMessage] = Field(default_factory=list)
    current_room_index: int = 0
    global_config: GlobalConfig | None = None


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
                "[bold green]Production mode: Generating intelligent room layout with LLM.[/]"
            )
            
            # Step 1: Use LLM to analyze floor dimensions from text description
            console.print("[bold cyan]Step 1: Analyzing floor dimensions with LLM...[/]")
            floor_analysis_prompt = (
                f"Based on the user request: '{ctx.state.user_input}' and building plan: '{ctx.state.plan}', "
                f"estimate realistic floor dimensions for the main room. Consider the room type and its intended use."
            )
            llm_floor_dims_result = await floor_size_agent.run(floor_analysis_prompt)
            llm_floor_dims = llm_floor_dims_result.output
            console.print(f"[bold cyan]LLM Dimension Analysis:[/] {llm_floor_dims.width}x{llm_floor_dims.length}m (floor), height: {llm_floor_dims.ceiling_height}m, {llm_floor_dims.shape}")
            
            # Step 2: Generate rooms with LLM using dimensional context
            console.print("[bold cyan]Step 2: Generating room layout with architectural intelligence...[/]")
            room_generation_prompt = (
                f"Create a room layout for: {ctx.state.user_input}\n"
                f"Building plan context: {ctx.state.plan}\n"
                f"Recommended dimensions: {llm_floor_dims.width}m x {llm_floor_dims.length}m (floor area)\n"
                f"Room shape: {llm_floor_dims.shape}\n"
                f"Focus on creating one primary room that matches the user's request with appropriate sizing." # TODO: multi rooms soon later 
            )
            generated_rooms_result = await floor_plan_agent.run(room_generation_prompt)
            generated_rooms = generated_rooms_result.output
            
            # Step 3: Apply LLM-analyzed dimensions to generated rooms
            console.print("[bold cyan]Step 3: Applying LLM dimension analysis to rooms...[/]")
            
            try:
                for room in generated_rooms:
                    # Apply LLM-analyzed dimensions to the room
                    room.floor_dimensions = llm_floor_dims
                    # Note: room.boundary is already generated by the LLM with the requested shape
                    console.print(f"[bold green]✓ Applied dimensions to {room.id} with {len(room.boundary) if room.boundary else 0} boundary points[/]")
                        
            except Exception as room_error:
                console.print(f"[bold red]✗ Error applying dimensions: {room_error}[/]")
                raise room_error
                    
            ctx.state.scene_definition.rooms.extend(generated_rooms)
            console.print(
                f"[bold cyan]✓ Successfully generated {len(generated_rooms)} room(s):[/] {[room.id for room in generated_rooms]}"
            )

        return DesignLoopEntry()


class DesignLoopEntry(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> End[Scene]:
        console.print("[bold yellow]Entering room design loop...[/]")
        if ctx.state.current_room_index < len(ctx.state.scene_definition.rooms):
            console.print("[magenta]Decision:[/] Design next room.")
            subgraph_result = await room_design_graph.run(
                RoomDesignAgent(ctx.state.initial_number)
            )
            ctx.state.scene_definition.rooms.append(subgraph_result)
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
        # user_prompt = "By the way, I have a quick question: are you able to read the deps (the PlacementState)?"
        # user_prompt = "Could you repeat exactly what was provided to you (in terms of the depedencies) into the 'reasoning' output?"
        # user_prompt = "Were you provided the current room boundaries (list[Vector2])? What is it?" # -> NO!
        # user_prompt = "Are you able to see the visualized image of the room?" 
        user_prompt = ""

        if user_prompt != "":
            response = await placement_agent.run(
                user_prompt=user_prompt, deps=ctx.state
            )
            # response = await placement_agent.run(ctx.state, user_prompt=user_prompt)
            # NOTE: when not using a kwarg, the first arg is understood as user prompt.
        else:
            response = await placement_agent.run(deps=ctx.state)

        if DEBUG:
            print(f"[PlacementAgent]: {response.output.reasoning}")
            print(f"[PlacementAgent]: {response.output.decision}")

        if response.output.decision == "finalize":
            return End(ctx.state.room)
        else:
            ctx.state.room = response.output.placement_action.updated_room
            return VisualFeedback()


class VisualFeedback(BaseNode[PlacementState]):
    async def run(self, ctx: GraphRunContext[PlacementState]) -> PlacementAgent:
        room_data = pydantic_to_dict(ctx.state.room)
        blender.parse_room_definition(room_data)
        renders = blender.render_top_down()
        prev_room = ctx.state.room
        prev_room.viz.append(renders)
        ctx.state.room_history.append(prev_room)
        return PlacementAgent()


class UpdateScene(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> DesignLoopEntry:
        """Merges the result from the room design subgraph back into the main state."""
        console.print("[bold cyan]Executing Node:[/] update_main_state_after_design")
        # The room has already been modified in place by RoomDesignAgent
        # Just increment the counter to move to the next room
        ctx.state.current_room_index += 1
        return DesignLoopEntry()


# --- Graph Definition ---
main_graph = Graph(
    nodes=[MetadataAgent, BuildingPlanAgent, FloorPlanAgent, DesignLoopEntry, RoomDesignAgent, UpdateScene],
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

placement_graph = Graph(
    nodes=[
        PlacementAgent,
        VisualFeedback,
    ],
    state_type=PlacementState,  # hmm
)

app = main_graph
