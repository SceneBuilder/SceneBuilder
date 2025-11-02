"""Utilities for exposing Blender-derived bounds to the linter."""

from __future__ import annotations

from scene_builder.decoder.blender import blender
from scene_builder.definition.scene import Object
from scene_builder.validation.models import AABB


def _box_from_tuple(
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]]
) -> AABB:
    min_corner, max_corner = bounds
    return AABB(
        min_corner=(float(min_corner[0]), float(min_corner[1]), float(min_corner[2])),
        max_corner=(float(max_corner[0]), float(max_corner[1]), float(max_corner[2])),
    )


def bounds_from_blender(object_id: str) -> AABB | None:
    """Compute world-space bounds for a tracked object using Blender state."""

    raw_bounds = blender.get_object_bounds(object_id)
    if raw_bounds is None:
        return None
    return _box_from_tuple(raw_bounds)


def blender_size_provider(obj: Object) -> AABB | None:
    """Return Blender-derived world-space bounds for ``obj`` if available."""

    return bounds_from_blender(obj.id)
