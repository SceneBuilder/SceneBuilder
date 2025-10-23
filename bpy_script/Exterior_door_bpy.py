import bpy
from pathlib import Path

# === CONFIGURATION ===

blend_file_path = "/Users/jaehkim/Library/Application Support/Blender/4.5/scripts/addons/Door It! Exterior Packed.blend"
object_name = "Door It! Exterior"

# Target area defined by these 4 corners:
# (0, 0), (0, 2), (4, 0), (4, 2) --> forms a rectangle 4m wide (X), 2m deep (Y)

target_width = 1 # X axis
target_depth = 2.0  # Y axis

actual_depth = target_depth / 2.0
print(f"Actual depth: {actual_depth}")

# Target center position
target_center = (target_width / 2.0, target_depth / 2.0, 0.0)  # Assuming bottom at Z=0

# === SCRIPT START ===

blend_path = Path(blend_file_path)

if not blend_path.exists():
    raise FileNotFoundError(f"Blend file not found: {blend_path}")

with bpy.data.libraries.load(str(blend_path), link=False) as (data_from, data_to):
    if object_name not in data_from.objects:
        raise ValueError(f"Object '{object_name}' not found in blend file.")
    data_to.objects = [object_name]

# Link and process object
for obj in data_to.objects:
    if obj is not None:
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.update()  # Ensure dimensions are correct

        # --- Step 1: Get Original Dimensions ---
        original_x = obj.dimensions.x
        original_y = obj.dimensions.y

        if original_x == 0 or original_y == 0:
            raise ValueError("Imported object has zero X or Y size.")

        # --- Step 2: Compute Scale Factors ---
        scale_x = target_width / original_x
        scale_y = target_depth / original_y

        # Apply non-uniform scale
        obj.scale.x *= scale_x
        obj.scale.y *= scale_y

        # Update again after scaling
        bpy.context.view_layer.update()

        # --- Step 3: Reposition to Center ---
        # After scaling, recenter it based on bounding box
#        bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
#        min_corner = [min(c[i] for c in bbox) for i in range(3)]
#        max_corner = [max(c[i] for c in bbox) for i in range(3)]

#        obj_center = [(min_corner[i] + max_corner[i]) / 2.0 for i in range(3)]

#        # Compute offset to move object center to target center
#        from mathutils import Vector
#        offset = Vector(target_center) - Vector(obj_center)
#        obj.location += offset

        # print(f"Scaled and positioned '{object_name}' to fit 4x2 area at {target_center}")
