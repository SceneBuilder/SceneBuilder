import math
import random
from typing import Dict, Iterable, Optional, Sequence, Tuple

import bpy
from mathutils import Vector


def _iter_interface_items(items: Iterable) -> Iterable:
    """Yield every item (including nested panel items) from a Geometry Nodes interface."""
    for item in items:
        yield item
        children = getattr(item, "items_tree", None)
        if children:
            yield from _iter_interface_items(children)


def _view3d_context_override() -> Dict[str, object]:
    """Return a context override suitable for running VIEW3D operators."""
    wm = bpy.context.window_manager
    if wm is None:
        raise RuntimeError("No WindowManager available to override context.")

    for window in wm.windows:
        screen = window.screen
        scene = window.scene
        view_layer = window.view_layer
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return {
                            "window": window,
                            "screen": screen,
                            "area": area,
                            "region": region,
                            "scene": scene,
                            "view_layer": view_layer,
                        }

    raise RuntimeError("Could not find a VIEW_3D area to override the context for the Window operator.")


# Window type base actual widths: actual_width = base_actual + (input_width - BASE_INPUT_WIDTH) * WIDTH_SCALE_FACTOR
# Based on empirical measurements where input Width = 0.410 corresponds to these base actual widths
# Linear relationship: actual width increases by 0.09m when input width increases by 0.1m
WINDOW_WIDTH_BASE = {
    1: 0.585,  # base actual width when input = 0.410
    2: 0.585,  # base actual width when input = 0.410
    3: 0.585,  # base actual width when input = 0.410
    4: 0.585,  # base actual width when input = 0.410
    5: 0.755,  # base actual width when input = 0.410
    6: 0.809,  # base actual width when input = 0.410
    7: 0.935,  # base actual width when input = 0.410
    8: 0.935,  # base actual width when input = 0.410
}
BASE_INPUT_WIDTH = 0.410  # The input width corresponding to base actual widths
WIDTH_SCALE_FACTOR = 0.9  # Slope: actual_width change / input_width change (0.09m / 0.1m)


