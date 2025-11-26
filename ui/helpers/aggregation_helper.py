from PySide6.QtCore import QObject, Signal
import os
import pathlib

def generate_file_tree_string(current_folder_path: str, relative_paths: set) -> str:
    """Generate a file tree representation from a set of relative paths."""
    path_tree = {}
    for rel_path in relative_paths:
        parts = pathlib.Path(rel_path).parts
        d = path_tree
        for part in parts:
            d = d.setdefault(part, {})
    
    def build(node, indent=0):
        lines = []
        items = sorted(node.items(), key=lambda x: (bool(x[1]), x[0]))
        for i, (name, children) in enumerate(items):
            is_last = (i == len(items) - 1)
            prefix = "└── " if is_last else "├── "
            suffix = "/" if children else ""
            lines.append(" " * (indent * 4) + prefix + name + suffix)
            if children:
                child_lines = build(children, indent + 1)
                lines.extend(child_lines)
        return lines
    
    root_name = pathlib.Path(current_folder_path).name
    return "\n".join([f"{root_name}/"] + build(path_tree))



class AggregationWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)
    progress_update = Signal(int, int)  # current_file, total_files
    token_update = Signal(int)          # current_token_count

    # List of binary extensions to explicitly skip
    BINARY_EXTENSIONS = {'.DS_Store', '.pyc', '.git', '.bin', '.exe', '.dll', '.so', '.dylib'}

    def __init__(self, file_paths, mode='xml'):
        super().__init__()
        self.file_paths = file_paths
        self.mode = mode
        self.is_running = True

    def run(self):
        chunks = []
        current_chunk_content = []
        current_chunk_size = 0
        total_tokens = 0
        
        # Internal chunk limit (~500k chars) to prevent memory spikes
        CHUNK_SIZE_LIMIT = 500000 

        total_files = len(self.file_paths)
        
        for i, file_path in enumerate(self.file_paths):
            if not self.is_running:
                break
                
            self.progress_update.emit(i + 1, total_files)
            
            # 1. Binary File Check
            filename = os.path.basename(file_path)
            _, ext = os.path.splitext(filename)
            
            if filename in self.BINARY_EXTENSIONS or ext in self.BINARY_EXTENSIONS:
                print(f"[AGG_WORKER] ⏭️ Skipping binary file: {filename}")
                continue
            
            try:
                # 2. Read & Sanitize
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                    
                # CRITICAL FIX: Strip Null Bytes (\x00)
                if '\x00' in content:
                    # Log if we are stripping null bytes for verification
                    null_count = content.count('\x00')
                    if null_count > 0:
                        print(f"[AGG_WORKER] ⚠️ Found {null_count} null bytes in {filename}. Cleaning...")
                    content = content.replace('\x00', '')
                
                formatted_content = self._format_content(file_path, content)
                content_len = len(formatted_content)
                
                # 3. Token Estimate (4 chars ~= 1 token)
                estimated_tokens = content_len // 4
                total_tokens += estimated_tokens
                self.token_update.emit(total_tokens)

                # 4. Internal Chunking
                if current_chunk_size + content_len > CHUNK_SIZE_LIMIT:
                    chunks.append("".join(current_chunk_content))
                    current_chunk_content = []
                    current_chunk_size = 0
                
                current_chunk_content.append(formatted_content)
                current_chunk_size += content_len
                
            except Exception as e:
                print(f"[AGG_WORKER] ❌ Error reading {file_path}: {e}")
                continue

        # Flush remaining content
        if current_chunk_content:
            chunks.append("".join(current_chunk_content))

        self.finished.emit({
            "chunks": chunks,
            "total_tokens": total_tokens,
            "file_count": total_files
        })

    def _format_content(self, path, content):
        if self.mode == 'markdown':
            return f"\n## File: {path}\n```\n{content}\n```\n"
        else:  # XML default
            return f"\n<file path=\"{path}\">\n{content}\n</file>\n"

    def stop(self):
        self.is_running = False
