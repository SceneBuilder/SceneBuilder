import asyncio
import os
from pathlib import Path

from pydantic_graph import GraphRunResult

from scene_builder.database.object import ObjectDatabase
from scene_builder.decoder import blender
from scene_builder.definition.scene import Object, ObjectBlueprint, Room, Vector2, Scene
from scene_builder.definition.plan import RoomPlan
from scene_builder.importer.test_asset_importer import search_test_asset
from scene_builder.logging import configure_logging
from scene_builder.nodes.design import (
    RoomDesignNode,
    RoomDesignVisualFeedback,
    room_design_graph,
)
# from scene_builder.nodes.placement import PlacementNode, placement_graph, VisualFeedback
from scene_builder.nodes.placement import PlacementNode, PlacementVisualFeedback, placement_graph
# from scene_builder.nodes.feedback import VisualFeedback
from scene_builder.utils.conversions import pydantic_from_yaml
from scene_builder.utils.image import create_gif_from_images
# from scene_builder.workflow.graphs import (
#     room_design_graph,
#     placement_graph,
# )
from scene_builder.workflow.states import PlacementState, RoomDesignState

configure_logging(level="DEBUG")

# Params
SAVE_DIR = "assets"

# Data
CLASSROOM_ROOM_DESCRIPTION = """\
### Classroom Space: A Sensory and Functional Blueprint

**Overall Atmosphere & Entry:**
Upon entering, the space immediately greets you with a unique olfactory signature: the sharp, slightly sweet smell of dry-erase markers, the warm, waxy scent of crayons, and the faint, papery dust of countless books. The primary sound is a low, almost subliminal hum from the overhead fluorescent light panels, which cast a flat, even, and unforgiving light across the room. The main door is heavy, with a steel handle that is cool to the touch, and it closes with a solid, echoing *thump*. The floor is a vast expanse of linoleum tile—cold, hard, and resilient, but covered in a galaxy of fine scratches and the occasional dark scuff mark from generations of shifting chairs and dragged backpacks. The room feels pregnant with contained, chaotic energy.

**The Command Wall (Front of Room / Teaching Zone):**
The front wall is the room's focal point, the stage. It is dominated by a vast, glossy-white expanse of whiteboard, hungry for colorful markers. The surface is smooth and cool, reflecting the overhead lights with a sterile glare. The air directly in front of it smells the strongest of chemical cleaner and the ghost of a thousand erased ideas. This area demands a central podium or a simple, functional teacher's desk—a command center from which to orchestrate the day. This zone needs to be clearly visible from every other point in the room. The floor space directly in front of the board must remain open, a buffer for movement and instruction.

**The Sea of Learning (Central Floor Space):**
Stretching from the teaching wall is a wide, open sea of scuffed linoleum tile, a neutral battlefield of beige and gray. This expanse is the primary zone for student focus. It needs to hold individual pods of concentration but must also have the flexibility to coalesce into collaborative islands. The furniture here must be durable and movable. Imagine the grating sound of thirty small chairs scooting at once. The surfaces of the desks or tables should be hard and smooth, able to withstand frantic scribbling, spilled glue, and the drumming of impatient fingers. This area is the room's workhorse.

**The Quiet Grotto (Reading & Decompression Zone):**
Tucked into the far-left corner, away from the main door's traffic, is a pocket of intentional quiet. This zone is bathed in the softer, more forgiving natural light from a large window. The floor here should feel different—a low-pile, durable rug that absorbs sound and invites sitting, its texture a welcome contrast to the hard linoleum. The air here is stiller. This zone craves low, accessible shelving, crammed with the comforting scent of old and new books. It is a space for soft, yielding forms: beanbags that sigh when sat upon, floor cushions, or perhaps a small, worn-out couch. It is a refuge.

**The Creation Station (Wet & Active Zone):**
Opposite the quiet grotto, along the wall with the room's only sink, is the zone of messy creation. The floor here is exclusively the easy-to-clean linoleum, prepared for spills of paint, water, and clay. A long, countertop-height workspace is essential here, with a surface that is non-porous and stain-resistant. The faucet's metallic tang and the faint smell of damp clay and tempera paint define this corner. This area requires robust storage for bulky, awkward supplies: wide drawers for paper, deep bins for blocks, and sturdy shelving for jars of brushes and bottles of glue.

**The Periphery (Storage & Display):**
The remaining wall space is dedicated to storage and identity. It is a vertical landscape. Large cork bulletin boards, with their distinct, earthy smell and porous texture, await staples and thumbtacks. Their surfaces are a chaotic collage of papers. Below them, a long, low bank of cubbies or shelving is needed—a place for the personal clutter of backpacks and lunchboxes. These surfaces should be tough and scratch-resistant. This is the room's skin, holding its memories and its tools.
"""

