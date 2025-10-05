# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.17.2
#   kernelspec:
#     display_name: sb
#     language: python
#     name: python3
# ---

# %% [markdown]
# # **MSD Orientation Normalization**

# %% [markdown]
# ## **Setup**

# %%
import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, MultiPolygon
from shapely.affinity import rotate

from scene_builder.msd_integration.loader import MSDLoader


# %% [markdown]
# ## **Functions**

# %%
def get_dominant_angle(polygons, visualize_histogram=False, strategy='length_weighted'):
    """
    Calculates the dominant angle of a set of polygons using a histogram.

    Args:
        polygons (list): A list of shapely Polygon objects.
        visualize_histogram (bool): If True, display a histogram of edge angles.
        strategy (str): Weighting strategy for histogram:
            - 'length_weighted': Weight edges by their length (robust to segmentation)
            - 'count': Each edge gets equal weight (legacy behavior)

    Returns:
        float: The dominant angle in degrees to correct for, i.e.,
               the angle to rotate by to make the shapes axis-aligned.
    """
    angles = []
    edge_lengths = []

    for poly in polygons:
        # Extract the exterior coordinates
        coords = np.array(poly.exterior.coords)

        # Calculate the vectors for each edge
        vectors = np.diff(coords, axis=0)

        # Calculate the angle of each vector
        # We use np.arctan2 which returns angles in radians [-pi, pi]
        edge_angles = np.arctan2(vectors[:, 1], vectors[:, 0])

        # Convert angles to degrees and normalize to [0, 180)
        edge_angles_deg = np.rad2deg(edge_angles) % 180

        # Calculate edge lengths
        lengths = np.linalg.norm(vectors, axis=1)

        angles.extend(edge_angles_deg)
        edge_lengths.extend(lengths)

    # Now, normalize all angles to the range [0, 90) to treat
    # parallel and perpendicular lines the same.
    normalized_angles = [angle % 90 for angle in angles]

    # Use a histogram to find the most frequent angle "bin"
    # We use 90 bins for 0-89 degrees.
    if strategy == 'length_weighted':
        # Weight each edge by its length
        hist, bin_edges = np.histogram(normalized_angles, bins=90, range=(0, 90), weights=edge_lengths)
        ylabel = 'Weighted Frequency (by length)'
        title_suffix = ' (Length-Weighted)'
    elif strategy == 'count':
        # Each edge gets equal weight (legacy behavior)
        hist, bin_edges = np.histogram(normalized_angles, bins=90, range=(0, 90))
        ylabel = 'Frequency'
        title_suffix = ' (Count-Based)'
    else:
        raise ValueError(f"Unknown strategy: {strategy}. Use 'length_weighted' or 'count'.")

    # The dominant angle is the center of the bin with the highest count
    dominant_angle_bin = np.argmax(hist)
    dominant_angle = bin_edges[dominant_angle_bin] + 0.5 # Get bin center

    # The correction angle is the negative of the dominant angle.
    # We choose the smaller rotation, e.g., rotate by -15 deg instead of +75 deg.
    if dominant_angle > 45:
        correction_angle = -(90 - dominant_angle)
    else:
        correction_angle = -dominant_angle

    # Visualize histogram if requested
    if visualize_histogram:
        plt.figure(figsize=(10, 5))
        plt.bar(bin_edges[:-1], hist, width=1.0, edgecolor='black', alpha=0.7)
        plt.axvline(dominant_angle, color='red', linestyle='--', linewidth=2,
                   label=f'Dominant angle: {dominant_angle:.2f}°')
        plt.xlabel('Edge Angle (degrees)', fontsize=12)
        plt.ylabel(ylabel, fontsize=12)
        plt.title(f'Distribution of Edge Angles (Normalized to 0-90°){title_suffix}', fontsize=14)
        plt.xlim(0, 90)
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.tight_layout()
        plt.show()

    return correction_angle


