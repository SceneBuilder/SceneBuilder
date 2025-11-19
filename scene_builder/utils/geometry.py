"""Geometry utility functions for scene building."""

import math
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from scene_builder.definition.scene import Vector2
from scene_builder.logging import logger


def convert_to_shapely(boundary: Iterable[Vector2]) -> Polygon:
    """Build a valid Shapely polygon from an iterable of ``Vector2`` points."""

    coords = [(vertex.x, vertex.y) for vertex in boundary]
    if len(coords) < 3:
        raise ValueError("A polygon requires at least three boundary vertices.")

    polygon = Polygon(coords)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    if polygon.is_empty or polygon.area <= 0.0:
        raise ValueError("Boundary does not form a valid polygon with positive area.")

    return polygon


def convert_to_listvec2(polygon: list[Vector2]):
    """Convert shapely.Polygon to list[Vector2]"""
    # Note: Shapely polygon.exterior.coords includes a duplicate closing point, which we don't need (?)
    return [Vector2(x=x, y=y) for x, y in list(polygon.exterior.coords)[:-1]]


def longest_edge_angle(polygon: Polygon | list[Vector2]) -> float:
    """
    Calculate the angle (degrees) of the longest edge in a polygon.

    Accepts a shapely Polygon or a list of Vector2 points.
    Returns angle in degrees from X-axis (counterclockwise).
    """
    # Convert to coordinate list
    if isinstance(polygon, Polygon):
        coords = list(polygon.exterior.coords[:-1])  # Exclude duplicate last point
    elif isinstance(polygon, list) and polygon and isinstance(polygon[0], Vector2):
        coords = [(v.x, v.y) for v in polygon]
    else:
        raise TypeError("Expected shapely Polygon or list[Vector2]")

    max_length = 0.0
    angle = 0.0

    for i in range(len(coords)):
        p1 = coords[i]
        p2 = coords[(i + 1) % len(coords)]

        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)

        if length > max_length:
            max_length = length
            angle = math.degrees(math.atan2(dy, dx))

    return angle


def longest_edge_direction(polygon: Polygon | list[Vector2]) -> tuple[float, float] | None:
    """Return a unit direction vector for the polygon's longest edge.

    Uses ``longest_edge_angle`` to avoid duplicating edge-walk logic.
    """
    try:
        angle_deg = longest_edge_angle(polygon)
    except (TypeError, ValueError):
        return None

    angle_rad = math.radians(angle_deg)
    dx = math.cos(angle_rad)
    dy = math.sin(angle_rad)
    length = math.hypot(dx, dy)
    if length == 0.0:
        return None
    return (dx / length, dy / length)


def misalignment_angle(angle_deg: float) -> float:
    """Fold an angle toward parallelism (0° means parallel/anti-parallel, 90° means orthogonal)."""
    angle_norm = abs(angle_deg) % 360.0
    if angle_norm > 180.0:
        angle_norm = 360.0 - angle_norm
    return min(angle_norm, 180.0 - angle_norm)


def angle_between_unit_vectors(
    a: tuple[float, float],
    b: tuple[float, float],
) -> float | None:
    """Return the angle between two (ideally unit) 2D vectors in degrees."""
    ax, ay = a
    bx, by = b
    len_a = math.hypot(ax, ay)
    len_b = math.hypot(bx, by)
    if len_a == 0.0 or len_b == 0.0:
        return None

    dot = (ax * bx + ay * by) / (len_a * len_b)
    dot = max(-1.0, min(1.0, dot))  # clamp for numerical stability
    return math.degrees(math.acos(dot))


def boundary_to_geometry(boundary: Iterable[Vector2] | None) -> BaseGeometry | None:
    """Convert a boundary definition into an appropriate Shapely geometry."""
    if not boundary:
        return None

    coords = [(v.x, v.y) for v in boundary]

    if len(coords) == 1:
        return Point(coords[0])
    if len(coords) == 2:
        return LineString(coords)

    polygon = Polygon(coords)
    if not polygon.is_valid or polygon.area == 0.0:
        return LineString(coords)
    return polygon


