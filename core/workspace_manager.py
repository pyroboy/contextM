import os
import json

# These were in main.py, now they are managed here.
WORKSPACE_FILE = "workspaces.json"
CUSTOM_INSTRUCTIONS_FILE = "custom_instructions.json"

# This was in scan_config_dialog.py, moved here to avoid core -> dialogs dependency
DEFAULT_IGNORE_FOLDERS = [
    ".git", "__pycache__", ".vscode", ".idea", "node_modules", "venv",
    ".svn", "dist", "build", "target", "out", "bin", "obj"
]

def load_workspaces():
    """Loads workspaces from the JSON file."""
    try:
        if os.path.exists(WORKSPACE_FILE):
            with open(WORKSPACE_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                workspaces = {}
                for ws_name, ws_data in loaded_data.items():
                    if ws_name == "last_active_workspace":
                        workspaces[ws_name] = ws_data
                        continue
                    
                    checked_paths_list = ws_data.get("checked_paths", [])
                    validated_data = {
                        "folder_path": ws_data.get("folder_path"),
                        "scan_settings": ws_data.get("scan_settings"),
                        "instructions": ws_data.get("instructions", ""),
                        "checked_paths": checked_paths_list 
                    }
                    if validated_data["scan_settings"] and "ignore_folders" in validated_data["scan_settings"]:
                        if isinstance(validated_data["scan_settings"]["ignore_folders"], list):
                            validated_data["scan_settings"]["ignore_folders"] = set(validated_data["scan_settings"]["ignore_folders"])
                        elif validated_data["scan_settings"]["ignore_folders"] is None:
                            validated_data["scan_settings"]["ignore_folders"] = set(DEFAULT_IGNORE_FOLDERS)
                    workspaces[ws_name] = validated_data
            print(f"Workspaces loaded and validated from {WORKSPACE_FILE}")
            return workspaces
        else:
            raise FileNotFoundError
    except (json.JSONDecodeError, IOError, TypeError, FileNotFoundError) as e:
        if not isinstance(e, FileNotFoundError):
            print(f"Error loading workspaces: {e}. Resetting to default.")
        else:
            print("Workspace file not found. Creating default.")
        
        default_workspaces = {
            "Default": {"folder_path": None, "scan_settings": None, "instructions": "", "checked_paths": []},
            "last_active_workspace": "Default"
        }
        save_workspaces(default_workspaces)
        return default_workspaces

def save_workspaces(workspaces):
    """Saves the workspaces dictionary to the JSON file."""
    workspaces_to_save = {}
    for ws_name, ws_data in workspaces.items():
        if ws_name == "last_active_workspace":
            workspaces_to_save[ws_name] = ws_data
            continue
        
        new_ws_data = ws_data.copy()
        
        if "checked_paths" in new_ws_data and isinstance(new_ws_data["checked_paths"], set):
             new_ws_data["checked_paths"] = sorted(list(new_ws_data["checked_paths"]))
        elif "checked_paths" not in new_ws_data:
             new_ws_data["checked_paths"] = []

        if "scan_settings" in new_ws_data and new_ws_data["scan_settings"]:
            new_ws_data["scan_settings"] = new_ws_data["scan_settings"].copy()
            if "ignore_folders" in new_ws_data["scan_settings"] and isinstance(new_ws_data["scan_settings"]["ignore_folders"], set):
                new_ws_data["scan_settings"]["ignore_folders"] = sorted(list(new_ws_data["scan_settings"]["ignore_folders"]))
        
        workspaces_to_save[ws_name] = new_ws_data
        
    try:
        with open(WORKSPACE_FILE, 'w', encoding='utf-8') as f:
            json.dump(workspaces_to_save, f, indent=4)
    except (IOError, TypeError) as e:
        print(f"Error saving workspaces: {e}")

def load_custom_instructions():
    """Loads custom instruction templates from JSON file."""
    try:
        if os.path.exists(CUSTOM_INSTRUCTIONS_FILE):
            with open(CUSTOM_INSTRUCTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            print("Custom instructions file not found. Creating default.")
            default_instructions = {
                "Default": "Instructions for the output format:\nOutput code without descriptions, unless it is important.\nMinimize prose, comments and empty lines."
            }
            save_custom_instructions(default_instructions)
            return default_instructions
    except (json.JSONDecodeError, IOError, TypeError) as e:
        print(f"Error loading custom instructions: {e}. Using default.")
        return { "Default": "Default instructions." }

def save_custom_instructions(instructions):
    """Saves custom instruction templates to JSON file."""
    try:
        with open(CUSTOM_INSTRUCTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(instructions, f, indent=4)
    except (IOError, TypeError) as e:
        print(f"Error saving custom instructions: {e}")
