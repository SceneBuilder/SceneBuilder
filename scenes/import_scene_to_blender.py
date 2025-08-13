import bpy
import yaml
import os

def clear_scene():
    """Clear all objects from the current scene."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    print("Cleared existing scene")

def create_placeholder_object(obj_data):
    """Create a placeholder cube for each object in the scene."""
    object_name = obj_data.get("name", "Unnamed Object")
    
    # Create a cube as placeholder
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.name = object_name
    
    # Set position, rotation, and scale
    pos = obj_data.get("position", {"x": 0, "y": 0, "z": 0})
    rot = obj_data.get("rotation", {"x": 0, "y": 0, "z": 0})
    scl = obj_data.get("scale", {"x": 1, "y": 1, "z": 1})
    
    obj.location = (pos["x"], pos["y"], pos["z"])
    obj.rotation_euler = (rot["x"], rot["y"], rot["z"])
    obj.scale = (scl["x"], scl["y"], scl["z"])
    
    # Add a material with random color to distinguish objects
    material = bpy.data.materials.new(name=f"{object_name}_Material")
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs[0].default_value = (
        hash(object_name) % 255 / 255,
        (hash(object_name) // 255) % 255 / 255,
        (hash(object_name) // (255*255)) % 255 / 255,
        1.0
    )
    obj.data.materials.append(material)
    
    print(f"Created placeholder for: {object_name}")
    return obj

def import_scene_from_yaml():
    """Import scene from the generated_scene.yaml file."""
    
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    yaml_path = os.path.join(script_dir, "generated_scene.yaml")
    
    if not os.path.exists(yaml_path):
        print(f"Error: Could not find {yaml_path}")
        return
    
    # Load YAML data
    with open(yaml_path, 'r') as f:
        scene_data = yaml.safe_load(f)
    
    print(f"Loading scene: {scene_data.get('category', 'Unknown')} - {', '.join(scene_data.get('tags', []))}")
    
    # Clear existing scene
    clear_scene()
    
    # Process each room
    for room_data in scene_data.get("rooms", []):
        room_id = room_data.get("id", "unknown_room")
        room_category = room_data.get("category", "unknown")
        print(f"Processing room: {room_id} ({room_category})")
        
        # Create objects in the room
        for obj_data in room_data.get("objects", []):
            create_placeholder_object(obj_data)
    
    print("Scene import complete!")
    print("Note: Objects are created as colored cubes. Replace with actual 3D models as needed.")

# Run the import
if __name__ == "__main__":
    import_scene_from_yaml()