class WindowController:
    """Convenience wrapper for adjusting Window Geometry Nodes parameters."""

    def __init__(self, obj: Optional[bpy.types.Object] = None, modifier_name: str = "GeometryNodes"):
        self.object = obj or bpy.context.object
        if self.object is None:
            raise ValueError("No active object found. Pass an object explicitly or select one in the viewport.")
        self.modifier = self._resolve_modifier(modifier_name)
        self._socket_cache: Dict[str, bpy.types.Property] = {}

    def _resolve_modifier(self, preferred_name: str) -> bpy.types.NodesModifier:
        if preferred_name in self.object.modifiers:
            mod = self.object.modifiers[preferred_name]
            if mod.type == 'NODES':
                return mod
        for mod in self.object.modifiers:
            if mod.type == 'NODES':
                return mod
        raise ValueError(f"No Geometry Nodes modifier found on object '{self.object.name}'.")

    def _get_interface_item(self, label: str):
        if label in self._socket_cache:
            return self._socket_cache[label]

        interface = self.modifier.node_group.interface
        for item in _iter_interface_items(interface.items_tree):
            if getattr(item, "name", None) == label and hasattr(item, "identifier"):
                self._socket_cache[label] = item
                return item

        raise KeyError(f"Socket labeled '{label}' not found on modifier '{self.modifier.name}'.")

    def _get_window_type(self) -> int:
        """Get the current window type from the modifier.
        
        Returns:
            The window type as an integer (1-8).
            
        Raises:
            KeyError: If the Type socket is not found.
        """
        item = self._get_interface_item("Type")
        window_type = int(self.modifier[item.identifier])
        return window_type

    def _set_numeric(self, label: str, value: float) -> float:
        item = self._get_interface_item(label)
        min_value = getattr(item, "min_value", None)
        max_value = getattr(item, "max_value", None)

        numeric_value = float(value)
        if min_value is not None:
            numeric_value = max(numeric_value, float(min_value))
        if max_value is not None:
            numeric_value = min(numeric_value, float(max_value))

        self.modifier[item.identifier] = numeric_value
        return numeric_value

    def _set_int(self, label: str, value: int) -> int:
        item = self._get_interface_item(label)
        int_value = int(value)
        min_value = getattr(item, "min_value", None)
        max_value = getattr(item, "max_value", None)

        if min_value is not None:
            int_value = max(int_value, int(min_value))
        if max_value is not None:
            int_value = min(int_value, int(max_value))

        self.modifier[item.identifier] = int_value
        return int_value

    def _set_bool(self, label: str, value: bool) -> bool:
        """Set a boolean value."""
        item = self._get_interface_item(label)
        bool_value = bool(value)
        self.modifier[item.identifier] = bool_value
        return bool_value

    def _randomize_int(self, label: str) -> int:
        item = self._get_interface_item(label)
        min_value = int(getattr(item, "min_value", 0))
        max_value_attr = getattr(item, "max_value", None)
        if max_value_attr is None:
            max_value = min_value
        else:
            max_value = int(max_value_attr)
        choice = random.randint(min_value, max_value)
        self.modifier[item.identifier] = choice
        return choice

    def set_width(self, value: float) -> float:
        """Set the window width socket in meters (true world width). Returns the applied value.
        
        The GeometryNodes "Width" input has a linear relationship with actual width:
        actual_width = base_actual + (input_width - BASE_INPUT_WIDTH) * WIDTH_SCALE_FACTOR
        
        Each window type has a different base actual width but the same scale factor (0.9).
        This method reverses the formula to calculate the required input width.
        
        Args:
            value: Desired actual window width in meters.
            
        Returns:
            The applied Width input value (after corrections).
            
        Raises:
            ValueError: If window type is invalid or not found in WINDOW_WIDTH_BASE.
        """
        # Get current window type
        window_type = self._get_window_type()
        
        # Look up base actual width for this window type
        if window_type not in WINDOW_WIDTH_BASE:
            raise ValueError(
                f"Invalid window type: {window_type}. Valid types are 1-8."
            )
        
        base_actual = WINDOW_WIDTH_BASE[window_type]
        
        # Formula: actual_width = base_actual + (input_width - BASE_INPUT_WIDTH) * WIDTH_SCALE_FACTOR
        # Solving for input_width:
        # input_width = BASE_INPUT_WIDTH + (actual_width - base_actual) / WIDTH_SCALE_FACTOR
        # where value = actual_width (desired actual width)
        input_width = BASE_INPUT_WIDTH + (value - base_actual) / WIDTH_SCALE_FACTOR
        
        if input_width < 0.1:
            input_width = 0.1  # safety clamp

        applied = self._set_numeric("Width", input_width)
        return applied

    def set_height(self, value: float) -> float:
        """Set the window height socket in meters (true world height). Returns the applied value."""
        # Convert from real height to GeometryNodes internal height
        # Empirical offset: Window It addon adds approximately 0.2m to the height parameter
        corrected_value = value - 0.2  # empirical offset
        if corrected_value < 0.1:
            corrected_value = 0.1  # safety clamp
        applied = self._set_numeric("Height", corrected_value)
        return applied

    def set_type(self, value: int) -> int:
        """Set the style/type index. Returns the applied integer value."""
        return self._set_int("Type", value)

    def randomize_type(self) -> int:
        """Pick a random valid style index and apply it."""
        return self._randomize_int("Type")

    def set_open_1(self, value: float) -> float:
        """Set the first opening amount. Returns the applied value."""
        return self._set_numeric("Open 1", value)

    def set_open_2(self, value: float) -> float:
        """Set the second opening amount. Returns the applied value."""
        return self._set_numeric("Open 2", value)

    def set_material(self, value: int) -> int:
        """Set the material index."""
        return self._set_int("Material", value)

    def randomize_material(self) -> int:
        """Pick a random valid material index and apply it."""
        return self._randomize_int("Material")

    def set_colour(self, color: Sequence[float]) -> Tuple[float, float, float, float]:
        """Set the RGBA colour. Returns the applied color tuple."""
        item = self._get_interface_item("Colour")
        if len(color) not in (3, 4):
            raise ValueError("Colour must have 3 (RGB) or 4 (RGBA) components.")

        rgba = tuple(float(c) for c in color[:4])
        if len(rgba) == 3:
            rgba = (*rgba, 1.0)

        self.modifier[item.identifier] = rgba
        return rgba

    def randomize_colour(self, alpha: float = 1.0) -> Tuple[float, float, float, float]:
        """Assign a random RGB colour with the given alpha."""
        rgba = (random.random(), random.random(), random.random(), float(alpha))
        self.set_colour(rgba)
        return rgba

    def set_flip(self, value: bool) -> bool:
        """Set the flip state. Returns the applied boolean value."""
        return self._set_bool("Flip", value)


