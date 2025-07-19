import os
import copy
import json
import hashlib
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# These were in main.py, now they are managed here.
WORKSPACE_FILE = "workspaces.json"
CUSTOM_INSTRUCTIONS_FILE = "custom_instructions.json"

# Backup Strategy Configuration
BACKUP_DIR = "backups"
MAX_BACKUPS = 5
BACKUP_RETENTION_DAYS = 7

# Global variable to hold the base path for testing
_TESTING_BASE_PATH = None

# This was in scan_config_dialog.py, moved here to avoid core -> dialogs dependency
DEFAULT_IGNORE_FOLDERS = [
    ".git", "__pycache__", ".vscode", ".idea", "node_modules", "venv",
    ".svn", "dist", "build", "target", "out", "bin", "obj","csv" ,"json"
]

def _migrate_workspaces(data):
    """Placeholder for migrating workspace data from old schemas."""
    # For now, it just handles the transition from un-versioned to v1 structure.
    if "schema_version" not in data:
        print("Migrating un-versioned workspace data to schema v1.")
        last_active = data.pop("last_active_workspace", None)
        # Find a default if last_active is not set
        if not last_active and data:
            last_active = next(iter(data))
        elif not data:
            last_active = "Default"

        return {
            "schema_version": 1,
            "workspaces": data,
            "last_active_workspace": last_active
        }
    # Future migrations would go here, e.g.:
    # if data["schema_version"] == 1:
    #     #... migrate to v2
    #     data["schema_version"] = 2
    return data

