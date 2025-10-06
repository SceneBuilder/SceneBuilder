"""Room utility functions for scene building."""

from scene_builder.definition.scene import Room, Vector2, Vector3
from scene_builder.utils.geometry import polygon_centroid


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
    restored.extra_info = None
    return restored
