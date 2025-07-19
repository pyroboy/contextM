import os, pathlib

def generate_file_tree_string(current_folder_path: str, relative_paths: set) -> str:
    if not current_folder_path or not relative_paths:
        return ""
    path_tree = {}
    all_paths = set(relative_paths)
    for p in relative_paths:
        if p == '.':
            continue
        parent = pathlib.Path(p).parent
        while str(parent) != '.':
            all_paths.add(str(parent))
            parent = parent.parent
    for p in sorted(all_paths):
        if p == '.':
            continue
        parts = p.split(os.sep)
        node = path_tree
        for part in parts:
            node = node.setdefault(part, {})

    def build(subtree, prefix=""):
        lines, entries = [], sorted(subtree.keys())
        for i, name in enumerate(entries):
            last = i == len(entries) - 1
            connector = "└── " if last else "├── "
            lines.append(f"{prefix}{connector}{name}{'/' if subtree[name] else ''}")
            if subtree[name]:
                lines.extend(build(subtree[name], prefix + ("    " if last else "│   ")))
        return lines

    root = pathlib.Path(current_folder_path).name
    return "\n".join([f"{root}/"] + build(path_tree))