def boundary_distance(
    boundary_a: Iterable[Vector2] | None,
    boundary_b: Iterable[Vector2] | None,
) -> float | None:
    """Compute the shortest distance between two boundaries."""
    geom_a = boundary_to_geometry(boundary_a)
    geom_b = boundary_to_geometry(boundary_b)
    if geom_a is None or geom_b is None:
        return None
    return geom_a.distance(geom_b)


def are_boundaries_close(
    boundary_a: Iterable[Vector2] | None,
    boundary_b: Iterable[Vector2] | None,
    max_distance: float,
) -> bool:
    """Return True if two boundaries are within a specified distance."""
    distance = boundary_distance(boundary_a, boundary_b)
    if distance is None:
        return False
    return distance <= max_distance


def nearest_boundary_segment_orientation(
    polygon: Polygon,
    target: BaseGeometry,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]] | None:
    """Return the exterior segment nearest to ``target`` and its direction/normal.

    The direction vector runs from the segment start to end and is normalized.
    The normal is a unit vector pointing outward based on the exterior ring
    winding (CCW → left-hand normal, CW → right-hand normal).
    """
    if polygon.is_empty or target.is_empty:
        return None

    coords = list(polygon.exterior.coords)
    if len(coords) < 2:
        return None

    closest: tuple[tuple[float, float], tuple[float, float]] | None = None
    min_distance = math.inf

    for idx in range(len(coords) - 1):
        start = coords[idx]
        end = coords[idx + 1]
        segment = LineString([start, end])
        distance = segment.distance(target)
        if distance < min_distance:
            min_distance = distance
            closest = (start, end)

    if closest is None:
        return None

    (x1, y1), (x2, y2) = closest
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0.0:
        return None

    direction = (dx / length, dy / length)
    normal = (
        (direction[1], -direction[0]) if polygon.exterior.is_ccw else (-direction[1], direction[0])
    )

    return (x1, y1), (x2, y2), direction, normal


def distance_to_box_2d(
    point: tuple[float, float] | Vector2,
    min_corner: tuple[float, float] | Vector2,
    max_corner: tuple[float, float] | Vector2,
) -> float:
    """Return the shortest 2D distance from a point to an axis-aligned bounding box.

    Args:
        point: 2D point as (x, y) tuple or Vector2
        min_corner: Minimum corner of bounding box as (x, y) tuple or Vector2
        max_corner: Maximum corner of bounding box as (x, y) tuple or Vector2

    Returns:
        Distance in meters
    """
    # Extract coordinates - works with tuples, Vector2, or any object with x/y attributes
    if isinstance(point, tuple):
        px, py = point
    else:
        px, py = point.x, point.y

    if isinstance(min_corner, tuple):
        min_x, min_y = min_corner
    else:
        min_x, min_y = min_corner.x, min_corner.y

    if isinstance(max_corner, tuple):
        max_x, max_y = max_corner
    else:
        max_x, max_y = max_corner.x, max_corner.y

    dx = max(min_x - px, 0, px - max_x)
    dy = max(min_y - py, 0, py - max_y)
    return math.sqrt(dx * dx + dy * dy)


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

    cx /= 6 * area
    cy /= 6 * area

    return Vector2(x=cx, y=cy)


def round_vector2(v: Vector2, ndigits: int = 2) -> Vector2:
    """Round Vector2 coordinates to specified decimal places.

    Args:
        v: Vector2 to round.
        ndigits: Number of decimal places (default: 2).

    Returns:
        New Vector2 with rounded coordinates.
    """
    return Vector2(x=round(v.x, ndigits), y=round(v.y, ndigits))


def round_vector2_list(vertices: list[Vector2], ndigits: int = 2) -> list[Vector2]:
    """Round all Vector2 coordinates in a list.

    Args:
        vertices: List of Vector2 objects to round.
        ndigits: Number of decimal places (default: 2).

    Returns:
        New list with rounded Vector2 objects.
    """
    return [round_vector2(v, ndigits) for v in vertices]


