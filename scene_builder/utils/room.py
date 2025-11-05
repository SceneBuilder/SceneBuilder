"""Room utility functions for scene building."""

from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
from shapely.geometry.base import BaseGeometry

from scene_builder.definition.scene import Room, Structure, Vector2, Vector3
from scene_builder.logging import logger
from scene_builder.utils.geometry import boundary_to_geometry, polygon_centroid


def recenter_room(room: Room) -> Room:
    """Recenter room to origin, storing original offset in extra_info.

    Args:
        room: The room to recenter.

    Returns:
        A new room with boundary and objects recentered to the polygon centroid.
        The original origin is stored in extra_info for later recovery.
    """
    if room.boundary is None or len(room.boundary) < 3:
        return room

    center = polygon_centroid(room.boundary)
    recentered = room.model_copy(deep=True)
    recentered.boundary = [
        Vector2(x=v.x - center.x, y=v.y - center.y) for v in room.boundary
    ]
    recentered.objects = [
        obj.model_copy(
            update={
                "position": Vector3(
                    x=obj.position.x - center.x,
                    y=obj.position.y - center.y,
                    z=obj.position.z,
                )
            }
        )
        for obj in room.objects
    ]
    if room.structure is None:
        recentered.structure = None
    else:
        recentered.structure = [
            s.model_copy(
                update={
                    "boundary": [
                        Vector2(x=p.x - center.x, y=p.y - center.y) for p in (s.boundary or [])
                    ]
                    if s.boundary
                    else None
                }
            )
            for s in room.structure
        ]
    recentered.extra_info = {"egocentric_proxy": True, "original_origin": center}
    return recentered


def restore_origin(room: Room) -> Room:
    """Restore room to original coordinate system if it was recentered.

    Args:
        room: The room to restore.

    Returns:
        A new room with original coordinate system restored if it was previously
        recentered. Otherwise, returns the room as-is.
    """
    if not (isinstance(room.extra_info, dict) and room.extra_info.get("egocentric_proxy")):
        return room

    origin = room.extra_info["original_origin"]
    restored = room.model_copy(deep=True)
    restored.boundary = (
        [Vector2(x=v.x + origin.x, y=v.y + origin.y) for v in room.boundary]
        if room.boundary
        else None
    )
    restored.objects = [
        obj.model_copy(
            update={
                "position": Vector3(
                    x=obj.position.x + origin.x,
                    y=obj.position.y + origin.y,
                    z=obj.position.z,
                )
            }
        )
        for obj in room.objects
    ]
    if room.structure is None:
        restored.structure = None
    else:
        restored.structure = [
            s.model_copy(
                update={
                    "boundary": [
                        Vector2(x=p.x + origin.x, y=p.y + origin.y) for p in (s.boundary or [])
                    ]
                    if s.boundary
                    else None
                }
            )
            for s in room.structure
        ]
    restored.extra_info = None
    return restored


def assign_structures_to_rooms(
    rooms: Iterable[Room],
    structures: Iterable[Structure],
    distance_threshold: float = 0.75,
) -> list[tuple[str, str]]:
    """Attach structures to any rooms within the distance threshold."""
    attachments: list[tuple[str, str]] = []

    room_geometries: list[tuple[Room, BaseGeometry]] = []
    for room in rooms:
        geom = boundary_to_geometry(room.boundary)
        if geom is None:
            logger.warning("Skipping room %s: missing or invalid boundary", room.id)
            continue
        room_geometries.append((room, geom))

    for structure in structures:
        structure_geom = boundary_to_geometry(structure.boundary)
        if structure_geom is None:
            logger.warning(
                "Skipping structure %s (%s): missing or invalid boundary",
                structure.id,
                structure.type,
            )
            continue

        attached = False
        for room, room_geom in room_geometries:
            distance = room_geom.distance(structure_geom)
            if distance <= distance_threshold:
                if room.structure is None:
                    room.structure = []
                if not any(existing.id == structure.id for existing in room.structure):
                    room.structure.append(structure)
                attachments.append((structure.id, room.id))
                attached = True

        if not attached:
            min_distance = min(
                (room_geom.distance(structure_geom) for _, room_geom in room_geometries),
                default=float("inf"),
            )
            logger.debug(
                "No nearby room found for structure %s (%s); min distance=%.3f",
                structure.id,
                structure.type,
                min_distance,
            )

    return attachments