# %%
def analyze_multiple_floor_plans(n_floor_plans=3, show_vertices=True, strategy='length_weighted'):
    """
    Analyze multiple random floor plans and visualize them in a grid.

    Args:
        n_floor_plans (int): Number of random floor plans to analyze
        show_vertices (bool): If True, add a fourth column showing vertices
        strategy (str): Weighting strategy - 'length_weighted' or 'count'

    Returns:
        list: List of tuples containing (floor_plan_id, correction_angle)
    """
    msd_loader = MSDLoader()
    results = []

    # Create figure with 3 or 4 columns depending on show_vertices
    n_cols = 4 if show_vertices else 3
    fig_width = 24 if show_vertices else 18
    fig, axes = plt.subplots(n_floor_plans, n_cols, figsize=(fig_width, 6 * n_floor_plans))

    # Ensure axes is 2D even for single row
    if n_floor_plans == 1:
        axes = axes.reshape(1, -1)

    for i in range(n_floor_plans):
        # Get random floor plan
        floor_plan_id = msd_loader.get_random_apartment()
        graph = msd_loader.create_graph(floor_plan_id)
        scene_data = msd_loader.graph_to_scene_data(graph)

        # Convert to shapely polygons
        polygons = []
        for room in scene_data['rooms']:
            coords = [(v.x, v.y) for v in room.boundary]
            polygons.append(Polygon(coords))

        # Calculate correction angle and get histogram data
        angles = []
        edge_lengths = []
        for poly in polygons:
            coords = np.array(poly.exterior.coords)
            vectors = np.diff(coords, axis=0)
            edge_angles = np.arctan2(vectors[:, 1], vectors[:, 0])
            edge_angles_deg = np.rad2deg(edge_angles) % 180
            lengths = np.linalg.norm(vectors, axis=1)
            angles.extend(edge_angles_deg)
            edge_lengths.extend(lengths)

        normalized_angles = [angle % 90 for angle in angles]

        # Apply strategy
        if strategy == 'length_weighted':
            hist, bin_edges = np.histogram(normalized_angles, bins=90, range=(0, 90), weights=edge_lengths)
        else:
            hist, bin_edges = np.histogram(normalized_angles, bins=90, range=(0, 90))

        dominant_angle_bin = np.argmax(hist)
        dominant_angle = bin_edges[dominant_angle_bin] + 0.5

        if dominant_angle > 45:
            # correction_angle = -(90 - dominant_angle)
            # correction_angle = -dominant_angle
            correction_angle = -(dominant_angle - 90)
        else:
            correction_angle = -dominant_angle

        # Create MultiPolygons
        floor_plan = MultiPolygon(polygons)
        aligned_floor_plan = rotate(floor_plan, correction_angle, origin='center')

        # Store results
        results.append((floor_plan_id, correction_angle))

        # Plot original floor plan (column 0)
        ax_orig = axes[i, 0]
        ax_orig.set_title(f'Original Floor Plan\nID: {floor_plan_id[:8]}...', fontsize=10)
        for poly in floor_plan.geoms:
            x, y = poly.exterior.xy
            ax_orig.fill(x, y, alpha=0.5, edgecolor='black', linewidth=1.5)
        ax_orig.set_aspect('equal')
        ax_orig.grid(True, alpha=0.3)
        ax_orig.set_xlabel('X')
        ax_orig.set_ylabel('Y')

        # Plot aligned floor plan (column 1)
        ax_aligned = axes[i, 1]
        ax_aligned.set_title(f'Aligned Floor Plan\nRotated by {correction_angle:.2f}°', fontsize=10)
        for poly in aligned_floor_plan.geoms:
            x, y = poly.exterior.xy
            ax_aligned.fill(x, y, alpha=0.5, edgecolor='black', linewidth=1.5)
        ax_aligned.set_aspect('equal')
        ax_aligned.grid(True, alpha=0.3)
        ax_aligned.set_xlabel('X')
        ax_aligned.set_ylabel('Y')

        # Plot histogram (column 2)
        ax_hist = axes[i, 2]
        ax_hist.bar(bin_edges[:-1], hist, width=1.0, edgecolor='black', alpha=0.7)
        ax_hist.axvline(dominant_angle, color='red', linestyle='--', linewidth=2,
                       label=f'Dominant: {dominant_angle:.2f}°')
        ax_hist.set_xlabel('Edge Angle (degrees)', fontsize=10)
        ylabel = 'Weighted Frequency' if strategy == 'length_weighted' else 'Frequency'
        ax_hist.set_ylabel(ylabel, fontsize=10)
        strategy_label = 'Length-Weighted' if strategy == 'length_weighted' else 'Count-Based'
        ax_hist.set_title(f'Edge Angle Distribution ({strategy_label})\n({len(polygons)} rooms)', fontsize=10)
        ax_hist.set_xlim(0, 90)
        ax_hist.grid(True, alpha=0.3)
        ax_hist.legend()

        # Plot vertices visualization (column 3, optional)
        if show_vertices:
            ax_vertices = axes[i, 3]
            ax_vertices.set_title(f'Vertex Visualization\n({sum(len(p.exterior.coords)-1 for p in polygons)} total vertices)', fontsize=10)

            # Plot each room polygon with vertices
            for poly in floor_plan.geoms:
                x, y = poly.exterior.xy
                # Draw polygon
                ax_vertices.fill(x, y, alpha=0.3, edgecolor='black', linewidth=1.5)
                # Draw vertices as markers (exclude the closing vertex which duplicates the first)
                ax_vertices.plot(x[:-1], y[:-1], 'ro', markersize=3, alpha=0.2, label='Vertices' if poly == floor_plan.geoms[0] else '')

            ax_vertices.set_aspect('equal')
            ax_vertices.grid(True, alpha=0.3)
            ax_vertices.set_xlabel('X')
            ax_vertices.set_ylabel('Y')
            # Only show legend on first row
            if i == 0:
                ax_vertices.legend()

    plt.tight_layout()
    plt.show()

    return results