def apply_window_settings(
    width: Optional[float] = None,
    height: Optional[float] = None,
    window_type: Optional[int] = None,
    randomize_type: bool = True,
    open_1: Optional[float] = None,
    open_2: Optional[float] = None,
    material: Optional[int] = None,
    randomize_material: bool = True,
    colour: Optional[Sequence[float]] = None,
    randomize_colour: bool = True,
    alpha: float = 1.0,
    flip: Optional[bool] = None,
    obj: Optional[bpy.types.Object] = None,
    modifier_name: str = "GeometryNodes",
    trigger_rebuild: bool = True,
) -> Dict[str, object]:
    """Apply a batch of settings to the Window Geometry Nodes modifier.

    Returns a dictionary summarizing the values that were applied. If ``trigger_rebuild`` is
    ``True`` the object's dependency graph is updated so the viewport reflects the changes.
    """
    controller = WindowController(obj=obj, modifier_name=modifier_name)
    results: Dict[str, object] = {"object": controller.object.name}

    if window_type is not None:
        results["type"] = controller.set_type(window_type)
    elif randomize_type:
        results["type"] = controller.randomize_type()

    # Now set width and height (width calculation depends on window type)
    if width is not None:
        results["width"] = controller.set_width(width)
    if height is not None:
        results["height"] = controller.set_height(height)

    if open_1 is not None:
        results["open_1"] = controller.set_open_1(open_1)
    if open_2 is not None:
        results["open_2"] = controller.set_open_2(open_2)

    if material is not None:
        results["material"] = controller.set_material(material)
    elif randomize_material:
        results["material"] = controller.randomize_material()

    if colour is not None:
        results["colour"] = controller.set_colour(colour)
    elif randomize_colour:
        results["colour"] = controller.randomize_colour(alpha=alpha)

    if flip is not None:
        results["flip"] = controller.set_flip(flip)

    if trigger_rebuild:
        obj = controller.object
        data_block = getattr(obj, "data", None)
        if data_block is not None:
            try:
                data_block.update()
            except AttributeError:
                # Not all data-blocks implement update; ignore if unavailable.
                pass

        try:
            obj.update_tag(refresh={"OBJECT", "DATA"})
        except TypeError:
            obj.update_tag()

        view_layer = bpy.context.view_layer
        if view_layer is not None:
            view_layer.update()

    return results


