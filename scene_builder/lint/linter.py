"""Room-level linting and visualization utilities for SceneBuilder output."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable
from itertools import cycle
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
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
from scene_builder.lint.models import AABB, LintIssue, LintReport, LintSeverity
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
    options: LintingOptions | None = None,
) -> LintReport:
    """Run lint checks for a single room."""

    report = LintReport(room_id=room.id)

    if options is None:
        options = LintingOptions()

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
    options: LintingOptions | None = None,
) -> list[LintReport]:
    """Run lint checks for every room in a scene or room iterable."""

    if isinstance(scene, Scene):
        rooms = scene.rooms
    else:
        rooms = list(scene)

    if options is None:
        options = LintingOptions()

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


def save_lint_visualization(
    room: Room,
    report: LintReport,
    output_path: str | Path,
    *,
    size_provider: SizeProvider = blender_size_provider,
    figsize: tuple[float, float] = (6.0, 6.0),
    dpi: int = 300,
) -> None:
    """Render a top-down view of lint data and save it to ``output_path``.

    The visualization shows the room boundary along with each object's footprint.
    Objects without issues are filled in grey, while linted objects receive
    colored outlines keyed by the issue codes present in ``report``.

    Parameters
    ----------
    room:
        Room definition that the linter evaluated.
    report:
        Lint results associated with ``room``.
    output_path:
        File path for the saved figure. Any existing file will be overwritten.
    size_provider:
        Callable that returns world-space bounds for objects. Defaults to the
        Blender-backed provider used by the linter.
    figsize:
        Size of the generated Matplotlib figure in inches.
    dpi:
        Resolution of the saved image.
    """

    context = _prepare_context(room, size_provider)
    path = Path(output_path)
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)

    # Organize issues by object identifier for quick lookup.
    issues_by_object: dict[str, list[LintIssue]] = {}
    room_level_issues: list[LintIssue] = []
    for issue in report.issues:
        if issue.object_id is None:
            room_level_issues.append(issue)
            continue

        # Some issues (e.g., object_overlap) refer to multiple objects and encode
        # their identifiers as a comma-separated string ("id_a,id_b"). For
        # visualization, attribute the issue to every referenced object so each
        # footprint gets outlined.
        object_ids: list[str]
        if "," in issue.object_id or ";" in issue.object_id or " " in issue.object_id:
            parts = re.split(r"[;,\s]+", issue.object_id)
            object_ids = [p for p in (s.strip() for s in parts) if p]
        else:
            object_ids = [issue.object_id]

        for oid in object_ids:
            issues_by_object.setdefault(oid, []).append(issue)

    # Assign colors per issue code so each lint type is visually distinct.
    color_cycle = cycle(plt.get_cmap("tab10").colors)
    code_colors: dict[str, str] = {}

    # Use constrained layout to make room for labels/legend when needed.
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi, constrained_layout=False)

    room_polygon = context.room.footprint
    room_x, room_y = room_polygon.exterior.xy
    ax.fill(room_x, room_y, facecolor="#f0f0f0", edgecolor="#4a4a4a", linewidth=2.0, alpha=0.6)

    legend_handles: dict[str, MplPolygon] = {}

    for lint_object in context.objects:
        footprint = lint_object.footprint
        x, y = footprint.exterior.xy

        base_patch = MplPolygon(
            list(zip(x, y)),
            closed=True,
            facecolor="#b0bec5",
            edgecolor="#546e7a",
            alpha=0.35,
            linewidth=1.0,
        )
        ax.add_patch(base_patch)

        issues = issues_by_object.get(lint_object.id, [])
        if not issues:
            continue

        centroid = footprint.centroid
        ax.text(
            centroid.x,
            centroid.y,
            lint_object.id,
            ha="center",
            va="center",
            fontsize=8,
            color="#263238",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7, linewidth=0.5),
        )

        for issue in issues:
            color = code_colors.setdefault(issue.code, next(color_cycle))
            outline = MplPolygon(
                list(zip(x, y)),
                closed=True,
                fill=False,
                edgecolor=color,
                linewidth=2.0,
            )
            ax.add_patch(outline)

            if issue.code not in legend_handles:
                legend_handles[issue.code] = MplPolygon(
                    [(0, 0)],
                    closed=True,
                    fill=False,
                    edgecolor=color,
                    linewidth=2.0,
                    label=f"{issue.code} ({issue.severity.value})",
                )

    if issues_by_object:
        handles = list(legend_handles.values())
        labels = [h.get_label() for h in handles]
        # Place the legend just outside the top-right of the axes so it
        # never occludes the drawing area.
        ax.legend(
            handles,
            labels,
            loc="upper left",
            bbox_to_anchor=(1.02, 1.0),
            borderaxespad=0.0,
            fontsize=8,
            frameon=True,
        )

    # Add any room-level issues as an annotation in the top-left corner.
    if room_level_issues:
        note_lines = [
            f"{issue.severity.value.upper()} {issue.code}: {issue.message}" for issue in room_level_issues
        ]
        ax.text(
            0.02,
            0.98,
            "\n".join(note_lines),
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=8,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8, linewidth=0.5),
        )

    min_x, min_y, max_x, max_y = room_polygon.bounds
    span = max(max_x - min_x, max_y - min_y)
    padding = 0.05 * span if span > 0 else 1.0
    ax.set_xlim(min_x - padding, max_x + padding)
    ax.set_ylim(min_y - padding, max_y + padding)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(f"Lint visualization for room {room.id}")
    ax.axis("off")

    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