def _load_and_verify(filepath):
    """Loads a JSON file, verifies its checksum, and returns the data."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    checksum = data.pop("checksum", None)
    if not checksum:
        raise ValueError("Missing checksum.")

    # The checksum is calculated on the byte-string of the JSON dump, without the checksum field.
    # We must be careful to dump it with the same settings (indent=4) to get the same string.
    json_bytes = json.dumps(data, indent=4).encode('utf-8')
    calculated_checksum = hashlib.sha256(json_bytes).hexdigest()

    if checksum != calculated_checksum:
        raise ValueError("Checksum mismatch.")

    return data

def set_testing_mode(temp_dir):
    """Sets the base path for testing purposes."""
    global _TESTING_BASE_PATH
    _TESTING_BASE_PATH = temp_dir

def _get_instructions_file_path(base_path=None):
    """Returns the absolute path to the custom instructions file."""
    if _TESTING_BASE_PATH:
        return Path(_TESTING_BASE_PATH).resolve() / CUSTOM_INSTRUCTIONS_FILE
    if base_path:
        return Path(base_path).resolve() / CUSTOM_INSTRUCTIONS_FILE
    return Path.cwd() / CUSTOM_INSTRUCTIONS_FILE

def _get_workspace_file_path(base_path=None):
    """Returns the absolute path to the workspace file."""
    if _TESTING_BASE_PATH:
        return Path(_TESTING_BASE_PATH).resolve() / WORKSPACE_FILE
    if base_path:
        return Path(base_path).resolve() / WORKSPACE_FILE
    return Path.cwd() / WORKSPACE_FILE

def load_workspaces(base_path=None):
    """Loads workspaces from the JSON file, with integrity checks and backup fallback."""
    workspace_file_path = _get_workspace_file_path(base_path)
    # Attempt to load the primary file
    try:
        if workspace_file_path.exists():
            print(f"Loading workspaces from {workspace_file_path}")
            loaded_data = _load_and_verify(workspace_file_path)
            return _migrate_workspaces(loaded_data)
        else:
             raise FileNotFoundError
    except (FileNotFoundError, json.JSONDecodeError, ValueError, IOError, TypeError) as e:
        if isinstance(e, FileNotFoundError):
            print(f"Workspace file not found: {workspace_file_path}. Creating a default configuration.")
            return {
                "schema_version": 1,
                "workspaces": {},
                "last_active_workspace": "Default"
            }
        print(f"Could not load primary workspace file '{workspace_file_path}': {e}")
        # Attempt to restore from the backups directory
        backup_dir = workspace_file_path.parent / BACKUP_DIR
        if backup_dir.exists():
            backups = sorted(backup_dir.glob("workspaces_*.bak"), key=os.path.getmtime, reverse=True)
            for backup_file in backups:
                try:
                    print(f"Attempting to restore from backup: {backup_file}")
                    shutil.copy(backup_file, workspace_file_path)
                    loaded_data = _load_and_verify(workspace_file_path)
                    print(f"Successfully restored from backup: {backup_file}")
                    # Save the restored data to regenerate checksum and ensure consistency
                    save_workspaces(loaded_data, base_path)
                    return loaded_data
                except (ValueError, json.JSONDecodeError, IOError) as backup_e:
                    print(f"Could not restore from backup '{backup_file}': {backup_e}")
                    continue # Try the next oldest backup

        # If no valid backup is found or the backup directory doesn't exist
        print("No valid backup found. Creating a default configuration.")
        return {
            "schema_version": 1,
            "workspaces": {},
            "last_active_workspace": "Default"
        }

    # Check for schema version and migrate if necessary
    loaded_data = _migrate_workspaces(loaded_data)

    # After migration, data should be in the new format.
    workspaces_data = loaded_data.get("workspaces", {})
    last_active_workspace = loaded_data.get("last_active_workspace")

    workspaces = {}
    for ws_name, ws_data in workspaces_data.items():
        checked_paths_list = ws_data.get("checked_paths", [])
        validated_data = {
            "folder_path": ws_data.get("folder_path"),
            "scan_settings": ws_data.get("scan_settings"),
            "instructions": ws_data.get("instructions", ""),
            "checked_paths": checked_paths_list,
            "selection_groups": ws_data.get("selection_groups", {}),
            "active_selection_group": ws_data.get("active_selection_group", "Default"),
            "use_local_templates": ws_data.get("use_local_templates", False),
            "local_custom_instructions": ws_data.get("local_custom_instructions", {})
        }
        if validated_data["scan_settings"] and "ignore_folders" in validated_data["scan_settings"]:
            if isinstance(validated_data["scan_settings"]["ignore_folders"], list):
                validated_data["scan_settings"]["ignore_folders"] = set(validated_data["scan_settings"]["ignore_folders"])
            elif validated_data["scan_settings"]["ignore_folders"] is None:
                validated_data["scan_settings"]["ignore_folders"] = set(DEFAULT_IGNORE_FOLDERS)
        workspaces[ws_name] = validated_data
    
    if last_active_workspace:
        workspaces["last_active_workspace"] = last_active_workspace

    print(f"Workspaces loaded and validated from {WORKSPACE_FILE}")
    return workspaces

def _manage_backups(source_path, base_path=None):
    """Creates a timestamped backup and prunes old backups based on retention policies."""
    workspace_file_path = _get_workspace_file_path(base_path)
    backup_dir = workspace_file_path.parent / BACKUP_DIR
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"workspaces_{timestamp}.bak"
    dest_backup_path = backup_dir / backup_filename
    shutil.copy(source_path, dest_backup_path)
    print(f"Created backup: {dest_backup_path}")

    try:
        all_backups = sorted(backup_dir.glob("workspaces_*.bak"), key=os.path.getmtime, reverse=True)
        
        if len(all_backups) > MAX_BACKUPS:
            for old_backup in all_backups[MAX_BACKUPS:]:
                old_backup.unlink()
                print(f"Removed backup (limit exceeded): {old_backup}")

        retention_limit = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)
        remaining_backups = sorted(backup_dir.glob("workspaces_*.bak"), key=os.path.getmtime)
        for backup in remaining_backups:
            backup_time = datetime.fromtimestamp(backup.stat().st_mtime)
            if backup_time < retention_limit:
                backup.unlink()
                print(f"Removed backup (expired): {backup}")

    except OSError as e:
        print(f"Error pruning backups: {e}")

def save_workspaces(workspaces, base_path=None):
    """Saves the workspaces dictionary, creating a backup only if data has changed."""
    workspace_file_path = _get_workspace_file_path(base_path)

    # Deepcopy for safe manipulation
    try:
        workspaces_copy = copy.deepcopy(workspaces)
    except Exception as e:
        print(f"Error deep copying workspace data: {e}")
        return

    # Clean data for serialization (convert sets to lists)
    last_active = workspaces_copy.get("last_active_workspace", None)
    clean_workspaces = {}
    for ws_name, ws_data in workspaces_copy.get("workspaces", {}).items():
        if not isinstance(ws_data, dict):
            continue
        if isinstance(ws_data.get("checked_paths"), set):
            ws_data["checked_paths"] = sorted(list(ws_data["checked_paths"]))
        scan_settings = ws_data.get("scan_settings")
        if scan_settings and isinstance(scan_settings.get("ignore_folders"), set):
            scan_settings["ignore_folders"] = sorted(list(scan_settings["ignore_folders"]))
        clean_workspaces[ws_name] = ws_data

    data_to_save = {
        "schema_version": 1,
        "workspaces": clean_workspaces,
        "last_active_workspace": last_active
    }

    # Check if data has actually changed before saving
    try:
        existing_data = load_workspaces(base_path=base_path)
        # Normalize existing data for comparison
        if existing_data.get('workspaces'):
            for ws in existing_data['workspaces'].values():
                if 'checked_paths' in ws:
                    ws['checked_paths'] = sorted(list(set(ws.get('checked_paths', []))))
    except Exception:
        existing_data = None

    if data_to_save == existing_data:
        print("No meaningful changes detected. Skipping save and backup.")
        return

    # Add checksum
    json_bytes = json.dumps(data_to_save, indent=4).encode('utf-8')
    checksum = hashlib.sha256(json_bytes).hexdigest()
    final_data = data_to_save.copy()
    final_data['checksum'] = checksum

    # Atomic write
    temp_file_path = workspace_file_path.with_suffix('.json.tmp')
    try:
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=4)
        
        # Create backup from the temp file before moving
        _manage_backups(temp_file_path, base_path=base_path)

        shutil.move(temp_file_path, workspace_file_path)
        print(f"Workspaces saved to {workspace_file_path}")

    except (IOError, TypeError) as e:
        print(f"Error saving workspaces: {e}")




def load_custom_instructions(base_path=None):
    """Loads custom instruction templates from JSON file."""
    instructions_file = _get_instructions_file_path(base_path)
    try:
        if instructions_file.exists():
            with open(instructions_file, 'r', encoding='utf-8') as f:
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

def save_custom_instructions(instructions, base_path=None):
    """Saves custom instruction templates to JSON file."""
    instructions_file = _get_instructions_file_path(base_path)
    try:
        with open(instructions_file, 'w', encoding='utf-8') as f:
            json.dump(instructions, f, indent=4)
    except (IOError, TypeError) as e:
        print(f"Error saving custom instructions: {e}")