def create_window(
    name: str,
    location: Sequence[float],
    rotation_angle: float = 0.0,
    width: Optional[float] = None,
    height: Optional[float] = None,
    depth: Optional[float] = None,
    window_type: Optional[int] = None,
    randomize_type: bool = False,
    open_1: Optional[float] = None,
    open_2: Optional[float] = None,
    material: Optional[int] = None,
    randomize_material: bool = False,
    colour: Optional[Sequence[float]] = None,
    randomize_colour: bool = False,
    alpha: float = 1.0,
    flip: Optional[bool] = None,
    modifier_name: str = "GeometryNodes",
    trigger_rebuild: bool = True,
) -> Dict[str, object]:
    """Create a new Window object at ``location`` and configure its parameters.

    If an object with ``name`` already exists in the blend file but is not part of the active
    scene it will be linked in, moved to ``location`` and have the requested settings applied.
    If it is already present in the scene the call becomes a no-op.
    """
    scene = bpy.context.scene
    if scene is None:
        raise RuntimeError("No active scene available to create the window.")

    if len(location) != 3:
        raise ValueError("Location must be a 3-component iterable (x, y, z).")

    location_vec = Vector(location)

    existing_obj = bpy.data.objects.get(name)
    if existing_obj is not None:
        in_scene = existing_obj.name in scene.objects
        if not in_scene:
            scene.collection.objects.link(existing_obj)
            existing_obj.location = location_vec
            settings_summary = apply_window_settings(
                width=width,
                height=height,
                window_type=window_type,
                randomize_type=randomize_type,
                open_1=open_1,
                open_2=open_2,
                material=material,
                randomize_material=randomize_material,
                colour=colour,
                randomize_colour=randomize_colour,
                alpha=alpha,
                flip=flip,
                obj=existing_obj,
                modifier_name=modifier_name,
                trigger_rebuild=trigger_rebuild,
            )
            return {
                "object": existing_obj.name,
                "created": False,
                "linked": True,
                "settings": settings_summary,
            }
        return {"object": existing_obj.name, "created": False, "linked": False}

    cursor = scene.cursor
    previous_cursor_location = cursor.location.copy()
    pre_existing_objects = set(bpy.data.objects)

    try:
        cursor.location = location_vec
        try:
            override = _view3d_context_override()
        except RuntimeError:
            override = None

        if override:
            with bpy.context.temp_override(**override):
                result = bpy.ops.windowit.add_window()
        else:
            result = bpy.ops.windowit.add_window()

        if result != {'FINISHED'}:
            raise RuntimeError(f"Window creation operator returned {result!r}.")
    finally:
        cursor.location = previous_cursor_location

    new_objects = [obj for obj in bpy.data.objects if obj not in pre_existing_objects]
    if not new_objects:
        raise RuntimeError("Window creation operator did not add any objects to the scene.")

    window_object = None
    for obj in new_objects:
        if any(mod.type == 'NODES' for mod in obj.modifiers):
            window_object = obj
            break

    if window_object is None:
        for obj in new_objects:
            if "Window" in obj.name or "window" in obj.name.lower():
                window_object = obj
                break

    if window_object is None:
        raise RuntimeError(
            "Could not locate the Window object with a Geometry Nodes modifier among created objects."
        )

    window_object.location = location_vec
    window_object.name = name

    settings_summary = apply_window_settings(
        width=width,
        height=height,
        window_type=window_type,
        randomize_type=randomize_type,
        open_1=open_1,
        open_2=open_2,
        material=material,
        randomize_material=randomize_material,
        colour=colour,
        randomize_colour=randomize_colour,
        alpha=alpha,
        flip=flip,
        obj=window_object,
        modifier_name=modifier_name,
        trigger_rebuild=trigger_rebuild,
    )

    if depth is not None:
        window_object.dimensions.x = depth
    bpy.context.view_layer.update()

    empty_name = f"Window_Controller_{name}_Arrow"

    #  Calculate bottom-center of the window using bounding box
    bbox = [window_object.matrix_world @ Vector(corner) for corner in window_object.bound_box]
    min_z = min(v.z for v in bbox)
    avg_x = sum(v.x for v in bbox) / len(bbox)
    avg_y = sum(v.y for v in bbox) / len(bbox)
    empty_initial_location = (avg_x, avg_y, min_z)

    #  Create empty at window's bottom-center
    bpy.ops.object.empty_add(type='ARROWS', location=empty_initial_location)
    empty_obj = bpy.context.active_object
    empty_obj.name = empty_name
    empty_obj.empty_display_size = 1.5

    #  Parent the window to the empty
    window_object.select_set(True)
    empty_obj.select_set(True)
    bpy.context.view_layer.objects.active = empty_obj
    bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)

    #  Move empty to window_boundary centroid (window moves with it due to parenting)
    empty_obj.location = location_vec

    #  Apply rotation to empty
    rotation_z = math.radians(rotation_angle)
    empty_obj.rotation_euler.z = rotation_z
    bpy.context.view_layer.update()

    return {
        "object": window_object.name,
        "controller": empty_name,
        "created": True,
        "settings": settings_summary,
    }


if __name__ == "__main__":
    # Example usage: tweak values here and run the script from Blender's text editor.
    SETTINGS = {
        "width": 1.2,              # meters
        "height": 1.5,             # meters
        "window_type": None,       # Set to an int to force a style, or keep None to randomize
        "randomize_type": True,    # Ignored when 'window_type' is provided
        "open_1": None,            # First opening amount; None to leave unchanged
        "open_2": None,            # Second opening amount; None to leave unchanged
        "material": None,          # Material preset index; None to randomize
        "randomize_material": True,
        "colour": None,            # Provide (R, G, B[, A]) or leave None to randomize
        "randomize_colour": True,  # Ignored when 'colour' is provided
        "alpha": 1.0,              # Alpha channel for randomized colours
        "flip": None,              # Boolean flip state; None to leave unchanged
        "modifier_name": "GeometryNodes",
        "trigger_rebuild": True,   # Forces a depsgraph update after applying settings
    }

    NEW_WINDOW = {
        "name": "Window_Example",
        "location": (0.0, 0.0, 0.0),
        "rotation_angle": 0.0,

        **SETTINGS,
    }

    created = create_window(**NEW_WINDOW)
    print("Create window summary:", created)

    if created["created"] is False and bpy.data.objects.get(created["object"]):
        # Optionally re-run settings on the already existing window.
        applied = apply_window_settings(obj=bpy.data.objects[created["object"]], **SETTINGS)
        print("Updated existing Window settings:", applied)