def render_structure_links(
    rooms: Iterable[Room] | Iterable[dict],
    structures: Iterable[Structure] | Iterable[dict],
    attachments: Iterable[tuple[str, str]],
    output_path: str | Path,
    *,
    figsize: tuple[float, float] = (10.0, 10.0),
    dpi: int = 150,
) -> Path:
    """Render a debug visualization of room boundaries and structure links.

    Accepts either Pydantic models (Room/Structure) or dicts with equivalent
    fields (e.g., produced by pydantic_to_dict). Dict inputs are cast to
    Pydantic models for consistent handling.
    """
    # Normalize inputs and one-line cast of dicts → Pydantic models (HACK?)
    rooms = [r if isinstance(r, Room) else Room.model_validate(r) for r in list(rooms)]
    structures = [s if isinstance(s, Structure) else Structure.model_validate(s) for s in list(structures)]
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    room_lookup = {room.id: room for room in rooms}
    structure_lookup = {structure.id: structure for structure in structures}

    room_geoms: dict[str, BaseGeometry] = {}
    for room in rooms:
        geom = boundary_to_geometry(room.boundary)
        if geom is None:
            logger.warning("Cannot visualize room %s: missing or invalid boundary", room.id)
            continue
        room_geoms[room.id] = geom

    structure_geoms: dict[str, BaseGeometry] = {}
    for structure in structures:
        geom = boundary_to_geometry(structure.boundary)
        if geom is None:
            logger.warning(
                "Cannot visualize structure %s (%s): missing or invalid boundary",
                structure.id,
                structure.type,
            )
            continue
        structure_geoms[structure.id] = geom

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

    # Draw rooms
    room_colors: dict[str, str] = {}
    base_colors = plt.rcParams["axes.prop_cycle"].by_key().get("color", ["tab:blue"])
    for idx, (room_id, geom) in enumerate(room_geoms.items()):
        room_color = base_colors[idx % len(base_colors)]
        room_colors[room_id] = room_color

        geom_type = geom.geom_type
        if geom_type == "Polygon":
            x, y = geom.exterior.xy
            ax.fill(
                x,
                y,
                facecolor=room_color,
                alpha=0.25,
                edgecolor=room_color,
                linewidth=2.0,
            )
        elif geom_type == "LineString":
            x, y = geom.xy
            ax.plot(x, y, color=room_color, alpha=0.7, linewidth=2.0)
        elif geom_type == "Point":
            ax.scatter([geom.x], [geom.y], color=room_color, alpha=0.7, s=50)
        else:
            logger.warning("Unsupported room geometry type for visualization: %s", geom_type)

        centroid = geom.centroid
        ax.text(
            centroid.x,
            centroid.y,
            room_id,
            color=room_color,
            fontsize=10,
            ha="center",
            va="center",
            bbox={"facecolor": "white", "alpha": 0.6, "edgecolor": "none"},
        )

    # Draw structures and links
    structure_colors = {"door": "tab:brown", "window": "tab:blue"}

    for structure_id, geom in structure_geoms.items():
        structure = structure_lookup.get(structure_id)
        structure_type = structure.type if structure else "structure"
        structure_color = structure_colors.get(structure_type, "tab:orange")

        geom_type = geom.geom_type
        if geom_type == "Polygon":
            x, y = geom.exterior.xy
            ax.fill(
                x,
                y,
                facecolor=structure_color,
                alpha=0.5,
                edgecolor=structure_color,
                linewidth=1.5,
            )
        elif geom_type == "LineString":
            x, y = geom.xy
            ax.plot(x, y, color=structure_color, alpha=0.8, linewidth=2.0)
        elif geom_type == "Point":
            ax.scatter([geom.x], [geom.y], color=structure_color, alpha=0.8, s=60)
        else:
            logger.warning(
                "Unsupported structure geometry type for visualization: %s",
                geom_type,
            )

        centroid = geom.centroid
        ax.scatter([centroid.x], [centroid.y], color=structure_color, s=30, zorder=5)
        ax.text(
            centroid.x,
            centroid.y,
            structure_id,
            color=structure_color,
            fontsize=8,
            ha="left",
            va="bottom",
            bbox={"facecolor": "white", "alpha": 0.6, "edgecolor": "none"},
        )

    # Draw association lines
    for structure_id, room_id in attachments:
        room_geom = room_geoms.get(room_id)
        structure_geom = structure_geoms.get(structure_id)
        if room_geom is None or structure_geom is None:
            missing = "room" if room_geom is None else "structure"
            logger.debug(
                "Skipping visualization link %s→%s due to missing %s geometry",
                structure_id,
                room_id,
                missing,
            )
            continue

        start = structure_geom.centroid
        end = room_geom.centroid
        ax.plot(
            [start.x, end.x],
            [start.y, end.y],
            color=room_colors.get(room_id, "tab:green"),
            linestyle="--",
            linewidth=1.5,
        )

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_title("Room ↔ Structure Associations")

    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    logger.debug("Saved room/structure association debug image to %s", output_path)
    return output_path