# %% [markdown]
# Example Usage

# %%
# Sample Data
p1 = Polygon([(0, 0), (0, 2), (4, 2), (4, 0)])
p2 = Polygon([(0, 2.5), (0, 4.5), (1.5, 4.5), (1.5, 2.5)])

# Group them into a MultiPolygon to easily rotate them together
floor_plan = MultiPolygon([p1, p2])

# Rotate the entire floor plan by a sample angle, e.g., 25 degrees
tilted_floor_plan = rotate(floor_plan, 25, origin='center')

# Now, let's pretend 'tilted_floor_plan.geoms' is your input
tilted_polygons = list(tilted_floor_plan.geoms)

# 1. Calculate the angle needed for correction
correction_angle = get_dominant_angle(tilted_polygons)
print(f"Calculated Correction Angle: {correction_angle:.2f} degrees")

# 2. Apply the rotation to align the floor plan
# We rotate the original tilted plan by the correction angle
aligned_floor_plan = rotate(tilted_floor_plan, correction_angle, origin='center')

# Now 'aligned_floor_plan' contains the axis-aligned polygons.
# You can save, plot, or further process these aligned shapes.

# %% [markdown]
# ## **Experiment**

# %% [markdown]
# ### Floor Plans from MSD Dataset

# %%
# Load MSD floor plan
msd_loader = MSDLoader()

# Option 1: Use a random apartment
floor_plan_id = msd_loader.get_random_apartment()

# Option 2: Use a specific apartment ID (uncomment to use)
# floor_plan_id = "b2e1f754f164e5b7c268485ca55495c8"

# Create graph and get room boundaries
graph = msd_loader.create_graph(floor_plan_id)
scene_data = msd_loader.graph_to_scene_data(graph)

# Convert room boundaries to shapely Polygons
msd_polygons = []
for room in scene_data['rooms']:
    coords = [(v.x, v.y) for v in room.boundary]
    msd_polygons.append(Polygon(coords))

print(f"Loaded {len(msd_polygons)} rooms from floor plan {floor_plan_id}")

# Calculate and apply correction angle (with histogram visualization)
msd_correction_angle = get_dominant_angle(msd_polygons, visualize_histogram=True)
print(f"MSD Floor Plan Correction Angle: {msd_correction_angle:.2f} degrees")

# Apply correction to align the floor plan
msd_floor_plan = MultiPolygon(msd_polygons)
aligned_msd_floor_plan = rotate(msd_floor_plan, msd_correction_angle, origin='center')

# %% [markdown]
# #### Single Floor Plan

# %%
# Visualize the floor plan before and after alignment
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 7))

# Plot original floor plan
ax1.set_title(f'Original Floor Plan\n(ID: {floor_plan_id})', fontsize=12)
for poly in msd_floor_plan.geoms:
    x, y = poly.exterior.xy
    ax1.fill(x, y, alpha=0.5, edgecolor='black', linewidth=1.5)
ax1.set_aspect('equal')
ax1.grid(True, alpha=0.3)
ax1.set_xlabel('X')
ax1.set_ylabel('Y')

# Plot aligned floor plan
ax2.set_title(f'Aligned Floor Plan\n(Rotated by {msd_correction_angle:.2f}°)', fontsize=12)
for poly in aligned_msd_floor_plan.geoms:
    x, y = poly.exterior.xy
    ax2.fill(x, y, alpha=0.5, edgecolor='black', linewidth=1.5)
ax2.set_aspect('equal')
ax2.grid(True, alpha=0.3)
ax2.set_xlabel('X')
ax2.set_ylabel('Y')

plt.tight_layout()
plt.show()

# %% [markdown]
# #### Batch Analysis

# %%
# Analyze multiple random floor plans at once with vertex visualization
# Using length-weighted strategy (default, robust to edge segmentation)
results = analyze_multiple_floor_plans(n_floor_plans=50, show_vertices=True, strategy='length_weighted')

# Print summary
print("\nSummary of analyzed floor plans:")
for floor_plan_id, correction_angle in results:
    print(f"  {floor_plan_id}: {correction_angle:.2f}°")

# %% [markdown]
# #### Strategy Comparison

# %%
# Compare strategies: length-weighted vs count-based
# Uncomment to see the difference between the two strategies:

# Length-weighted (recommended - robust to edge segmentation)
# results_weighted = analyze_multiple_floor_plans(n_floor_plans=3, show_vertices=True, strategy='length_weighted')

# Count-based (legacy behavior - sensitive to edge segmentation)
# results_count = analyze_multiple_floor_plans(n_floor_plans=3, show_vertices=True, strategy='count')
