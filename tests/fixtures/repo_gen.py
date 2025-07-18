import os
import pathlib

def create_test_repo(base_path, structure, ignored_folders=None, hidden_files=None):
    """
    Creates a temporary directory structure for testing.

    Args:
        base_path (pathlib.Path): The root directory to create the structure in.
        structure (dict): A dictionary representing the file structure.
                          Keys are filenames/dirnames, values are content (for files)
                          or another dict (for subdirectories).
        ignored_folders (list, optional): A list of folder names to create that
                                          would typically be ignored. Defaults to None.
        hidden_files (list, optional): A list of hidden file names to create.
                                       Defaults to None.
    Returns:
        pathlib.Path: The path to the created root directory.
    """
    repo_root = base_path / "test_repo"
    os.makedirs(repo_root, exist_ok=True)

    _create_structure(repo_root, structure)

    if ignored_folders:
        for folder in ignored_folders:
            os.makedirs(repo_root / folder, exist_ok=True)
            (repo_root / folder / ".placeholder").touch()

    if hidden_files:
        for file in hidden_files:
            (repo_root / file).touch()

    return repo_root

def _create_structure(current_path, structure):
    """Recursively creates files and directories."""
    for name, content in structure.items():
        path = current_path / name
        if isinstance(content, dict):
            os.makedirs(path, exist_ok=True)
            _create_structure(path, content)
        elif isinstance(content, str):
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            path.touch()