GARAGE_ROOM_DESCRIPTION = """\
### A sportscar garage

The garage has a diverse set of sports car in a grid layout.
"""

KITCHEN_ROOM_DESCRIPTION = """\
A modern residential kitchen with central island, full appliances, and ample counter space for cooking and meal preparation.
"""

BEDROOM_ROOM_DESCRIPTION = """\
A cozy master bedroom with a queen bed, nightstands, dresser, and reading chair by the window.
"""

OFFICE_ROOM_DESCRIPTION = """\
A home office setup with desk, office chair, bookshelf, filing cabinet, and computer workstation.
"""

LIVING_ROOM_DESCRIPTION = """\
A comfortable living room with sectional sofa, coffee table, TV entertainment center, and accent lighting.
"""

BATHROOM_ROOM_DESCRIPTION = """\
A full bathroom with toilet, sink vanity, bathtub/shower combo, and storage cabinet.
"""

DINING_ROOM_DESCRIPTION = """\
A formal dining room with dining table for 6, matching chairs, sideboard, and chandelier.
"""

LIBRARY_ROOM_DESCRIPTION = """\
A quiet library space with wall-to-wall bookshelves, reading tables, comfortable armchairs, and study lamps.
"""

GYM_ROOM_DESCRIPTION = """\
A home gym with exercise equipment including treadmill, weight rack, exercise bike, and yoga mats.
"""

RESTAURANT_KITCHEN_DESCRIPTION = """\
A commercial restaurant kitchen with industrial equipment, prep stations, walk-in cooler, and service line.
"""

RETAIL_STORE_DESCRIPTION = """\
A retail clothing store with display racks, fitting rooms, checkout counter, and mannequins.
"""

HOSPITAL_ROOM_DESCRIPTION = """\
A hospital patient room with medical bed, monitoring equipment, visitor chairs, and medical supply cabinet.
"""

LABORATORY_DESCRIPTION = """\
A scientific laboratory with lab benches, fume hoods, microscopes, centrifuges, and chemical storage.
"""

WAREHOUSE_DESCRIPTION = """\
A storage warehouse with industrial shelving units, pallet racks, loading dock area, and forklift.
"""

CONFERENCE_ROOM_DESCRIPTION = """\
A corporate conference room with large table, office chairs, projector screen, and presentation equipment.
"""

ART_GALLERY_DESCRIPTION = """\
An art gallery space with white walls, track lighting, display pedestals, and artwork hanging systems.
"""

BAR_DESCRIPTION = """\
A cocktail bar with bar counter, stools, liquor shelves, draft beer taps, and lounge seating area.
"""

THEATER_BACKSTAGE_DESCRIPTION = """\
A theater backstage area with costume racks, makeup stations, prop storage, and quick-change areas.
"""

FACTORY_FLOOR_DESCRIPTION = """\
A manufacturing floor with assembly line equipment, workstations, tool storage, and safety equipment.
"""

SMALL_RECTANGULAR_BOUNDARY = [
    Vector2(x=4.0, y=2.0),
    Vector2(x=-4.0, y=2.0),
    Vector2(x=-4.0, y=-2.0),
    Vector2(x=4.0, y=-2.0),
]

LARGE_RECTANGULAR_BOUNDARY = [
    Vector2(x=6.0, y=4.0),
    Vector2(x=-6.0, y=4.0),
    Vector2(x=-6.0, y=-4.0),
    Vector2(x=6.0, y=-4.0),
]

SQUARE_BOUNDARY = [
    Vector2(x=3.0, y=3.0),
    Vector2(x=-3.0, y=3.0),
    Vector2(x=-3.0, y=-3.0),
    Vector2(x=3.0, y=-3.0),
]

