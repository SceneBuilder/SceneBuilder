from typing import TypedDict, List, Annotated
from langgraph.graph import StateGraph, START, END, Send
from langgraph.graph.message import add_messages

# import pkl
# # Load the Pkl scene definitions
# # Note: This assumes the .pkl files will be compiled to Python modules.
# # We will need to set up a build step for this later.
# # from scene_builder.definitions import scene


# --- Placeholder Definitions (to be replaced by Pkl-generated code) ---
class Vector3:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z
    def __repr__(self):
        return f"Vector3(x={self.x}, y={self.y}, z={self.z})"

class Object:
    def __init__(self, id, name, position, rotation, scale):
        self.id = id
        self.name = name
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
def add_object_node(state: RoomDesignState) -> RoomDesignState:
    """Adds a placeholder object to the room."""
    print("Executing Node: add_object")
    new_object = Object("sofa_1", "Sofa", Vector3(0, 0, 0), Vector3(0, 0, 0), Vector3(1, 1, 1))
    state["room"].objects.append(new_object)
    return {"room": state["room"], "messages": [("assistant", f"Added object {new_object.name} to room.")]}

room_design_builder = StateGraph(RoomDesignState)
room_design_builder.add_node("add_object", add_object_node)
room_design_builder.add_edge(START, "add_object")
room_design_builder.add_edge("add_object", END)
# The subgraph is now a runnable that accepts RoomDesignState and outputs the final RoomDesignState
room_design_subgraph = room_design_builder.compile()


# --- Main Graph Nodes ---
def metadata_agent(state: MainState) -> MainState:
    print("Executing Metadata Agent...")
    initial_scene = Scene("residential", ["modern", "minimalist"], "single", [])
    return {"scene_definition": initial_scene, "messages": [("assistant", "Scene metadata created.")]}

def scene_planning_agent(state: MainState) -> MainState:
    print("Executing Scene Planning Agent...")
    plan = "1. Create a living room.\n2. Add a sofa."
    return {"plan": plan, "messages": [("assistant", "Scene plan created.")]}

def floor_plan_agent(state: MainState) -> MainState:
    print("Executing Floor Plan Agent...")
    living_room = Room("living_room_1", "living_room", ["main"], [])
    state["scene_definition"].rooms.append(living_room)
    return {"scene_definition": state["scene_definition"], "messages": [("assistant", "Floor plan created.")]}

def update_main_state_after_design(state: MainState) -> MainState:
    """Merges the result from the room design subgraph back into the main state."""
    print("Executing update_main_state_after_design...")
    # The output of the subgraph is automatically merged into the state.
    # We need to take the designed room and update our scene_definition.
    designed_room = state.pop("room", None) # Use .pop to get and remove the key
    if designed_room:
        state["scene_definition"].rooms[state["current_room_index"]] = designed_room
    state["current_room_index"] += 1
    return state

# --- Router ---
def room_design_router(state: MainState):
    """Routes to the room design subgraph or ends the workflow."""
    print("Executing Router: room_design_router")
    if state["current_room_index"] < len(state["scene_definition"].rooms):
        print("Decision: Design next room.")
        room_to_design = state["scene_definition"].rooms[state["current_room_index"]]
        # This Send object directs the workflow to the subgraph
        # and provides the specific input it needs.
        return Send("room_design_agent", {"room": room_to_design, "messages": []})
    else:
        print("Decision: Finish.")
        return END


# --- Graph Definition ---
workflow_builder = StateGraph(MainState)

workflow_builder.add_node("metadata_agent", metadata_agent)
workflow_builder.add_node("scene_planning_agent", scene_planning_agent)
workflow_builder.add_node("floor_plan_agent", floor_plan_agent)
# The subgraph is a node in the main graph
workflow_builder.add_node("room_design_agent", room_design_subgraph)
# This node updates the main state after the subgraph is done
workflow_builder.add_node("update_state", update_main_state_after_design)

workflow_builder.set_entry_point("metadata_agent")
workflow_builder.add_edge("metadata_agent", "scene_planning_agent")
workflow_builder.add_edge("scene_planning_agent", "floor_plan_agent")

# After the floor plan, the router decides what to do next.
workflow_builder.add_conditional_edges("floor_plan_agent", room_design_router)

# After the subgraph runs, we update the main state.
workflow_builder.add_edge("room_design_agent", "update_state")
# After updating the state, we loop back to the router to check for more rooms.
workflow_builder.add_edge("update_state", "floor_plan_agent")

app = workflow_builder.compile()


# --- Main Execution ---
if __name__ == "__main__":
    print("Running SceneBuilder workflow...")
    initial_state = {
        "user_input": "Create a modern, minimalist living room.",
        "messages": [("user", "Create a modern, minimalist living room.")],
        "current_room_index": 0
    }
    for event in app.stream(initial_state, stream_mode="values"):
        print("\n--- Workflow Step ---")
        print(event)