def _perpendicular_distance(point: Vector2, line_start: Vector2, line_end: Vector2) -> float:
    """Calculate perpendicular distance from point to line segment.

    Args:
        point: Point to measure distance from.
        line_start: Start of line segment.
        line_end: End of line segment.

    Returns:
        Perpendicular distance from point to line.
    """
    dx = line_end.x - line_start.x
    dy = line_end.y - line_start.y

    # Handle degenerate case where line segment is a point
    if dx == 0 and dy == 0:
        return ((point.x - line_start.x) ** 2 + (point.y - line_start.y) ** 2) ** 0.5

    # Calculate perpendicular distance using cross product formula
    numerator = abs(dx * (line_start.y - point.y) - (line_start.x - point.x) * dy)
    denominator = (dx**2 + dy**2) ** 0.5

    return numerator / denominator


def _rdp_simplify(vertices: list[Vector2], epsilon: float, start: int, end: int) -> list[int]:
    """Recursive Ramer-Douglas-Peucker algorithm implementation.

    Args:
        vertices: List of vertices.
        epsilon: Distance threshold.
        start: Start index.
        end: End index.

    Returns:
        List of indices to keep.
    """
    if end - start <= 1:
        return [start, end]

    # Find point with maximum distance from line segment
    max_distance = 0.0
    max_index = start

    for i in range(start + 1, end):
        distance = _perpendicular_distance(vertices[i], vertices[start], vertices[end])
        if distance > max_distance:
            max_distance = distance
            max_index = i

    # If max distance is greater than epsilon, recursively simplify
    if max_distance > epsilon:
        left_indices = _rdp_simplify(vertices, epsilon, start, max_index)
        right_indices = _rdp_simplify(vertices, epsilon, max_index, end)
        # Combine results, avoiding duplicate at max_index
        return left_indices[:-1] + right_indices
    else:
        return [start, end]


def _triangle_area(p1: Vector2, p2: Vector2, p3: Vector2) -> float:
    """Calculate area of triangle formed by three points.

    Args:
        p1: First point.
        p2: Second point.
        p3: Third point.

    Returns:
        Area of triangle.
    """
    return abs((p2.x - p1.x) * (p3.y - p1.y) - (p3.x - p1.x) * (p2.y - p1.y)) / 2.0


def _vw_simplify(vertices: list[Vector2], epsilon: float) -> list[Vector2]:
    """Visvalingam-Whyatt algorithm implementation.

    Args:
        vertices: List of vertices.
        epsilon: Area threshold.

    Returns:
        Simplified list of vertices.
    """
    if len(vertices) <= 3:
        return vertices.copy()

    # Create list of vertices with their effective areas
    # Each entry: (index, vertex, area)
    indexed_vertices = []
    for i, v in enumerate(vertices):
        indexed_vertices.append([i, v, float("inf")])

    # Calculate initial areas for each vertex
    for i in range(1, len(indexed_vertices) - 1):
        prev_v = indexed_vertices[i - 1][1]
        curr_v = indexed_vertices[i][1]
        next_v = indexed_vertices[i + 1][1]
        indexed_vertices[i][2] = _triangle_area(prev_v, curr_v, next_v)

    # Iteratively remove vertices with smallest area
    while len(indexed_vertices) > 3:
        # Find vertex with minimum area
        min_area = float("inf")
        min_idx = -1

        for i in range(1, len(indexed_vertices) - 1):
            if indexed_vertices[i][2] < min_area:
                min_area = indexed_vertices[i][2]
                min_idx = i

        # Stop if minimum area exceeds threshold
        if min_area > epsilon:
            break

        # Remove vertex with minimum area
        indexed_vertices.pop(min_idx)

        # Recalculate areas for neighbors
        if min_idx > 0 and min_idx < len(indexed_vertices):
            prev_v = indexed_vertices[min_idx - 1][1]
            curr_v = indexed_vertices[min_idx][1]
            next_v = (
                indexed_vertices[(min_idx + 1) % len(indexed_vertices)][1]
                if min_idx + 1 < len(indexed_vertices)
                else indexed_vertices[0][1]
            )

            if min_idx < len(indexed_vertices) - 1:
                indexed_vertices[min_idx][2] = _triangle_area(prev_v, curr_v, next_v)

        if min_idx - 1 > 0 and min_idx - 1 < len(indexed_vertices) - 1:
            prev_v = indexed_vertices[min_idx - 2][1]
            curr_v = indexed_vertices[min_idx - 1][1]
            next_v = indexed_vertices[min_idx][1]
            indexed_vertices[min_idx - 1][2] = _triangle_area(prev_v, curr_v, next_v)

    return [entry[1] for entry in indexed_vertices]


