import asyncio
import os
from pathlib import Path

from pydantic_graph import GraphRunResult

from scene_builder.decoder import blender
from scene_builder.definition.scene import Object, ObjectBlueprint, Room, Vector2, Scene
from scene_builder.definition.plan import RoomPlan
from scene_builder.importer.test_asset_importer import search_test_asset
from scene_builder.utils.conversions import pydantic_from_yaml
from scene_builder.utils.image import create_gif_from_images
from scene_builder.workflow.graph import (
    room_design_graph,
    placement_graph,
    RoomDesignAgent,
    PlacementAgent,
    VisualFeedback,
)
from scene_builder.workflow.state import PlacementState

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

SMALL_RECTANGULAR_BOUNDARY = [
    Vector2(x=4.0, y=2.0),
    Vector2(x=-4.0, y=2.0),
    Vector2(x=-4.0, y=-2.0),
    Vector2(x=4.0, y=-2.0),
]


def test_single_object_placement():
    initial_state = PlacementState(
        room=Room(
            id="classroom-01",
            boundary=SMALL_RECTANGULAR_BOUNDARY,
        ),
        room_plan=RoomPlan(room_description=CLASSROOM_ROOM_DESCRIPTION),
        what_to_place=search_test_asset("classroom_table"),
    )

    async def run_graph():
        # return await room_design_graph.run(PlacementAgent(), state=initial_state)
        return await placement_graph.run(PlacementAgent(), state=initial_state)
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

    # TODO: log each step, save info GIF, video, or markdown(?).

    result = asyncio.run(run_graph())


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

    blender.load_template(
        "test_assets/scenes/classroom.blend", clear_scene=True
    )

    async def run_graph():
        return await placement_graph.run(VisualFeedback(), state=initial_state)

    # TODO: log each step, save info GIF, video, or markdown(?).

    result: GraphRunResult[PlacementState] = asyncio.run(run_graph())

    room_vizs = []
    for step, state in enumerate(result.state.room_history):
        room_vizs.append(state.viz[-1])

    create_gif_from_images(room_vizs, "test_output/partial_room_completion.gif")

    blender.save_scene("tests/test_partial_room_completion.blend")


def test_room_design_workflow():
    RoomDesignAgent


if __name__ == "__main__":
    # test_single_object_placement()
    test_partial_room_completion()
    # test_room_design_workflow()
