import bpy
import os
from pathlib import Path

# Get the directory of the current script
script_dir = Path(os.path.dirname(os.path.realpath(__file__)))

# Path to the script to be executed
script_to_run = (script_dir / "../bpy_script/Exterior_door_bpy.py").resolve()

# Path for the output .blend file
output_blend_file = script_dir / "output.blend"

# Execute the script
exec(compile(script_to_run.read_text(), str(script_to_run), 'exec'), {'__file__': str(script_to_run)})

# Save the current scene to a new .blend file
bpy.ops.wm.save_as_mainfile(filepath=str(output_blend_file))

print(f"Scene saved to {output_blend_file}")