def remove_collinear_points(vertices: list[Vector2], epsilon: float = 1e-10) -> list[Vector2]:
    """Remove collinear points from a polygon using Shapely's simplify method.

    Uses Shapely's simplify() with tolerance=0 to remove perfectly collinear points.
    The epsilon parameter is ignored when using Shapely (kept for API compatibility).

    Args:
        vertices: List of vertices defining the polygon boundary.
        epsilon: Not used (kept for API compatibility).

    Returns:
        List of vertices with collinear points removed.

    Raises:
        ValueError: If fewer than 3 vertices are provided.
    """
    if len(vertices) < 3:
        raise ValueError("Need at least 3 vertices to define a polygon")

    if len(vertices) == 3:
        return vertices.copy()

    # Convert to Shapely Polygon
    coords = [(v.x, v.y) for v in vertices]
    polygon = Polygon(coords)

    # Simplify with tolerance=0 to remove only collinear points
    # simplified = polygon.simplify(tolerance=0, preserve_topology=True)
    simplified = polygon.simplify(tolerance=epsilon, preserve_topology=True)  # ALT

    # Convert back to Vector2 list
    # Note: Shapely polygon.exterior.coords includes a duplicate closing point
    result = [Vector2(x=x, y=y) for x, y in list(simplified.exterior.coords)[:-1]]

    # Ensure we still have at least 3 vertices
    if len(result) < 3:
        return vertices.copy()

    return result


def simplify_polygon(
    vertices: list[Vector2], epsilon: float = 1e-10, strategy: str = "rdp", verbose: bool = False
) -> list[Vector2]:
    """Simplify a polygon using specified algorithm.

    Args:
        vertices: List of vertices defining the polygon boundary.
        epsilon: Tolerance parameter. For RDP, this is distance threshold.
                For VW, this is area threshold.
        strategy: Simplification strategy - "rdp" for Ramer-Douglas-Peucker,
                 "vw" for Visvalingam-Whyatt, or "collinear" for collinear
                 point removal (default: "rdp").
        verbose: If True, log vertex reduction statistics (default: False).

    Returns:
        Simplified list of vertices.

    Raises:
        ValueError: If strategy is not valid, or if fewer than 3 vertices.
    """
    if len(vertices) < 3:
        raise ValueError("Need at least 3 vertices to define a polygon")

    if strategy not in ["rdp", "vw", "collinear"]:
        raise ValueError(f"Invalid strategy '{strategy}'. Must be 'rdp', 'vw', or 'collinear'")

    original_count = len(vertices)

    if strategy == "rdp":
        # RDP algorithm
        indices = _rdp_simplify(vertices, epsilon, 0, len(vertices) - 1)
        # Remove duplicate last index if it equals first (closed polygon)
        if len(indices) > 1 and indices[-1] == len(vertices) - 1:
            # Check if we should close the polygon
            if vertices[0].x == vertices[-1].x and vertices[0].y == vertices[-1].y:
                indices = indices[:-1]
        result = [vertices[i] for i in indices]
    elif strategy == "vw":
        # VW algorithm
        result = _vw_simplify(vertices, epsilon)
    else:
        # Collinear point removal
        result = remove_collinear_points(vertices, epsilon)

    if verbose:
        new_count = len(result)
        reduced = original_count - new_count
        if reduced > 0:
            percentage = (reduced / original_count) * 100
            logger.debug(
                f"Simplified polygon using '{strategy}': "
                f"{original_count} → {new_count} vertices "
                f"({reduced} removed, {percentage:.1f}% reduction)"
            )
        else:
            logger.debug(
                f"Simplified polygon using '{strategy}': "
                f"No vertices removed ({original_count} vertices)"
            )

    return result


