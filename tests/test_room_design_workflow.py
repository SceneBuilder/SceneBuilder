import asyncio
import os
from pathlib import Path

from pydantic_graph import GraphRunResult

from scene_builder.config import TEST_ASSET_DIR
from scene_builder.database.object import ObjectDatabase
from scene_builder.decoder import blender
from scene_builder.definition.plan import RoomPlan
from scene_builder.definition.scene import Object, ObjectBlueprint, Room, Vector2, Scene
from scene_builder.importer.test_asset_importer import search_test_asset
from scene_builder.logging import configure_logging
from scene_builder.nodes.design import (
    RoomDesignNode,
    # RoomDesignVisualFeedback,
    room_design_graph,
)

# from scene_builder.nodes.placement import PlacementNode, placement_graph, VisualFeedback
from scene_builder.nodes.placement import (
    PlacementNode,
    PlacementVisualFeedback,
    placement_graph,
)

# from scene_builder.nodes.feedback import VisualFeedback
from scene_builder.msd_integration.loader import MSDLoader
from scene_builder.utils.conversions import pydantic_from_yaml
from scene_builder.utils.image import create_gif_from_images
from scene_builder.utils.pydantic import save_yaml
from scene_builder.workflow.agents import generic_agent, room_design_agent

# from scene_builder.workflow.graphs import (
#     room_design_graph,
#     placement_graph,
# )
from scene_builder.workflow.states import PlacementState, RoomDesignState

configure_logging(level="DEBUG")
# configure_logging(level="DEBUG", enable_logfire=False)

# Params
SAVE_DIR = "assets"

# Data
# single room
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

DIFFUSCENE_DESCRIPTION = """\
The room has a dining table and two dining chairs. The second dining chair is to the right of the first dining chair. There is a pendant lamp above the dining table. 
"""

# multi-room
APARTMENT_UNIT_DESCRIPTION = """\
This spacious, three-bedroom, two-bathroom apartment occupies the entire third floor of a pre-war building, boasting large, bay-style windows that flood the living room and master bedroom with natural light. 
The open-concept living and dining area features original parquet flooring, a decorative fireplace with intricate tile work, and built-in bookshelves. 
The recently renovated kitchen includes stainless steel appliances, a large island with seating, and ample pantry space, while a dedicated laundry room adds to its family-friendly appeal. 
The apartment also includes a small balcony off the dining area, offering a charming view of the neighborhood park.
"""

COMMUNITY_HOSPITAL_UNIT_DESCRIPTION = """\
Set back from the main road, the Hillcrest Community Hospital is a single-story, sprawling brick building with a newer glass-fronted wing. 
Inside, the main lobby's polished floors and bright lighting lead off into several distinct areas.

- The Emergency Department:
    Located to the right of the main entrance, the ER is a compact and efficient space with six curtained bays organized around a central, circular nurses' station. 
    The air is filled with the low beeps of monitors and the rustle of scrubs. While an undercurrent of urgency is always present, the atmosphere is generally one of focused calm rather than chaos.

- Inpatient Rooms: 
    The main corridor leads to the patient wing, where private and semi-private rooms line the hall. 
    Each room is painted a soft, neutral tone and features a large, low window that looks out onto the hospital's quiet grounds. 
    The furnishings are simple and functional: a standard adjustable bed, a bedside table, a wall-mounted TV, and a single vinyl armchair for visitors.

- The Surgical Suite: 
    Accessed via a set of automated double doors, the corridor to the operating rooms is noticeably cooler and more sterile. 
    The lighting is brighter and whiter here. 
    Through small porthole windows in the doors, one can glimpse the gleaming stainless steel equipment and the focused movements of the surgical teams within the two main operating rooms.

- Radiology and Imaging: 
    This department is a quiet, tech-focused area down a less-trafficked hall. 
    It contains a small waiting area with just a handful of chairs. 
    The main imaging room houses a large, modern CT scanner whose low, powerful hum is audible even from the hallway. 
    A smaller room is dedicated to standard X-rays, its heavy, lead-lined door often slightly ajar.

- The Cafeteria: 
    Situated in the modern glass wing, the "Hillcrest Café" serves as a small social hub. 
    It's a bright space with a handful of small tables and a counter serving coffee, sandwiches, and hot meals. 
    The comforting smell of fresh coffee and baked goods offers a welcome contrast to the clinical scents of the rest of the hospital.
"""

