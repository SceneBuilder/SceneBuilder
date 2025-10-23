import bpy
import bmesh
from mathutils import Vector

# Assumes object is selected and is a mesh
obj = bpy.context.active_object

if obj is None or obj.type != 'MESH':
    raise Exception("No mesh object selected.")

# Apply transforms to ensure geometry is clean (but keep rotation for testing local space)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

# Get dimensions
dims = obj.dimensions
if dims.x >= dims.y:
    axis_index = 1
    target_axis = Vector((0, 1, 0))  # Y axis
    axis_name = "Y"
else:
    axis_index = 0
    target_axis = Vector((1, 0, 0))  # X axis
    axis_name = "X"

# Switch to Edit Mode and access BMesh
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(obj.data)
bm.faces.ensure_lookup_table()

# Compare face normals in local space
def face_aligned(face, axis_vector, threshold=0.99):
    return face.normal.normalized().dot(axis_vector) > threshold

# Find faces aligned to both positive and negative directions
positive_axis = target_axis
negative_axis = target_axis * -1

positive_faces = [f for f in bm.faces if face_aligned(f, positive_axis)]
negative_faces = [f for f in bm.faces if face_aligned(f, negative_axis)]

if not positive_faces:
    raise Exception(f"No face found aligned with the +{axis_name} axis.")
if not negative_faces:
    raise Exception(f"No face found aligned with the -{axis_name} axis.")

# Pick the furthest faces in both directions
positive_face = max(
    positive_faces,
    key=lambda f: sum(v.co[axis_index] for v in f.verts) / len(f.verts)
)
negative_face = min(
    negative_faces,
    key=lambda f: sum(v.co[axis_index] for v in f.verts) / len(f.verts)
)

extrude_distance = 5.0

# Extrude positive face
for f in bm.faces:
    f.select_set(False)
positive_face.select_set(True)
bmesh.update_edit_mesh(obj.data)

positive_normal_world = obj.matrix_world.to_3x3() @ positive_face.normal.normalized()
bpy.ops.mesh.extrude_region_move(
    TRANSFORM_OT_translate={"value": positive_normal_world * extrude_distance}
)

# Extrude negative face
for f in bm.faces:
    f.select_set(False)
negative_face.select_set(True)
bmesh.update_edit_mesh(obj.data)

negative_normal_world = obj.matrix_world.to_3x3() @ negative_face.normal.normalized()
bpy.ops.mesh.extrude_region_move(
    TRANSFORM_OT_translate={"value": negative_normal_world * extrude_distance}
)

# Back to Object Mode
bpy.ops.object.mode_set(mode='OBJECT')
print(f"Extruded in both +{axis_name} and -{axis_name} directions by {extrude_distance}m each.")
