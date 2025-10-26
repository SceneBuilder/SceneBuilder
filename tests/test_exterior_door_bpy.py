import bpy
import os
from pathlib import Path

# Install and enable add-on
addon_path = "/tmp/Door It! Interior 4.0,4.1.zip"
bpy.ops.preferences.addon_install(filepath=addon_path)
print("Addon installed")

# Enable the addon
bpy.ops.preferences.addon_enable(module="DoorItInterior")
bpy.ops.wm.save_userpref()
print("Addon enabled and preferences saved")

# Get the directory of the current script
script_dir = Path(os.path.dirname(os.path.realpath(__file__)))

# script_to_run = (script_dir / "../bpy_script/randomizing_door.py").resolve()

# Execute the script
# exec(compile(script_to_run.read_text(), str(script_to_run), "exec"), {"__file__": str(script_to_run)})
output_blend_file = script_dir / "addon_installed.blend"

# Save the current scene to a new .blend file
bpy.ops.wm.save_as_mainfile(filepath=str(output_blend_file))

print(f"Scene saved to {output_blend_file}")
