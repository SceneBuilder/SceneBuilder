"""Helper utilities for installing and managing Blender addons."""
# TODO: will be adding window addon soon

from pathlib import Path

import addon_utils
import bpy
from scene_builder.config import DOOR_ADDON_ZIP_PATH

from scene_builder.logging import logger


def install_door_it_addon(addon_path: str = DOOR_ADDON_ZIP_PATH) -> bool:
    """Install and enable Door It! Interior addon.

    Args:
        addon_path: Path to the Door It! Interior addon zip file

    Returns:
        True if successfully installed and enabled, False otherwise
    """
    addon_module = "DoorItInterior"

    # Check if already enabled
    if addon_utils.check(addon_module)[1]:
        logger.info(f"✓ {addon_module} addon already enabled")
        return True

    # Check if addon file exists
    addon_file = Path(addon_path)
    if not addon_file.exists():
        logger.warning(f"Door It! Interior addon not found at: {addon_path}\n")
        return False

    try:
        # Install addon
        bpy.ops.preferences.addon_install(filepath=str(addon_path))
        logger.info(f"✓ Installed Door It! Interior from {addon_path}")

        # Enable addon
        bpy.ops.preferences.addon_enable(module=addon_module)
        bpy.ops.wm.save_userpref()
        addon_utils.modules_refresh()
        logger.info(f"✓ Enabled {addon_module} addon")
        return True

    except Exception as e:
        logger.error(f"Failed to install/enable Door It! Interior addon: {e}")
        return False


def enable_door_it_addon() -> bool:
    """Enable Door It! Interior addon if already installed.

    Returns:
        True if addon is enabled, False otherwise
    """
    addon_module = "DoorItInterior"

    # Check if already enabled
    if addon_utils.check(addon_module)[1]:
        return True

    # Try to enable it
    try:
        bpy.ops.preferences.addon_enable(module=addon_module)
        addon_utils.modules_refresh()
        logger.info(f"✓ Enabled {addon_module} addon")
        return True
    except Exception as e:
        logger.debug(f"Door It! Interior addon not available: {e}")
        return False
