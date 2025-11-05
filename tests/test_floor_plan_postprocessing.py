import argparse
import random
from pathlib import Path
from typing import Iterable, Optional

import matplotlib.pyplot as plt
import pytest
from shapely.geometry import Polygon

from scene_builder.msd_integration.loader import (
    MSDLoader,
    get_dominant_angle,
    normalize_floor_plan_orientation,
)
from scene_builder.utils.room import render_structure_links


OUTPUT_DIR = Path("test_output/floorplan_postprocessing")


def _run_orientation_correction(
    strategy: str, runs: int, show_grid: bool = False
) -> tuple[bool, str | None]:
    random.seed(2025)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    loader = MSDLoader()
    buildings = loader.get_building_list()
    if not buildings:
        return False, "No MSD buildings available for testing."

    successes = 0
    attempts = 0

    while successes < runs and attempts < runs * 5:
        attempts += 1

        building_id = random.choice(buildings)
        apartments = loader.get_apartments_in_building(building_id)
        if not apartments:
            continue

        apartment_id = random.choice(apartments)
        scene = loader.get_scene(apartment_id)
        if scene is None or not scene.rooms:
            continue

        rooms = scene.rooms
        original_polys = [_room_to_polygon(room) for room in rooms]
        _, correction_angle = normalize_floor_plan_orientation(rooms, strategy=strategy)
        corrected_polys = [_room_to_polygon(room) for room in rooms]

        residual = abs(get_dominant_angle(corrected_polys, strategy=strategy))
        if residual > 2.0:
            continue

        _save_plot(
            original_polys=original_polys,
            corrected_polys=corrected_polys,
            strategy=strategy,
            idx=successes,
            apartment_id=apartment_id,
            applied_angle=correction_angle,
            residual=residual,
            show_grid=show_grid,
        )
        successes += 1

    if successes < runs:
        return False, "Insufficient MSD apartments with valid geometry for test."

    return True, None


def _room_to_polygon(room) -> Polygon:
    coords = [(v.x, v.y) for v in room.boundary]
    return Polygon(coords)


def _save_plot(
    original_polys: Iterable[Polygon],
    corrected_polys: Iterable[Polygon],
    strategy: str,
    idx: int,
    apartment_id: str,
    applied_angle: float,
    residual: float,
    show_grid: bool,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(8, 4))

    _plot_polygons(axes[0], original_polys, "Original", show_grid=show_grid)
    _plot_polygons(axes[1], corrected_polys, "Corrected", show_grid=show_grid)

    apt_label = apartment_id[:8] if apartment_id else "unknown"
    fig.suptitle(
        f"{strategy} • {apt_label}\nangle={applied_angle:.2f}° residual={residual:.2f}°",
        fontsize=11,
    )

    output_path = OUTPUT_DIR / f"msd_{strategy}_{idx:02d}.jpg"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _plot_polygons(ax, polygons: Iterable[Polygon], title: str, show_grid: bool = True) -> None:
    for poly in polygons:
        if poly.is_empty:
            continue
        x, y = poly.exterior.xy
        ax.fill(x, y, alpha=0.6)
        ax.plot(x, y, color="black", linewidth=0.8)
    ax.set_title(title)
    ax.set_aspect("equal")
    if show_grid:
        ax.grid(True, alpha=0.2, linestyle="--")
    # ax.axis("off")
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)

    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)


@pytest.mark.parametrize("strategy", ["length_weighted", "count", "complex_sum"])
def test_orientation_correction_stability(strategy):
    success, reason = _run_orientation_correction(strategy=strategy, runs=10)
    if not success:
        pytest.skip(reason)


def _run_structure_links_visualization(
    building_id: int = 2144, apartment_id: Optional[str] = None
) -> Optional[Path]:
    """Generate a debug image of room ↔ structure associations.

    Returns path to the saved image if generated, otherwise None.
    """
    loader = MSDLoader()

    # Resolve apartment id
    apt_id = apartment_id
    if apt_id is None:
        apartments = loader.get_apartments_in_building(building_id)
        if not apartments:
            return None
        apt_id = apartments[0]

    # Build rooms with structures attached (never returns structures as rooms)
    graph = loader.create_graph(apt_id, format="sb")
    if graph is None:
        return None
    rooms = loader.convert_graph_to_rooms(graph, include_structure=True)

    # Extract structures and attachments from rooms
    structures = []
    attachments: list[tuple[str, str]] = []
    for room in rooms:
        if not getattr(room, "structure", None):
            continue
        for s in room.structure:
            structures.append(s)
            attachments.append((s.id, room.id))

    if not structures:
        # No structures to visualize
        return None

    # Render debug visualization into the existing postprocessing output dir
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"structure_links_{apt_id}.png"
    render_structure_links(rooms, structures, attachments, out_path)
    return out_path if out_path.exists() else None


def test_structure_links_visualization():
    """Pytest wrapper for structure links visualization."""
    out = _run_structure_links_visualization()
    if out is None:
        pytest.skip("No structures available to visualize or dataset unavailable.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Floor plan postprocessing visualizations and debug utilities."
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=10,
        help="Number of random floorplans to generate per strategy.",
    )
    parser.add_argument(
        "--grid",
        action="store_false",
        help="Overlay a light grid on the saved plots.",
    )
    parser.add_argument(
        "--links",
        action="store_true",
        default=True,
        help="Generate a room ↔ structure links debug image (saved to output dir).",
    )
    parser.add_argument(
        "--building-id",
        type=int,
        default=2144,
        help="Building ID to use when generating structure links visualization.",
    )
    parser.add_argument(
        "--apartment-id",
        type=str,
        default=None,
        help="Specific apartment ID. If omitted, uses the first apartment in the building.",
    )
    args = parser.parse_args()

    for strategy in ("length_weighted", "count", "complex_sum"):
        success, reason = _run_orientation_correction(
            strategy=strategy, runs=args.runs, show_grid=args.grid
        )
        if not success and reason:
            print(reason)

    if args.links:
        out = _run_structure_links_visualization(
            building_id=args.building_id, apartment_id=args.apartment_id
        )
        if out is None:
            print("No structure links visualization generated (no data or dataset unavailable).")
        else:
            print(f"Saved structure links visualization: {out}")