STARTUP_OFFICE_UNIT_DESCRIPTION = """\
The office occupies a single, open-plan floor in a renovated brick warehouse, with exposed ductwork running across the high ceiling. 
Simple, white IKEA desks are arranged in collaborative pods, each littered with laptops, secondary monitors, and empty coffee mugs. 
One wall is painted with whiteboard paint and is covered in a chaotic web of diagrams, code snippets, and inside jokes. 
In the corner, a small kitchenette features a high-end espresso machine as its centerpiece, surrounded by shelves stocked with protein bars and energy drinks. 
The space hums with the clicking of keyboards and quiet, focused conversation, all underscored by the faint smell of stale pizza and fresh coffee.
"""

CITY_HALL_UNIT_DESCRIPTION = """\
Standing at the head of the town square, the city hall is a dignified building made of weathered grey stone, with tall, narrow windows and a small clock tower that chimes on the hour. 
Wide granite steps lead up to a pair of heavy, bronze-handled oak doors. 
The interior lobby is quiet and formal, with high ceilings, polished terrazzo floors, and walls paneled in dark wood. 
A long, marble-topped counter serves as the hub for all public business—from permits to water bills—while a large, glass-encased bulletin board displays official notices and community announcements. 
The air carries the faint, layered scent of old paper, floor polish, and damp wool from raincoats on a wet day.

More information about the rooms:

- Clerk's Office and Treasury: This would be the main public service area behind the long marble counter. It's where residents would go to pay taxes and water bills, register to vote, and apply for business or marriage licenses.

- Planning and Zoning Department: A smaller office, often just off the main lobby, where contractors and homeowners would submit building plans, apply for permits, and review zoning maps laid out under a glass countertop.

- Municipal Courtroom / Council Chambers: A single, multi-purpose room serving as both a courtroom for minor traffic and ordinance violations and as the chamber for city council meetings. It would be formally decorated with dark wood benches for the public, a raised dais for the judge or council members, and the state and national flags.

- Public Records Room: A small room or alcove with a desk and a microfilm reader or computer terminal where citizens could look up property deeds, historical ordinances, and other public documents.

- The Mayor's Office: Typically the largest and best-appointed office, often in a corner overlooking the town square. It would feature a large wooden desk, portraits of past mayors, and shelves of law books and local histories.

- City Manager's Office: A more functional, working office where the day-to-day administration of the city is managed. You'd likely find blueprints, binders full of reports, and city maps.

- Conference Rooms: One or two smaller rooms with a large table and chairs used for internal meetings between department heads and for public committee meetings.

- Records Vault / Archives: A secure, often climate-controlled room filled with file cabinets and shelves holding the city's historical records, old ledgers, and official documents.
"""

PIZZERIA_UNIT_DESCRIPTION = """\
Tucked into a small brick storefront, "Gino's Pizzeria" is a cozy, no-frills neighborhood institution. 
The air inside is warm and heavy with the rich, overlapping smells of garlic, simmering tomato sauce, and melting cheese. 
The room is simple, with a handful of wooden booths upholstered in cracked red vinyl and walls adorned with faded photos of Italy and local sports memorabilia. 
The centerpiece is the open kitchen behind a low counter, where you can watch cooks stretch dough, scatter toppings, and use long wooden paddles to slide pies into the fiery mouth of a large, gas-fired deck oven. 
The constant sounds are the happy chatter of families, the ring of the phone for takeout orders, and the satisfying rumble of a pizza cutter slicing through a crispy crust.
"""

