"""Geometry utility functions for scene building."""

from scene_builder.definition.scene import Vector2


def polygon_centroid(vertices: list[Vector2]) -> Vector2:
    """Calculate the centroid of a polygon given its boundary vertices.

    Uses the standard polygon centroid formula which is exact for any
    simple polygon (convex or concave).

    Args:
        vertices: List of vertices defining the polygon boundary,
                 ordered clockwise or counter-clockwise.

    Returns:
        The centroid position as a Vector2.

    Raises:
        ValueError: If fewer than 3 vertices are provided.
    """
    n = len(vertices)
    if n < 3:
        raise ValueError("Need at least 3 vertices to define a polygon")

    # Compute signed area and centroid coordinates using the shoelace formula
    area = 0.0
    cx = 0.0
    cy = 0.0

    for i in range(n):
        x0, y0 = vertices[i].x, vertices[i].y
        x1, y1 = vertices[(i + 1) % n].x, vertices[(i + 1) % n].y

        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross

    area *= 0.5

    # Handle degenerate case (collinear points)
    if abs(area) < 1e-10:
        # Fall back to simple average
        x_avg = sum(v.x for v in vertices) / n
        y_avg = sum(v.y for v in vertices) / n
        return Vector2(x=x_avg, y=y_avg)

    cx /= (6 * area)
    cy /= (6 * area)

    return Vector2(x=cx, y=cy)
