from __future__ import annotations
import hashlib
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from rich.console import Console

from scene_builder.config import DEBUG, generation_config
from scene_builder.database.object import ObjectDatabase
from scene_builder.decoder.blender import blender
# from scene_builder.definition.scene import Object, Room, Vector3
from scene_builder.definition.scene import Object, ObjectBlueprint, Room, Scene, Shell, Vector3
from scene_builder.logging import logger
# from scene_builder.nodes.feedback import VisualFeedback
# from scene_builder.nodes.placement import PlacementNode, VisualFeedback
from scene_builder.nodes.placement import (
    PlacementNode,
    PlacementVisualFeedback,
    placement_graph,
)
# from scene_builder.nodes.routing import DesignLoopRouter
from scene_builder.utils.pai import transform_paths_to_binary
from scene_builder.utils.pydantic import save_yaml
from scene_builder.workflow.agents import (
    issue_resolution_agent,
    room_design_agent,
    sequencing_agent,
    shopping_agent,
)
# from scene_builder.workflow.graphs import placement_graph # hopefully no circular import... -> BRUH.
# from scene_builder.workflow.states import PlacementState, RoomDesignState
from scene_builder.workflow.states import (
    CritiqueAction,
    MainState,
    PlacementState,
    RoomDesignState,
)
from scene_builder.validation.models import LintActionTaken, LintIssueTicket
from scene_builder.workflow.toolsets import material_toolset, shopping_toolset
from scene_builder.validation.linter import format_lint_feedback, lint_room
from scene_builder.validation.models import LintIssue, LintReport

console = Console()
obj_db = ObjectDatabase()


