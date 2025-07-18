# core/selection_manager.py

"""Data model and persistence logic for selection groups."""

from typing import Dict, Set


def load_groups(workspace_dict: dict) -> Dict[str, dict]:
    """
    Loads selection groups from the workspace data.

    If no groups are found, returns a default group.
    """
    groups = workspace_dict.get("selection_groups", {})
    if not groups:
        return {"Default": {"description": "Default selection", "checked_paths": []}}
    return groups


def save_group(workspace_dict: dict, name: str, description: str, paths: Set[str]) -> None:
    """
    Saves a selection group to the workspace data.

    The checked paths are stored as a sorted list for consistency.
    """
    if "selection_groups" not in workspace_dict:
        workspace_dict["selection_groups"] = {}

    workspace_dict["selection_groups"][name] = {
        "description": description,
        "checked_paths": sorted(list(paths)),
    }


def delete_group(workspace_dict: dict, name: str) -> None:
    """
    Deletes a selection group from the workspace data.

    The "Default" group cannot be deleted.
    """
    if name == "Default":
        # Silently ignore attempts to delete the default group
        return

    if "selection_groups" in workspace_dict:
        workspace_dict["selection_groups"].pop(name, None)