COMMERCIAL_BOUNDARY = [
    Vector2(x=8.0, y=6.0),
    Vector2(x=-8.0, y=6.0),
    Vector2(x=-8.0, y=-6.0),
    Vector2(x=8.0, y=-6.0),
]

# Test cases dictionary mapping case names to room descriptions and boundaries
TEST_CASES = {
    "classroom": {
        "description": CLASSROOM_ROOM_DESCRIPTION,
        "boundary": SMALL_RECTANGULAR_BOUNDARY,
        "room_id": "classroom-01",
    },
    "garage": {
        "description": GARAGE_ROOM_DESCRIPTION,
        "boundary": LARGE_RECTANGULAR_BOUNDARY,
        "room_id": "garage-01",
    },
    "kitchen": {
        "description": KITCHEN_ROOM_DESCRIPTION,
        "boundary": LARGE_RECTANGULAR_BOUNDARY,
        "room_id": "kitchen-01",
    },
    "bedroom": {
        "description": BEDROOM_ROOM_DESCRIPTION,
        "boundary": SMALL_RECTANGULAR_BOUNDARY,
        "room_id": "bedroom-01",
    },
    "office": {
        "description": OFFICE_ROOM_DESCRIPTION,
        "boundary": SMALL_RECTANGULAR_BOUNDARY,
        "room_id": "office-01",
    },
    "living_room": {
        "description": LIVING_ROOM_DESCRIPTION,
        "boundary": LARGE_RECTANGULAR_BOUNDARY,
        "room_id": "living-room-01",
    },
    "bathroom": {
        "description": BATHROOM_ROOM_DESCRIPTION,
        "boundary": SQUARE_BOUNDARY,
        "room_id": "bathroom-01",
    },
    "dining_room": {
        "description": DINING_ROOM_DESCRIPTION,
        "boundary": SMALL_RECTANGULAR_BOUNDARY,
        "room_id": "dining-room-01",
    },
    "library": {
        "description": LIBRARY_ROOM_DESCRIPTION,
        "boundary": LARGE_RECTANGULAR_BOUNDARY,
        "room_id": "library-01",
    },
    "gym": {
        "description": GYM_ROOM_DESCRIPTION,
        "boundary": LARGE_RECTANGULAR_BOUNDARY,
        "room_id": "gym-01",
    },
    "restaurant_kitchen": {
        "description": RESTAURANT_KITCHEN_DESCRIPTION,
        "boundary": COMMERCIAL_BOUNDARY,
        "room_id": "restaurant-kitchen-01",
    },
    "retail_store": {
        "description": RETAIL_STORE_DESCRIPTION,
        "boundary": COMMERCIAL_BOUNDARY,
        "room_id": "retail-store-01",
    },
    "hospital_room": {
        "description": HOSPITAL_ROOM_DESCRIPTION,
        "boundary": LARGE_RECTANGULAR_BOUNDARY,
        "room_id": "hospital-room-01",
    },
    "laboratory": {
        "description": LABORATORY_DESCRIPTION,
        "boundary": COMMERCIAL_BOUNDARY,
        "room_id": "laboratory-01",
    },
    "warehouse": {
        "description": WAREHOUSE_DESCRIPTION,
        "boundary": COMMERCIAL_BOUNDARY,
        "room_id": "warehouse-01",
    },
    "conference_room": {
        "description": CONFERENCE_ROOM_DESCRIPTION,
        "boundary": LARGE_RECTANGULAR_BOUNDARY,
        "room_id": "conference-room-01",
    },
    "art_gallery": {
        "description": ART_GALLERY_DESCRIPTION,
        "boundary": COMMERCIAL_BOUNDARY,
        "room_id": "art-gallery-01",
    },
    "bar": {
        "description": BAR_DESCRIPTION,
        "boundary": LARGE_RECTANGULAR_BOUNDARY,
        "room_id": "bar-01",
    },
    "theater_backstage": {
        "description": THEATER_BACKSTAGE_DESCRIPTION,
        "boundary": LARGE_RECTANGULAR_BOUNDARY,
        "room_id": "theater-backstage-01",
    },
    "factory_floor": {
        "description": FACTORY_FLOOR_DESCRIPTION,
        "boundary": COMMERCIAL_BOUNDARY,
        "room_id": "factory-floor-01",
    }
}

obj_db = ObjectDatabase()