class DesignLoopRouter(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> End[Scene]:
        console.print("[bold yellow]Entering room design loop...[/]")
        if ctx.state.current_room_index < len(ctx.state.scene_definition.rooms):
            console.print("[magenta]Decision:[/] Design next room.")
            subgraph_result = await room_design_graph.run(
                RoomDesignNode(ctx.state.initial_number)
            )
            ctx.state.scene_definition.rooms.append(subgraph_result)
        else:
            console.print("[magenta]Decision:[/] Finish.")
            return End(ctx.state.scene_definition)
        # TODO: use VisualFeedback to decide if there are rooms that still need designing.
        # TODO:


# TODO: move these to the other file with placement action and stuff like that(?)
class RDAInitialResponse(BaseModel):
    plan: str
    complete: bool = False


class MaterialAction(BaseModel):
    action: Literal["change", "keep"]

class MaterialSelection(BaseModel):
    material_id: str
    rationale: str


class ObjectAdjustment(BaseModel):
    id: str | None = None
    position: Vector3 | None = None
    rotation: Vector3 | None = None
    scale: Vector3 | None = None
    remove: bool = False


class IssueResolutionOutput(BaseModel):
    resolved: bool = False
    action_taken: str
    rationale: str
    object_id: str | None = None
    adjustment: ObjectAdjustment | None = None


ISSUE_TRACKER_KEY = "lint_issue_tracker"
MAX_AUTO_RESOLUTION_ATTEMPTS = 3


def _compute_issue_id(issue) -> str:
    base = f"{issue.code}|{issue.object_id or 'room'}|{issue.message}"
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def _issue_tracker(state: RoomDesignState) -> dict[str, object]:
    return state.extra_info.setdefault(
        ISSUE_TRACKER_KEY, {"tickets": {}, "actions": []}
    )


def _as_ticket(value: object) -> LintIssueTicket:
    return value if isinstance(value, LintIssueTicket) else LintIssueTicket(**value)


def _as_action(value: object) -> LintActionTaken:
    return value if isinstance(value, LintActionTaken) else LintActionTaken(**value)


def _sync_issue_tracker(
    state: RoomDesignState, lint_report: LintReport
) -> tuple[dict[str, object], dict[str, LintIssueTicket]]:
    tracker = _issue_tracker(state)
    tickets = {
        issue_id: _as_ticket(raw)
        for issue_id, raw in tracker.get("tickets", {}).items()
    }
    seen: set[str] = set()
    for issue in lint_report.issues:
        issue_id = _compute_issue_id(issue)
        seen.add(issue_id)
        ticket = tickets.get(issue_id)
        if ticket is None:
            ticket = LintIssueTicket(
                issue_id=issue_id,
                object_id=issue.object_id,
                code=issue.code,
                message=issue.message,
                hint=issue.hint,
            )
            tickets[issue_id] = ticket
        else:
            ticket.status = "open"
            ticket.object_id = issue.object_id
            ticket.code = issue.code
            ticket.message = issue.message
            ticket.hint = issue.hint
    for issue_id, ticket in tickets.items():
        if issue_id not in seen:
            ticket.status = "resolved"
    tracker["tickets"] = tickets
    tracker["actions"] = [
        _as_action(raw) for raw in tracker.get("actions", [])
    ]
    return tracker, tickets


def _append_action(
    tracker: dict[str, object],
    ticket: LintIssueTicket,
    summary: str,
    rationale: str,
) -> None:
    action = LintActionTaken(
        issue_id=ticket.issue_id,
        object_id=ticket.object_id,
        summary=summary,
        rationale=rationale,
    )
    tracker.setdefault("actions", []).append(action)
    ticket.actions.append(summary)


def _consume_issue_feedback(state: RoomDesignState) -> str:
    tracker = state.extra_info.get(ISSUE_TRACKER_KEY)
    if not tracker:
        return ""
    tracker["tickets"] = {
        issue_id: _as_ticket(raw)
        for issue_id, raw in tracker.get("tickets", {}).items()
    }
    tracker["actions"] = [
        _as_action(raw) for raw in tracker.get("actions", [])
    ]
    new_actions = [action for action in tracker["actions"] if not action.delivered]
    lines: list[str] = []
    if new_actions:
        lines.append("Actions taken since last turn:")
        for action in new_actions:
            lines.append(
                f"- [{action.issue_id}] {action.summary} (rationale: {action.rationale})"
            )
            action.delivered = True
    open_tickets = [
        ticket
        for ticket in tracker["tickets"].values()
        if ticket.status == "open"
    ]
    if open_tickets:
        lines.append("Outstanding lint issues:")
        for ticket in open_tickets:
            target = ticket.object_id or "room"
            lines.append(
                f"- ({ticket.code}) {target}: {ticket.message} (retries: {ticket.retries})"
            )
    return "\n".join(lines)


class RoomDesignNode(BaseNode[RoomDesignState]):
    async def run(
        self, ctx: GraphRunContext[RoomDesignState]
    # ) -> RoomDesignVisualFeedback | End[Room]:
    ) -> RoomDesignNode | End[Room]:
        console.print("[bold cyan]Executing Node:[/] RoomDesignNode")
        room = ctx.state.room
        # Build room and add translucent walls for clearer feedback renders
        blender.parse_room_definition(room, with_walls="translucent")
        output_dir = f"test_output/{ctx.state.extra_info['building_name']}/{ctx.state.room.id}"
        top_down_render = blender.visualize(scene=room.id, output_dir=output_dir, show_grid=True)
        isometric_render = blender.visualize(
            scene=room.id, output_dir=output_dir, view="isometric", show_grid=True
        )
        renders = transform_paths_to_binary([top_down_render, isometric_render])
        room_plan = transform_paths_to_binary(ctx.state.room_plan)
        rda_user_prompt = (
            f"This is design iteration {ctx.state.run_count}.\n",
            "Please look at the following information:\n",
            f"- Room State: \n\n```json\n{room}\n```\n",
            "- Renders (top-down and isometric):",
            *renders,
            f"- Concept: {room_plan}\n" if ctx.state.run_count == 0 else "",
            # "Please decide whether to continue designing the room, or if you are satisfied with the current state of the room.",
            "Please write a detailed design plan that may include details on areas or sections of the room, what kind of objects and furnitures you plan to place, and how you plan to place them." if ctx.state.run_count == 0 else\
            # "Please write a detailed design plan." if ctx.state.run_count == 0 else\  # ALT
            "Do you want to continue designing the room, or are you complete with the design?",
            "Please return `complete=True` if you are complete with the design." if ctx.state.run_count > 0 else ""
        )
        rda_initial_response = await room_design_agent.run(
            rda_user_prompt,
            # deps=ctx.state,  # I don't think this means anything anymore (it's just for tool calling)
            # output_type=RDAInitialResponse  # WRONG
            output_type=str if ctx.state.run_count == 0 else RDAInitialResponse
        )
        # TODO: make sure the plan is added to message_history even if the output type is not plain `str`.
        # tried to look into variables but they are complex. i guess a possible approach is doing a "blindfolding" experiment!
        # NOTE!: Tool call results are NOT added to message_history — it failed the blindfolding repeat experiment.
        
        # NOTE: design termination is not handled. 
        #       one idea is to conditionally specify output type based on run count. 
        # NOTE: lowkey, design plan is useful even beyond the first step - i want to find a way for it to keep generating (and adding into context) the refined design plans even in later iterations. 
        #       or maybe we just separate the planning and continuation/completion into two calls. because why not. 
        # NOTE: oh shoot ig it was not generating the design plan outside of the first step anyway. i thought it was. whoops.

        if DEBUG:
        #     print(f"[RoomDesignNode]: {response.output.decision}")
        #     print(f"[RoomDesignNode]: {response.output.reasoning}")
            print(f"[RoomDesignNode]: {rda_initial_response.output}")
            
            # TEMP: context blindfolding experiment
            # experiment_response = await room_design_agent.run(
            #     "Could you recite the room plan verbatim?",
            #     message_history=rda_initial_response.all_messages(),
            #     output_type=str,
            # )
            # print(f"[RoomDesignNode]: {experiment_response.output}")

        # if response.output.decision == "finalize":
        #     return End(ctx.state.room)

        # Inspect current floor shell (if any) for context
        floor_shell = None
        try:
            floor_shell = next((s for s in room.shells if s.type == "floor"), None)
        except Exception:
            floor_shell = None

        material_change_user_prompt = (
            "Do you want to change the floor material (texture), or keep the existing one?",
            f"Current floor state: {floor_shell}",
        )
        material_change_response = await room_design_agent.run(material_change_user_prompt, output_type=MaterialAction)
        # if material_change_response.output:  # is True
        if material_change_response.output.action == "change":  # is True
            material_user_prompt = (
                "Could you search for a material (texture) to be applied to the floor?",
                "The `query` tool provides search results from a material database.",
                "The `get_metadata` tool provides various metadata about the material.",
                "Please return the `material_id` of the material of your choice."
            )
            material_response = await room_design_agent.run(material_user_prompt, toolsets=[material_toolset], output_type=MaterialSelection)
            logger.debug(f"Selected floor material for room {room.id}: {material_response.output.material_id}")
            # logger.debug(f"Selected floor material for room {room.id}: {material_response.output}")
            # Update existing floor shell or append a new one
            existing_floor = next((s for s in ctx.state.room.shells if s.type == "floor"), None)
            if existing_floor is not None:
                existing_floor.material_id = material_response.output.material_id
            else:
                ctx.state.room.shells.append(
                    Shell(type="floor", material_id=material_response.output.material_id)
                )

        # Ask about wall material selection similar to floor
        wall_shell = None
        try:
            wall_shell = next((s for s in room.shells if s.type == "wall"), None)
        except Exception:
            wall_shell = None

        wall_change_user_prompt = (
            "Do you want to change the wall material (texture), or keep the existing one?",
            f"Current wall state: {wall_shell}",
        )
        wall_change_response = await room_design_agent.run(
            wall_change_user_prompt, output_type=MaterialAction
        )
        if wall_change_response.output.action == "change":
            wall_material_user_prompt = (
                "Could you search for a material (texture) to be applied to the wall?",
                "The `query` tool provides search results from a material database.",
                "The `get_metadata` tool provides various metadata about the material.",
                "Please return the `material_id` of the material of your choice."
            )
            wall_material_response = await room_design_agent.run(
                wall_material_user_prompt,
                toolsets=[material_toolset],
                output_type=MaterialSelection,
            )
            logger.debug(
                f"Selected wall material for room {room.id}: {wall_material_response.output.material_id}"
            )
            existing_wall = next((s for s in ctx.state.room.shells if s.type == "wall"), None)
            if existing_wall is not None:
                existing_wall.material_id = wall_material_response.output.material_id
            else:
                ctx.state.room.shells.append(
                    Shell(type="wall", material_id=wall_material_response.output.material_id)
                )

        shopping_user_prompt = (
            "Please explore the object database to choose the objects that you would like to use for designing the room.",
            "The `search` tool provides information about potential candidates including ids, thumbnails, and dimensions.",
            "You can then use the `pack` tool to transform uids into a list of `ObjectBlueprint` instances.",
            "Please use the top_k parameter generously to explore different options and choose your favorite ones.",
            "(NOTE: If you feel like everything is added already, there is no need to add more objects every time!)",
            f"Existing items in the shopping cart: {ctx.state.shopping_cart}",
        )
        shopping_response = await room_design_agent.run(
            shopping_user_prompt,
            # deps=ctx.state,
            message_history=rda_initial_response.all_messages(),
            output_type=list[ObjectBlueprint],
            toolsets=[shopping_toolset],
        )
        items_to_add = shopping_response.output
        console.print(
            f"[bold cyan]Added Objects:[/] {[obj.name for obj in items_to_add]}"
        )
        ctx.state.shopping_cart.extend(items_to_add)
        # NOTE: I think it would be nice if the shopping cart thumbnails are visible even after the initial markdown report search.
        #       let's try to cook something up with either paths or binarycontent, so that the VLM can still see what they look like later.

        # NOTE: this simple implementation lacks the possibility of shop-once, place-multiple-times workflow.
        #       the above two prompts (and LLM calls) need to repeat. i think actually, pydantic_graph *is* needed to properly implement
        #       conditional routing of this sort. 
        feedback = None
        placement_run_count = 0
        while True:
            placement_user_prompt = (
                "Please design the room by placing objects into the room, by writing the `object` data with position, rotation, and scale.",
                "You don't need to place all objects at once (although you can!).",
                "Once you are done, you will be given updated renders so that you can review and refine the placements.",
                "(NOTE: A right-handed z-up coordinate system is used. All units are in meters. Rotations are in degrees!)",
                "(NOTE: Please retain the original `uid` property of the ObjectBlueprint — it's used later for retrieving the 3D model file.",
                "(NOTE: Please assign a unique id for each object. If you want to modify the placement of an existing object, you can do so by overwriting the pos/rot/scl, while re-using the same id.)",
                # f"The shopping cart: {ctx.state.shopping_cart}"  # NOTE: not sure if needed
            ) if placement_run_count == 0 else (
                f"Placement Feedback (reason for rejection): {feedback}"
            )
            placement_response = await room_design_agent.run(
                placement_user_prompt,
                message_history=shopping_response.all_messages(),
                output_type=list[Object],
            )
            ctx.state.room.objects = placement_response.output

            # post-placement render
            # Rebuild room after placement with translucent walls for feedback
            blender.parse_room_definition(room, with_walls="translucent")
            lint_report = lint_room(ctx.state.room)
            ctx.state.last_lint_report = lint_report
            tracker, tickets_store = _sync_issue_tracker(ctx.state, lint_report)
            issue_lookup = {
                _compute_issue_id(issue): issue for issue in lint_report.issues
            }
            while await self._resolve_open_tickets(
                ctx,
                tracker,
                tickets_store,
                issue_lookup,
            ):
                lint_report = lint_room(ctx.state.room)
                ctx.state.last_lint_report = lint_report
                tracker, tickets_store = _sync_issue_tracker(ctx.state, lint_report)
                issue_lookup = {
                    _compute_issue_id(issue): issue for issue in lint_report.issues
                }
            lint_summary = format_lint_feedback(lint_report)
            if DEBUG:
                print(f"[Lint] {lint_summary}")
            top_down_render = blender.visualize(scene=room.id, output_dir=output_dir, show_grid=True)
            isometric_render = blender.visualize(
                scene=room.id, output_dir=output_dir, view="isometric", show_grid=True
            )
            renders = transform_paths_to_binary([top_down_render, isometric_render])
            lint_section = f"Automated lint analysis for the current placement:\n{lint_summary}"

            critique_user_prompt = (
                "Updated renders:",
                *renders,
                lint_section,
                "Do you approve of the previous placement result?",
                "If so, please provide a rationale, and if not, please provide feedback for the PlacementAgent,",
                "so it can address the issues in the upcoming design step.",
            )
            critique_response = await room_design_agent.run(
                critique_user_prompt,
                message_history=placement_response.all_messages(),
                output_type=CritiqueAction,
            )
            critique = critique_response.output
            if DEBUG:
                print(f"{critique.result=}")
                print(f"{critique.explanation=}")
            if critique.result == "rejected":
                feedback = self._compose_feedback(ctx, critique.explanation, lint_summary)
            elif critique.result == "approved":
                break
            if generation_config.terminate_early:
                logger.debug(f"Breaking placement loop for {room.id} to terminate early")
                break
            placement_run_count += 1
        

        ### Inter-Agent Collaboration Logic v1 (old) ###
        # # rda2sha_prompt = "Please tell the `ShoppingAgent` what you would like to achieve in the next design step."
        # # rda2sha_prompt = "Please communicate with the `ShoppingAgent` what you would like to achieve in the next design step."
        # rda2sha_prompt = (
        #     "Please request the `ShoppingAgent` if you would like it to find specific objects from the object database.",
        #     "Your next response will be passed along to the `ShoppingAgent`.",
        # )
        # rda2sha_response = await room_design_agent.run(
        #     rda2sha_prompt, message_history=response.all_messages(), output_type=str
        # )
        # shopping_user_prompt = (
        #     f"Message from `RoomDesignAgent`: {rda2sha_response.output}"
        #     f"Room id: '{room.id}'.",
        #     f"Room category: '{room.category}'.",
        #     f"Room plan: {ctx.state.room_plan}.",
        #     f"Existing items in the shopping cart: {ctx.state.shopping_cart}",
        # )
        # # NOTE: It may be beneficial to add a state variable to control whether shopping_agent can / should be invoked,
        # #       to allow for "waterfall"-style selection → placement sequence.
        # # NOTE: For example, it can be beneficial to think of "design" and "build" separately,
        # #       where design consists of shopping and planning, and building consists of going back-and-forth
        # #       between the placement node/agent, doing quality checks via visual feedback (potentially giving
        # #       the PlacementNode some advice, although it has feedback of its own), or re-initiating motion
        # #       of certain already-place items, and then finalizing the room to end the process.
        # #       What this ultimately means is that there are probably certain parts that are to be invoked once,
        # #       and certain parts that are meant to run repetitively. It's useful to model the human design process.

        # shopping_agent_response = await shopping_agent.run(shopping_user_prompt)
        # shopping_cart = shopping_agent_response.output
        # console.print(
        #     f"[bold cyan]Added Objects:[/] {[obj.name for obj in shopping_cart]}"
        # )
        # ctx.state.shopping_cart.extend(shopping_cart)
        # # NOTE: may need to diff the shopping cart content or something, if shopping
        # #       is anything other than shopping a singular object that is immediately needed.
        # # NOTE: not sure if VLM is going to repeat existing stuff in the ShoppingCart
        # #       or skip them. (probably need to explicitly prompt to "pin" this behavior.)

        # # TEMP: choose the first item in the shopping cart
        # what_to_place = ctx.state.shopping_cart[0]

        # rda2sea_prompt = (
        #     # "Please communicate with the `SequencingAgent` what you would like to achieve in the next design step.",
        #     "Please communicate with the `SequencingAgent` what you would like to achieve (e.g., which objects to place first) in the next design step.",
        #     # "Your next response will be passed along to the `SequencingAgent`.",
        #     "Your next response will be passed along to the `SequencingAgent`. (Just respond in natural language this time!)",
        # )
        # rda2sea_response = await room_design_agent.run(
        #     rda2sea_prompt,
        #     message_history=rda2sha_response.all_messages(),
        #     output_type=str,
        # )
        # if DEBUG:
        #     print(f"[RoomDesignAgent → SequencingAgent] {rda2sea_response.output}")
        # sequencing_user_prompt = (
        #     f"Message from `RoomDesignAgent`: {rda2sea_response.output}",
        #     f"Shopping Cart: {str(ctx.state.shopping_cart)}",
        # )  # stuff to include:
        # # shopping cart content: names, thumbnails, metadata
        # # scene vizs that show room evolution history (?),
        # # ^ maybe some text that describe what was changed (like a commmit msg) is helpful?
        # # probably the room plan,
        # # probably the visual feedback content (text) from prev iter
        # sequencing_response = await sequencing_agent.run(sequencing_user_prompt)
        # sequence = sequencing_response.output
        # what_to_place = sequence[0]
        # # NOTE: if it gives a multi-length sequence, maybe let's consume it all before consulting it again
        # #       (as long as it's not unreasonable - like it specifies the whole damn shopping cart. we can do sanity checks.)
        # console.print(f"[bold cyan]Placing Next:[/] {what_to_place}")
        # # Remove the object (blueprint) from shopping cart to prevent excessive repeats
        # # NOTE: since the shopping cart does not have a quantity property, we assume quantity=1 for now
        # idx = next(
        #     (
        #         i
        #         for i, obj in enumerate(ctx.state.shopping_cart)
        #         if obj == what_to_place
        #     ),
        #     None,
        # )
        # if idx is not None:
        #     ctx.state.shopping_cart.pop(idx)

        # NOTE: It would be interesting if the room design agent can "think" of
        #       certain opinions and feed it to PlacementNode as text guidance.
        #       Like describing what it wants in natural language, based on contexts.
        #         (Then, why doesn't it do everything itself, since it knows the context already? Hmm...)

        # NOTE: Or lowkey PlacementAgent can take care of what to do (altho language comm prolly is useful & better)
        #       and we just do termination management by measuring the number of objects it add and terminating @ 1? Idk.

        # rda2pla_prompt = (
        #     "Please request the `PlacementAgent` what you would like to achieve in the next design step.",
        #     # "Your next response will be passed along to the `PlacementAgent`.",
        #     "Your next response will be passed along to the `PlacementAgent`. (Just respond in natural language this time!)",
        # )
        # rda2pla_response = await room_design_agent.run(
        #     rda2pla_prompt,
        #     message_history=rda2sea_response.all_messages(),
        #     output_type=str,
        # )
        # if DEBUG:
        #     print(f"[RoomDesignAgent → PlacementAgent] {rda2pla_response.output}")
        # placement_state = PlacementState(
        #     room=room,
        #     room_plan=ctx.state.room_plan,
        #     what_to_place=what_to_place,
        #     user_prompt=f"Message from `RoomDesignAgent`: {rda2pla_response}",
        # )

        # # PROBLEM(?): placement_graph runs for extended periods and places multiple objects.

    async def _resolve_open_tickets(
        self,
        ctx: GraphRunContext[RoomDesignState],
        tracker: dict[str, object],
        tickets_store: dict[str, LintIssueTicket],
        issue_lookup: dict[str, LintIssue],
    ) -> bool:
        modified = False
        for issue_id, ticket in tickets_store.items():
            if ticket.status != "open":
                continue
            if ticket.retries >= MAX_AUTO_RESOLUTION_ATTEMPTS:
                continue
            issue = issue_lookup.get(issue_id)
            if issue is None:
                continue
            resolved = await self._resolve_ticket(ctx, tracker, ticket, issue)
            if resolved:
                modified = True
        return modified

    async def _resolve_ticket(
        self,
        ctx: GraphRunContext[RoomDesignState],
        tracker: dict[str, object],
        ticket: LintIssueTicket,
        issue: LintIssue,
    ) -> bool:
        ticket.retries += 1
        object_state_json = None
        if ticket.object_id:
            target = next(
                obj for obj in ctx.state.room.objects if obj.id == ticket.object_id
            )
            object_state_json = target.model_dump_json(indent=2)
        prompt_parts = [
            "Resolve the following lint issue in the 3D room design.",
            f"Room id: {ctx.state.room.id}",
            f"Issue code: {issue.code}",
            f"Issue message: {issue.message}",
        ]
        if issue.hint:
            prompt_parts.append(f"Hint: {issue.hint}")
        prompt_parts.append(f"Attempts so far: {ticket.retries - 1}")
        if object_state_json:
            prompt_parts.append("Current object state:")
            prompt_parts.append(f"```json\n{object_state_json}\n```")
        else:
            prompt_parts.append("The issue applies to the overall room context.")
        if ticket.actions:
            prompt_parts.append("Recent actions:")
            prompt_parts.extend(f"- {action}" for action in ticket.actions[-3:])
        prompt_parts.extend(
            [
                "Respond with JSON that matches the IssueResolutionOutput schema:",
                '{"resolved": bool, "action_taken": str, "rationale": str,',
                ' "object_id": str | null, "adjustment": {',
                '   "id": str | null, "position": Vector3 | null,',
                '   "rotation": Vector3 | null, "scale": Vector3 | null,',
                '   "remove": bool',
                " }}",
            ]
        )
        response = await issue_resolution_agent.run(
            tuple(prompt_parts),
            output_type=IssueResolutionOutput,
        )
        result = response.output
        if result.object_id:
            ticket.object_id = result.object_id
        adjustment = result.adjustment
        if adjustment is not None:
            target_id = adjustment.id or ticket.object_id
            if adjustment.remove:
                ctx.state.room.objects = [
                    obj for obj in ctx.state.room.objects if obj.id != target_id
                ]
            else:
                obj = next(
                    item for item in ctx.state.room.objects if item.id == target_id
                )
                if adjustment.position is not None:
                    obj.position = adjustment.position
                if adjustment.rotation is not None:
                    obj.rotation = adjustment.rotation
                if adjustment.scale is not None:
                    obj.scale = adjustment.scale
        if result.resolved:
            ticket.status = "resolved"
        _append_action(tracker, ticket, result.action_taken, result.rationale)
        return bool(adjustment) or result.resolved

    def _compose_feedback(
        self,
        ctx: GraphRunContext[RoomDesignState],
        critique_text: str,
        lint_summary: str,
    ) -> str:
        sections = []
        if critique_text:
            sections.append(critique_text)
        if lint_summary:
            sections.append(f"Automated lint analysis:\n{lint_summary}")
        issue_feedback = _consume_issue_feedback(ctx.state)
        if issue_feedback:
            sections.append(issue_feedback)
        return "\n\n".join(section for section in sections if section)

        # placement_subgraph_response = await placement_graph.run(
        #     PlacementNode(), state=placement_state
        # )
        # updated_room: Room = placement_subgraph_response.output
        # ctx.state.room = updated_room
        # # ctx.state.room_history += new_placement_state.room_history

        # TODO: use VisualFeedback and ShoppingCart to decide if room needs more objects or end
        # NOTE: the logic should be: the room is fed to a visual feedback agent, along with information
        #       such as the remaining items in the shopping cart (that is "explorable" in terms of detail,
        #       meaning it can be as simple as how many objects are left and their names, or their thumbnails & sizes),

        # TODO: decide whether to finalize the scene, or to continue designing.
        # TODO: if deciding to continue, choose what to place next.
        ### END ###

        ### LOG ###
        # Save room definition
        if DEBUG:
            room_yaml_path = f"{output_dir}/room_step_{ctx.state.run_count}.yaml"
            save_yaml(ctx.state.room, room_yaml_path)
            # logger.debug(f"Saved room definition to {room_yaml_path}")

        ### Return ###
        # TODO: if DEBUG, make it dump (latest) state & .blend to a file at every turn. or maybe all turns. for web viz.
        ctx.state.run_count += 1  # (TEMP?)
        ctx.state.message_history = critique_response.all_messages()  # TODO: confirm this is correct
        # if ctx.state.run_count >= 2:  # TEMP: test that it ends successfully
        #     return End(ctx.state.room)
        # if ctx.state.run_count > 5 and generation_config.terminate_early:  # DEBUG
        if ctx.state.run_count > 2 and generation_config.terminate_early:  # DEBUG
            return End(ctx.state.room)
        elif ctx.state.run_count > 1 and rda_initial_response.output.complete:
            return End(ctx.state.room)
        else:
            return RoomDesignNode()  # maybe this is the issue? self-returning function?
    
    
        # NOTE: don't return `UpdateScene` directly; return a room to caller (DesignLoopRouter)
        #       and let it take care of coalescing it with the entire Scene.

        # IDEA: It would be cool to visualize the conversations and back-and-forths between the different "agents"
        #       in the time-lapse scene building video, along with locations (just randomized movements around the room/
        #       object of interest, probably). Think: cute minimal robot blob characters with chat bubbles, sounds, and motions.

        # IDEA: Using a conditioned image diffusion model to "imagine" different layouts, based on the current room image
        #       and thumbnails of the assets. So that diverse layouts can be efficiently "explored", without having to repetitively
        #       call VLMs and building in Blender. This is a cool idea with questionable practicality, but just for the sake of
        #       modeling the human design process with VLMs/AI agents, it is *very* interesting.
        #       Honestly, can be a cool part of the paper.

        # return UpdateScene()


# class RoomDesignVisualFeedback(BaseNode[RoomDesignState]):
#     # NOTE: see PlacementVisualFeedback in `placement.py` for notes and design decisions.
#     # NOTE: I think this node must take care of room design termination management (e.g., invoking it).
#     async def run(self, ctx: GraphRunContext[RoomDesignState]) -> RoomDesignNode:
#         blender.parse_room_definition(ctx.state.room)
#         top_down_render = blender.create_scene_visualization(output_dir="test_output")
#         isometric_render = blender.create_scene_visualization(
#             output_dir="test_output", view="isometric"
#         )
#         ctx.state.viz.append(top_down_render)
#         ctx.state.viz.append(isometric_render)
#         return RoomDesignNode()


room_design_graph = Graph(
    nodes=[
        DesignLoopRouter,  # TEMP
        RoomDesignNode,
        # RoomDesignVisualFeedback,
    ],
    state_type=Room,
)

# NOTES
"""
There are two models of the room design process that can be thought of, as of now:

1) The RoomDesignNode selects a single object to add into the room (using ShoppingAgent), and calls
   PlacementNode to place the object. This simple loop is repeated, along with VisualFeedback and
   RoomPlan as a reference, so that RoomDesignNode can find a stopping point, when it finds it satisfactory.

2) The RoomDesignNode selects what objects to add into the room (using ShoppingAgent), and then calls
   RoomBuildNode, which interactively commands the PlacementNode along with VisualFeedback and RoomPlan,
   and is capable of invoking edits of existing object placements, and generating multiple room layout candidates,
   to be fed into a quantitative scorer for score-based winner-takes-all pooling. 
   
   The RoomBuildNode can ask to "go back to the drawing board", giving back control to the design node to invite
   additional objects into the ShoppingCart, or do so when it empties the given ShoppingCart, or finds the room
   sufficiently occupied where placement of more objects is not necessary. 
   
   The RoomDesignNode can perform additional tasks, such as generating GenAI-based candidate layout generation
   in the form of images, to effectively serve as the inspiration ("inspo") of downstream designers/placers. 
   
   This suggests to allow a more organic flow of placement, editing, designing, and imagining, and
   may yield a higher quality scene overall. 

"""