LOCAL_MUSEUM_UNIT_DESCRIPTION = """\
Housed in a historic, red-brick former Carnegie Library, the Coweta County Historical Museum is a quiet repository of the area's past. 
Upon entering through the grand, arched doorway, the air feels cool and still, carrying the faint, dry scent of old paper, aged wood, and bookbinding glue. 
The main gallery's original hardwood floors creak softly underfoot, a sound that echoes in the high-ceilinged room. 
Sunlight streams through tall, Palladian windows, illuminating glass display cases filled with Civil War artifacts, antique farming tools, faded family portraits, and local pottery. 
The only other sounds are the gentle hum of a dehumidifier preserving the delicate exhibits and the hushed, respectful tones of visitors reading the neatly typed description cards.
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
        "boundary": LARGE_RECTANGULAR_BOUNDARY,
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
    },
    "diffuscene": {
        "description": DIFFUSCENE_DESCRIPTION,
        "boundary": SMALL_RECTANGULAR_BOUNDARY,
        "room_id": "diffuscene-01",
    },
    # multi-room
    "apartment": {
        "description": APARTMENT_UNIT_DESCRIPTION,
        "floor_plan_id": "b2e1f754f164e5b7c268485ca55495c8",
    },
    "community_hospital": {
        "description": COMMUNITY_HOSPITAL_UNIT_DESCRIPTION,
        "floor_plan_id": "c223a17396ec597fdab338b0b0eb3d1b",
    },
    "startup_office": {
        "description": STARTUP_OFFICE_UNIT_DESCRIPTION,
        "floor_plan_id": "96371508c631525c872350ca7c08274b",
    },
    "city_hall": {
        "description": CITY_HALL_UNIT_DESCRIPTION,
        "floor_plan_id": "e3ec3c97ce1f83867b9d709831160c3f",
    },
    "pizzeria": {
        "description": PIZZERIA_UNIT_DESCRIPTION,
        "floor_plan_id": "26eb729493ee068f7ad0e44d9488ce8c",
    },
    "local_museum": {
        "description": LOCAL_MUSEUM_UNIT_DESCRIPTION,
        "floor_plan_id": "abeec822befbfe3d5580d932bc0947c7",
    },
}

obj_db = ObjectDatabase()
msd_loader = MSDLoader()


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

    blender.load_template(f"{TEST_ASSET_DIR}/scenes/classroom.blend", clear_scene=True)

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
    room = pydantic_from_yaml(f"{TEST_ASSET_DIR}/scenes/classroom.yaml", Scene).rooms[0]

    initial_state = PlacementState(
        room=room,
        room_plan=RoomPlan(),
        what_to_place=search_test_asset("classroom_table"),
    )

    blender.load_template(f"{TEST_ASSET_DIR}/scenes/classroom.blend", clear_scene=True)

    async def run_graph():
        return await placement_graph.run(PlacementVisualFeedback(), state=initial_state)

    # TODO: log each step, save info GIF, video, or markdown(?).

    result: GraphRunResult[PlacementState] = asyncio.run(run_graph())

    room_vizs = []
    for step, state in enumerate(result.state.room_history):
        room_vizs.append(state.viz[-1])

    create_gif_from_images(room_vizs, "test_output/partial_room_completion.gif")

    blender.save_scene("tests/test_partial_room_completion.blend")


def test_single_room_design_workflow(case: str):
    if case not in TEST_CASES:
        raise ValueError(f"Unknown test case: {case}. Available cases: {list(TEST_CASES.keys())}")

    test_data = TEST_CASES[case]
    boundary = test_data["boundary"]
    description = test_data["description"]

    initial_room_state = RoomDesignState(
        room=Room(
            id=test_data["room_id"],
            boundary=boundary,
        ),
        room_plan=RoomPlan(room_description=description),
    )
    blender._clear_scene()

    # NOTE: Big fucking warning: If `run_sync()` is ran before await {agent}.run(), it will silently get stuck. (i mean, wtf? also, it used to work just fine???)
    async def run_graph():
        # return await room_design_graph.run(RoomDesignNode(), state=initial_room_state)
        return await room_design_graph.run(
            # RoomDesignVisualFeedback(), state=initial_room_state
            RoomDesignNode(),
            state=initial_room_state,
        )

    result: RoomDesignState = asyncio.run(run_graph())
    blender.save_scene(f"test_output/test_single_room_design_workflow_{case}.blend")
    save_yaml(f"test_output/test_single_room_design_workflow_{case}.yaml")


def test_parallel_room_design_workflow(cases: list[str]):
    """
    Test parallel execution of multiple room design graphs.

    Args:
        cases: List of test case names to run in parallel
    """
    # Validate all test cases exist
    for case in cases:
        if case not in TEST_CASES:
            raise ValueError(
                f"Unknown test case: {case}. Available cases: {list(TEST_CASES.keys())}"
            )

    # Prepare initial states for each room
    initial_states = []
    for case in cases:
        test_data = TEST_CASES[case]
        boundary = test_data["boundary"]
        description = test_data["description"]

        room_state = RoomDesignState(
            room=Room(
                id=test_data["room_id"],
                boundary=boundary,
            ),
            room_plan=RoomPlan(room_description=description),
        )
        initial_states.append((case, room_state))

    # Clear the main Blender scene once at the start
    blender._clear_scene()

    async def run_graphs():
        """Run all room design graphs in parallel using asyncio.gather."""
        results = await asyncio.gather(
            *[
                room_design_graph.run(RoomDesignNode(), state=state)
                for (case, state) in initial_states
            ]
        )
        return results

    # Execute all graphs in parallel
    results = asyncio.run(run_graphs())

    # Save results for each room
    for (case, state), result in zip(initial_states, results):
        # Each room was designed in an isolated scene (per the implementation)
        # Save the Blender scene and YAML for each room
        blender.save_scene(f"test_output/test_multi_room_design_workflow_{case}.blend")
        save_yaml(result, f"test_output/test_multi_room_design_workflow_{case}.yaml")

    return results


def test_multi_room_design_workflow(case: str):
    if case not in TEST_CASES:
        raise ValueError(f"Unknown test case: {case}. Available cases: {list(TEST_CASES.keys())}")

    test_data = TEST_CASES[case]
    
    # Import a unit-level floor plan from MSD
    floor_plan_id = test_data["floor_plan_id"]
    scene_data = msd_loader.get_scene(floor_plan_id)

    # Start multiple instances of room_design_graph
    #   Create a copy of each room and perform origin normalization w.r.t. room boundary
    #     Store `proxy=True` and `origin_offset` attribute
    #   ^ This logic probably belongs to `DesignOrchestrator`

    # I think it's a great idea to build/render each room in an isolated scene,
    # and then create a linked copy to the higher-level (apartment) unit / building (scene).
    # I'm not sure whether Blender decoder will experience unwanted data mutation or race conditions — since it's blocking.


if __name__ == "__main__":
    # test_single_object_placement(hardcoded_object=True)
    # test_single_object_placement(hardcoded_object=False)

    # test_partial_room_completion()

    # test_single_room_design_workflow("classroom")
    # test_single_room_design_workflow("garage")
    # test_single_room_design_workflow("kitchen")
    # test_single_room_design_workflow("bedroom")
    # test_single_room_design_workflow("office")
    # test_single_room_design_workflow("living_room")
    # test_single_room_design_workflow("bathroom")
    # test_single_room_design_workflow("dining_room")
    # test_single_room_design_workflow("library")
    # test_single_room_design_workflow("gym")
    # test_single_room_design_workflow("restaurant_kitchen")
    # test_single_room_design_workflow("retail_store")
    # test_single_room_design_workflow("hospital")
    # test_single_room_design_workflow("hospital_room")
    # test_single_room_design_workflow("laboratory")
    # test_single_room_design_workflow("warehouse")
    # test_single_room_design_workflow("conference_room")
    # test_single_room_design_workflow("art_gallery")
    # test_single_room_design_workflow("bar")
    # test_single_room_design_workflow("theater_backstage")
    # test_single_room_design_workflow("factory_floor")
    # test_single_room_design_workflow("diffuscene")

    # Test parallel execution of multiple room designs
    # test_parallel_room_design_workflow(["bedroom", "office", "bathroom"])
    # test_parallel_room_design_workflow(["bedroom", "office"])
    # test_parallel_room_design_workflow(["garage", "library"])
    test_parallel_room_design_workflow(["bar", "classroom"])
    # test_parallel_room_design_workflow(["bedroom"])
