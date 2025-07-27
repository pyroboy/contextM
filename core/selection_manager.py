# core/selection_manager.py

"""Data model and persistence logic for selection groups."""

import os
from typing import Dict, Set, List, Union


def load_groups(workspace_dict: dict) -> dict:
    """
    Loads selection groups from workspace data with absolute path conversion.
    
    Converts relative paths to absolute paths based on workspace root.
    Ensures Default group exists if no groups are found.
    """
    groups = workspace_dict.get("selection_groups", {})
    workspace_root = workspace_dict.get("folder_path")
    
    # Convert relative paths to absolute when loading
    if workspace_root and groups:
        for group_name, group_data in groups.items():
            absolute_paths = []
            for rel_path in group_data.get("checked_paths", []):
                try:
                    abs_path = os.path.normpath(os.path.join(workspace_root, rel_path))
                    absolute_paths.append(abs_path)
                except Exception:
                    # Fallback to original path if conversion fails
                    absolute_paths.append(rel_path)
            group_data["checked_paths"] = absolute_paths
    
    # Ensure Default group exists
    if not groups:
        return {
            "Default": {
                "description": "Default selection",
                "checked_paths": []
            }
        }
    
    return groups


def save_group(workspace_dict: dict, name: str, description: str, paths: Union[Set[str], List[str]]) -> None:
    """
    Saves a selection group to the workspace data.
    
    Paths are converted to relative paths before storage for portability.
    The checked paths are stored as a sorted list for consistency.
    """
    # Get workspace root for path conversion
    workspace_root = workspace_dict.get("folder_path")
    
    # Convert paths to relative if possible
    relative_paths = []
    if workspace_root:
        for path in paths:
            try:
                rel_path = os.path.relpath(path, workspace_root)
                # Only use relative path if it doesn't start with .. (outside workspace)
                if not rel_path.startswith('..'):
                    relative_paths.append(rel_path)
                else:
                    # Keep absolute path if it's outside workspace
                    relative_paths.append(path)
            except Exception:
                # Fallback to absolute if conversion fails
                relative_paths.append(path)
    else:
        # No workspace root, store as-is
        relative_paths = list(paths)
    
    # Ensure selection_groups exists
    if "selection_groups" not in workspace_dict:
        workspace_dict["selection_groups"] = {}
    
    # Save with relative paths
    workspace_dict["selection_groups"][name] = {
        "description": description,
        "checked_paths": sorted(list(set(relative_paths)))
    }
    
    print(f"[SELECTION] 💾 Saved group '{name}' with {len(relative_paths)} paths (relative to workspace)")


def delete_group(workspace_dict: dict, name: str) -> None:
    """
    Deletes a selection group from the workspace data.

    The "Default" group cannot be deleted.
    """
    if name == "Default":
        # Silently ignore attempts to delete the default group
        print(f"[SELECTION] ⚠️ Cannot delete Default group")
        return

    if "selection_groups" in workspace_dict:
        if name in workspace_dict["selection_groups"]:
            workspace_dict["selection_groups"].pop(name, None)
            print(f"[SELECTION] 🗑️ Deleted group '{name}'")
        else:
            print(f"[SELECTION] ⚠️ Group '{name}' not found for deletion")


def get_group_paths_absolute(workspace_dict: dict, group_name: str) -> List[str]:
    """
    Get absolute paths for a specific selection group.
    
    Converts relative paths to absolute based on workspace root.
    Returns empty list if group doesn't exist.
    """
    groups = workspace_dict.get("selection_groups", {})
    if group_name not in groups:
        return []
    
    workspace_root = workspace_dict.get("folder_path")
    relative_paths = groups[group_name].get("checked_paths", [])
    
    if not workspace_root:
        return relative_paths
    
    absolute_paths = []
    for rel_path in relative_paths:
        try:
            abs_path = os.path.normpath(os.path.join(workspace_root, rel_path))
            absolute_paths.append(abs_path)
        except Exception:
            absolute_paths.append(rel_path)
    
    return absolute_paths


def update_group_paths(workspace_dict: dict, group_name: str, paths: Union[Set[str], List[str]]) -> None:
    """
    Update paths for an existing selection group.
    
    Creates the group if it doesn't exist.
    Paths are converted to relative before storage.
    """
    # Get existing group or create new one
    groups = workspace_dict.get("selection_groups", {})
    if group_name in groups:
        description = groups[group_name].get("description", "")
    else:
        description = f"{group_name} selection"
    
    # Use save_group to handle path conversion
    save_group(workspace_dict, group_name, description, paths)