def save_polygon_image(
    vertices: list[Vector2],
    output_path: str | Path,
    format: str = "png",
    fill_color: str = "lightblue",
    edge_color: str = "black",
    edge_width: float = 2.0,
    vertex_color: str = "red",
    vertex_size: float = 50.0,
    show_vertices: bool = True,
    show_labels: bool = False,
    figsize: tuple[float, float] = (8, 8),
    dpi: int = 150,
) -> Path:
    """Save a polygon visualization to an image file.

    Args:
        vertices: List of Vector2 vertices defining the polygon.
        output_path: Path to save the image file.
        format: Image format - "png", "jpg", "svg" (default: "png").
        fill_color: Polygon fill color (default: "lightblue").
        edge_color: Polygon edge color (default: "black").
        edge_width: Edge line width (default: 2.0).
        vertex_color: Vertex marker color (default: "red").
        vertex_size: Vertex marker size (default: 50.0).
        show_vertices: Whether to show vertex markers (default: True).
        show_labels: Whether to show vertex index labels (default: False).
        figsize: Figure size as (width, height) in inches (default: (8, 8)).
        dpi: Resolution in dots per inch (default: 150).

    Returns:
        Path to the saved image file.

    Raises:
        ValueError: If fewer than 3 vertices or invalid format.
    """
    if len(vertices) < 3:
        raise ValueError("Need at least 3 vertices to define a polygon")

    if format not in ["png", "jpg", "jpeg", "svg"]:
        raise ValueError(f"Invalid format '{format}'. Must be 'png', 'jpg', 'jpeg', or 'svg'")

    output_path = Path(output_path)

    # Convert Vector2 list to shapely Polygon
    coords = [(v.x, v.y) for v in vertices]
    polygon = Polygon(coords)

    # Create figure and axis
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

    # Plot polygon
    x, y = polygon.exterior.xy
    ax.fill(x, y, alpha=0.5, fc=fill_color, ec=edge_color, linewidth=edge_width)

    # Plot vertices
    if show_vertices:
        vertex_x = [v.x for v in vertices]
        vertex_y = [v.y for v in vertices]
        ax.scatter(vertex_x, vertex_y, c=vertex_color, s=vertex_size, zorder=5)

    # Add vertex labels
    if show_labels:
        for i, v in enumerate(vertices):
            ax.annotate(
                str(i),
                (v.x, v.y),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=10,
                color="darkred",
            )

    # Set equal aspect ratio and add grid
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_title(f"Polygon ({len(vertices)} vertices)")

    # Save figure
    plt.tight_layout()
    plt.savefig(output_path, format=format, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    return output_path


def get_object_volume(obj) -> float:
    """Calculate object volume from dimensions.

    Args:
        obj: Blender object (or any object with dimensions attribute)

    Returns:
        Volume in cubic meters
    """
    d = obj.dimensions
    return d.x * d.y * d.z


def calculate_bounds_2d(
    vertices_2d: list[tuple[float, float]],
) -> dict[str, float | bool | int]:
    """
    Calculate bounding box dimensions from 2D vertices.

    Args:
        vertices_2d: List of (x, y) coordinate tuples

    Returns:
        Dictionary containing min/max coordinates, width, height, and area
    """

    if not vertices_2d:
        return {
            "value": False,
            "count": 0,
            "min_x": 0,
            "max_x": 0,
            "min_y": 0,
            "max_y": 0,
            "width": 0,
            "height": 0,
            "area": 0,
            "has_area": False,
        }

    x_coords = [x for x, y in vertices_2d]
    y_coords = [y for x, y in vertices_2d]

    min_x, max_x = min(x_coords), max(x_coords)
    min_y, max_y = min(y_coords), max(y_coords)
    width = max_x - min_x
    height = max_y - min_y
    area = width * height

    return {
        "value": True,
        "count": len(vertices_2d),
        "min_x": min_x,
        "max_x": max_x,
        "min_y": min_y,
        "max_y": max_y,
        "width": width,
        "height": height,
        "area": area,
        "has_area": (width > 0 and height > 0),
    }
