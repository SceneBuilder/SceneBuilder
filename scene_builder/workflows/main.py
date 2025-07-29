from typing import TypedDict, List, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import Send
from langgraph.prebuilt import ToolNode
from rich.console import Console
from rich.panel import Panel

from scene_builder.tools.object_database import query_object_database

# import pkl
# # Load the Pkl scene definitions
# # Note: This assumes the .pkl files will be compiled to Python modules.
# # We will need to set up a build step for this later.
# # from scene_builder.definitions import scene

console = Console()

# --- Placeholder Definitions (to be replaced by Pkl-generated code) ---
class Vector3:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z
    def __repr__(self):
        return f"Vector3(x={self.x}, y={self.y}, z={self.z})"

class Object:
    def __init__(self, id, name, source, sourceId, position, rotation, scale):
        self.id = id
        self.name = name
        self.source = source
        self.sourceId = sourceId
        self.position = position
        self.rotation = rotation
        self.scale = scale
    def __repr__(self):
        return f"Object(id='{self.id}', name='{self.name}')"

class Room:
    def __init__(self, id, category, tags, objects):
        self.id = id
        self.category = category
        self.tags = tags
        self.objects = objects

    def __repr__(self):
        return f"Room(id='{self.id}', category='{self.category}', tags={self.tags}, objects={self.objects})"

class Scene:
    def __init__(self, category, tags, floorType, rooms):
        self.category = category
        self.tags = tags
        self.floorType = floorType
        self.rooms = rooms

    def __repr__(self):
        return f"Scene(category='{self.category}', tags={self.tags}, floorType='{self.floorType}', rooms={self.rooms})"


# --- State Definitions ---
class MainState(TypedDict):
    user_input: str
    scene_definition: Scene
    plan: str
    messages: Annotated[list, add_messages]
    current_room_index: int

class RoomDesignState(TypedDict):
    room: Room
    messages: Annotated[list, add_messages]


# --- Room Design Subgraph ---
tools = [query_object_database]
tool_node = ToolNode(tools)

def room_design_agent_node(state: RoomDesignState) -> RoomDesignState:
    """This node simulates an LLM call that can use tools."""
    console.print("[bold cyan]Executing Node:[/] room_design_agent_node")
    
    # In a real implementation, this would be an LLM call.
    # For now, we'll just hardcode a tool call.
    tool_call_message = ("tool_code", "query_object_database('a modern sofa')")
    
    # Simulate finding a sofa and adding it to the room
    sofa_data = query_object_database("a modern sofa")[0]
    new_object = Object(
        id=sofa_data["id"],
        name=sofa_data["name"],
        source=sofa_data["source"],
        sourceId=sofa_data["id"],
        position=Vector3(0, 0, 0),
        rotation=Vector3(0, 0, 0),
        scale=Vector3(1, 1, 1)
    )
    state["room"].objects.append(new_object)
    
    return {
        "room": state["room"],
        "messages": [("assistant", f"Added object {new_object.name} to room.")]
    }


room_design_builder = StateGraph(RoomDesignState)
room_design_builder.add_node("agent", room_design_agent_node)
room_design_builder.add_node("tools", tool_node)

room_design_builder.add_edge(START, "agent")
room_design_builder.add_conditional_edges(
    "agent",
    # This simple router always calls the tool node if there are tool calls,
    # and otherwise finishes.
    lambda x: "tools" if x.get("messages", [])[-1].tool_calls else END,
)
room_design_builder.add_edge("tools", "agent")

room_design_subgraph = room_design_builder.compile()


# --- Main Graph Nodes ---
def metadata_agent(state: MainState) -> MainState:
    console.print("[bold cyan]Executing Agent:[/] Metadata Agent")
    initial_scene = Scene("residential", ["modern", "minimalist"], "single", [])
    return {"scene_definition": initial_scene, "messages": [("assistant", "Scene metadata created.")]}

def scene_planning_agent(state: MainState) -> MainState:
    console.print("[bold cyan]Executing Agent:[/] Scene Planning Agent")
    plan = "1. Create a living room.\n2. Add a sofa."
    return {"plan": plan, "messages": [("assistant", "Scene plan created.")]}

def floor_plan_agent(state: MainState) -> MainState:
    console.print("[bold cyan]Executing Agent:[/] Floor Plan Agent")
    living_room = Room("living_room_1", "living_room", ["main"], [])
    state["scene_definition"].rooms.append(living_room)
    return {"scene_definition": state["scene_definition"], "messages": [("assistant", "Floor plan created.")]}

def update_main_state_after_design(state: MainState) -> MainState:
    """Merges the result from the room design subgraph back into the main state."""
    console.print("[bold cyan]Executing Node:[/] update_main_state_after_design")
    designed_room = state.pop("room", None)
    if designed_room:
        state["scene_definition"].rooms[state["current_room_index"]] = designed_room
    state["current_room_index"] += 1
    return state

def design_loop_entry(state: MainState) -> MainState:
    """A pass-through node to act as the entry point for the room design loop."""
    console.print("[bold yellow]Entering room design loop...[/]")
    return state

# --- Router ---
def room_design_router(state: MainState):
    """Routes to the room design subgraph or ends the workflow."""
    console.print("[bold magenta]Executing Router:[/] room_design_router")
    if state["current_room_index"] < len(state["scene_definition"].rooms):
        console.print("[magenta]Decision:[/] Design next room.")
        room_to_design = state["scene_definition"].rooms[state["current_room_index"]]
        return Send("room_design_agent", {"room": room_to_design, "messages": []})
    else:
        console.print("[magenta]Decision:[/] Finish.")
        return END


# --- Graph Definition ---
workflow_builder = StateGraph(MainState)

workflow_builder.add_node("metadata_agent", metadata_agent)
workflow_builder.add_node("scene_planning_agent", scene_planning_agent)
workflow_builder.add_node("floor_plan_agent", floor_plan_agent)
workflow_builder.add_node("design_loop_entry", design_loop_entry)
workflow_builder.add_node("room_design_agent", room_design_subgraph)
workflow_builder.add_node("update_state", update_main_state_after_design)

workflow_builder.set_entry_point("metadata_agent")
workflow_builder.add_edge("metadata_agent", "scene_planning_agent")
workflow_builder.add_edge("scene_planning_agent", "floor_plan_agent")
workflow_builder.add_edge("floor_plan_agent", "design_loop_entry")

workflow_builder.add_conditional_edges("design_loop_entry", room_design_router)

workflow_builder.add_edge("room_design_agent", "update_state")
workflow_builder.add_edge("update_state", "design_loop_entry")

app = workflow_builder.compile()


# --- Main Execution ---
if __name__ == "__main__":
    console.print(Panel("[bold green]Running SceneBuilder Workflow[/]", expand=False))
    initial_state = {
        "user_input": "Create a modern, minimalist living room.",
        "messages": [("user", "Create a modern, minimalist living room.")],
        "current_room_index": 0
    }
    for i, event in enumerate(app.stream(initial_state, stream_mode="values")):
        console.print(Panel(f"[bold yellow]Workflow Step {i+1}[/]", expand=False))
        console.print(event)