def test_single_object_placement(hardcoded_object=True):
    if hardcoded_object:
        object = search_test_asset("classroom_table")
    else:
        object = obj_db.query("classroom table")[0]
        # NOTE: This doesn't involve ShoppingAgent and instead uses the first asset returned.

    initial_state = PlacementState(
        room=Room(
            id="classroom-01",
            boundary=SMALL_RECTANGULAR_BOUNDARY,
        ),
        room_plan=RoomPlan(room_description=CLASSROOM_ROOM_DESCRIPTION),
        what_to_place=object,
    )

    blender.load_template("test_assets/scenes/classroom.blend", clear_scene=True)

    async def run_graph():
        # return await room_design_graph.run(PlacementAgent(), state=initial_state)
        return await placement_graph.run(PlacementNode(), state=initial_state)
        # return await placement_graph.run(PlacementAgent(), deps=initial_state)
        # PROBLEM:
        # If I pass `PlacementState` as a `state`, then it tries to enter the LLM's prompt
        # and fails to do so, because it's not a straightforward mapping composed of media types.
        # If I pass it as a dependency, then it's not available as a state.
        # (I guess I could just copy it from deps to state in the run() func, though.)
        # I do want the LLM to output a PlacementState. I think one approach to do it is
        # to serialize into string and then pass into LLM (or lowkey maybe deps already does that),
        # then specify output_model(?) to have it reconstruct another PlacementState.

        # Phew. Not sure if this is actually a worthwhile effort or overengineering for nothing... hmm.
        # The most simple workflow possible is just having it create any scene lang repr, then create in Blender,
        # and then show photos, and let it repeat. Doing the control entirely in natural language.

        # Honestly, doing this a few times might be an incredibly good idea.

    result: PlacementState = asyncio.run(run_graph())

    room_vizs = []
    for step, state in enumerate(result.room_history):
        room_vizs.append(state.viz[0])

    create_gif_from_images(
        room_vizs, f"test_output/single_object_placement_{hardcoded_object=}.gif"
    )
    blender.save_scene(f"test_output/single_object_placement_{hardcoded_object=}.blend")


def test_partial_room_completion():
    # NOTE: option 1
    # room = Room(
    #     id="classroom-01",
    #     category="education",
    #     boundary=SMALL_RECTANGULAR_BOUNDARY,
    # )

    # NOTE: option 2
    room = pydantic_from_yaml("test_assets/scenes/classroom.yaml", Scene).rooms[0]

    initial_state = PlacementState(
        room=room,
        room_plan=RoomPlan(),
        what_to_place=search_test_asset("classroom_table"),
    )

    blender.load_template("test_assets/scenes/classroom.blend", clear_scene=True)

    async def run_graph():
        return await placement_graph.run(PlacementVisualFeedback(), state=initial_state)

    # TODO: log each step, save info GIF, video, or markdown(?).

    result: GraphRunResult[PlacementState] = asyncio.run(run_graph())

    room_vizs = []
    for step, state in enumerate(result.state.room_history):
        room_vizs.append(state.viz[-1])

    create_gif_from_images(room_vizs, "test_output/partial_room_completion.gif")

    blender.save_scene("tests/test_partial_room_completion.blend")


def test_room_design_workflow(case: str):
    if case not in TEST_CASES:
        raise ValueError(f"Unknown test case: {case}. Available cases: {list(TEST_CASES.keys())}")

    test_data = TEST_CASES[case]

    initial_room_state = RoomDesignState(
        room=Room(
            id=test_data["room_id"],
            boundary=test_data["boundary"],
        ),
        room_plan=RoomPlan(room_description=test_data["description"]),
    )
    blender._clear_scene()

    async def run_graph():
        # return await room_design_graph.run(RoomDesignNode(), state=initial_room_state)
        return await room_design_graph.run(
            RoomDesignVisualFeedback(), state=initial_room_state
        )

    result: RoomDesignState = asyncio.run(run_graph())
    blender.save_scene(f"test_output/test_room_design_workflow_{case}.blend")


if __name__ == "__main__":
    # test_single_object_placement(hardcoded_object=True)
    # test_single_object_placement(hardcoded_object=False)
    # test_partial_room_completion()
    # test_room_design_workflow("classroom")
    test_room_design_workflow("garage")
