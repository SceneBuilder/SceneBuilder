"""Room-level linting for SceneBuilder output."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable

from shapely.geometry import box

from scene_builder.decoder.blender.data_bridge import blender_size_provider
from scene_builder.definition.scene import Object, Room, Scene
from scene_builder.utils.geometry import convert_to_shapely

from scene_builder.lint.context import (
    LintContext,
    LintableObjectData,
    LintableRoomData,
    LintingOptions,
)
from scene_builder.lint.models import AABB, LintReport, LintSeverity
from scene_builder.lint.rules.base import LintRule


# Providers return world-space axis-aligned bounding boxes for objects.
SizeProvider = Callable[[Object], AABB | None]


def _prepare_context(room: Room, provider: SizeProvider) -> LintContext:
    if not room.boundary:
        raise ValueError(
            f"Room {room.id!r} must define a boundary with at least three vertices."
        )

    room_polygon = convert_to_shapely(room.boundary)
    lint_objects: list[LintableObjectData] = []
    for obj in room.objects or []:
        bbox = provider(obj)
        if bbox is None:
            continue

        if bbox.width <= 0.0 or bbox.depth <= 0.0:
            continue

        min_x, min_y, _ = bbox.min_corner
        max_x, max_y, _ = bbox.max_corner
        footprint = box(min_x, min_y, max_x, max_y)
        if footprint.is_empty:
            continue

        lint_objects.append(
            LintableObjectData(object=obj, bounds=bbox, footprint=footprint)
        )

    room_data = LintableRoomData(definition=room, footprint=room_polygon)

    return LintContext(room=room_data, objects=lint_objects)


def lint_room(
    room: Room,
    *,
    size_provider: SizeProvider = blender_size_provider,
    options: LintingOptions = LintingOptions(),
) -> LintReport:
    """Run lint checks for a single room."""

    report = LintReport(room_id=room.id)

    context = _prepare_context(room, size_provider)

    room_area = context.room.area
    if room_area > 0.0:
        report.stats["room_area"] = room_area

    enabled = options.enabled_rules

    active_rules: Iterable[LintRule]
    if enabled is None:
        active_rules = options.rules
    else:
        active_rules = [rule for rule in options.rules if rule.code in enabled]

    for rule in active_rules:
        for issue in rule.apply(context, options):
            report.add(issue)

    return report


def lint_scene(
    scene: Scene | Iterable[Room],
    *,
    size_provider: SizeProvider = blender_size_provider,
    options: LintingOptions = LintingOptions(),
) -> list[LintReport]:
    """Run lint checks for every room in a scene or room iterable."""

    if isinstance(scene, Scene):
        rooms = scene.rooms
    else:
        rooms = list(scene)

    return [
        lint_room(
            room,
            size_provider=size_provider,
            options=options,
        )
        for room in rooms
    ]


def format_lint_feedback(report: LintReport) -> str:
    """Convert a lint report into a concise, VLM-friendly summary."""

    if not report.issues:
        return "No automated lint issues detected."

    counts = Counter(issue.severity for issue in report.issues)
    count_fragments: list[str] = []
    for severity in LintSeverity:
        count = counts.get(severity, 0)
        if count:
            label = severity.value
            if count != 1:
                label += "s"
            count_fragments.append(f"{count} {label}")

    header = f"Automated lint detected {len(report.issues)} issue(s)"
    if count_fragments:
        header += " (" + ", ".join(count_fragments) + ")"
    header += "."

    lines = [header]
    for issue in report.issues:
        target = f" on object '{issue.object_id}'" if issue.object_id else ""
        line = f"- [{issue.severity.value.upper()}] {issue.code}{target}: {issue.message}"
        if issue.hint:
            line += f" Hint: {issue.hint}"
        lines.append(line)

    return "\n".join(lines)
