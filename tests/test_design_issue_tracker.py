import os
import sys
import types
from pathlib import Path

from pydantic import BaseModel

sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

bpy_module = types.ModuleType("bpy")


class _BpyTypes:
    def __init__(self) -> None:
        self.Object = type("Object", (), {})
        self.NodesModifier = type("NodesModifier", (), {})

    def __getattr__(self, name: str):
        dummy = type(name, (), {})
        setattr(self, name, dummy)
        return dummy


bpy_module.types = _BpyTypes()

graphics_module = types.ModuleType("graphics_db_server")
logging_module = types.ModuleType("graphics_db_server.logging")
logging_module.logger = None
schemas_module = types.ModuleType("graphics_db_server.schemas")
asset_module = types.ModuleType("graphics_db_server.schemas.asset")


class _Asset(BaseModel):  # minimal stub for dependency injection
    model_config = {
        "arbitrary_types_allowed": True,
    }


asset_module.Asset = _Asset
schemas_module.asset = asset_module
graphics_module.schemas = schemas_module

sys.modules.setdefault("graphics_db_server", graphics_module)
sys.modules.setdefault("graphics_db_server.logging", logging_module)
sys.modules.setdefault("graphics_db_server.schemas", schemas_module)
sys.modules.setdefault("graphics_db_server.schemas.asset", asset_module)
sys.modules.setdefault("bpy", bpy_module)
sys.modules.setdefault("bmesh", types.ModuleType("bmesh"))
sys.modules.setdefault("addon_utils", types.ModuleType("addon_utils"))
mathutils_module = types.ModuleType("mathutils")


class _Vector:  # simple stub used by blender bindings
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs


mathutils_module.Vector = _Vector
geometry_module = types.ModuleType("mathutils.geometry")


def _tessellate_polygon(*args, **kwargs):
    return []


geometry_module.tessellate_polygon = _tessellate_polygon
mathutils_module.geometry = geometry_module
sys.modules.setdefault("mathutils", mathutils_module)
sys.modules.setdefault("mathutils.geometry", geometry_module)

from scene_builder.definition.plan import RoomPlan
from scene_builder.definition.scene import Room
from scene_builder.nodes.design import (
    _append_action,
    _compute_issue_id,
    _consume_issue_feedback,
    _sync_issue_tracker,
)
from scene_builder.validation.models import LintIssue, LintReport
from scene_builder.workflow.states import RoomDesignState


def _make_state() -> RoomDesignState:
    room = Room(id="room-1", objects=[], shells=[], boundary=[], tags=[])
    return RoomDesignState(room=room, room_plan=RoomPlan())


def test_sync_issue_tracker_creates_ticket_and_marks_resolved():
    state = _make_state()
    issue = LintIssue(code="OVERLAP", message="Objects overlap", object_id="chair")
    report = LintReport(room_id=state.room.id, issues=[issue])

    tracker, tickets = _sync_issue_tracker(state, report)
    issue_id = _compute_issue_id(issue)
    assert issue_id in tickets
    ticket = tickets[issue_id]
    assert ticket.status == "open"
    assert ticket.object_id == "chair"

    _append_action(tracker, ticket, "Moved chair", "Prevented overlap")
    feedback = _consume_issue_feedback(state)
    assert "Moved chair" in feedback
    assert "Outstanding lint issues" in feedback

    # Subsequent consumption should not repeat delivered actions
    follow_up_feedback = _consume_issue_feedback(state)
    assert "Moved chair" not in follow_up_feedback

    # When the report no longer contains the issue, it should be marked resolved
    resolved_report = LintReport(room_id=state.room.id, issues=[])
    tracker, tickets = _sync_issue_tracker(state, resolved_report)
    assert tickets[issue_id].status == "resolved"
