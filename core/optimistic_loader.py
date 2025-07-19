# --- File: optimistic_loader.py ---
"""
Optimistic loading system that uses workspace metadata to quickly display
file trees while deferring expensive operations like tokenization.
"""

import os
import pathlib
from PySide6.QtCore import QObject, Signal, QTimer, QThread
from typing import List, Tuple, Dict, Set
from . import workspace_manager


class OptimisticLoader(QObject):
    """
    Loads file tree structure immediately from workspace metadata,
    then progressively updates with real-time data.
    """
    
    # Signals
    tree_structure_ready = Signal(list, str)  # items, root_path
    token_update = Signal(str, int)  # file_path, token_count
    file_validation_update = Signal(str, bool, str)  # file_path, is_valid, reason
    loading_progress = Signal(int, int)  # current, total
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._background_tokenizer = None
        self._pending_files = []
        
    def load_workspace_optimistically(self, workspace_name: str, workspaces_data: dict) -> bool:
        """
        Immediately loads file tree structure from workspace metadata.
        Returns True if successful, False if no cached data available.
        """
        import time
        start_time = time.time()
        
        print(f"[OPTIMISTIC] Checking workspace '{workspace_name}' for cached data...")
        
        if workspace_name not in workspaces_data.get('workspaces', {}):
            print(f"[OPTIMISTIC] ❌ Workspace '{workspace_name}' not found in workspaces data")
            return False
            
        workspace = workspaces_data['workspaces'][workspace_name]
        folder_path = workspace.get('folder_path', '')
        selection_groups = workspace.get('selection_groups', {})
        
        print(f"[OPTIMISTIC] Found workspace data - folder: {folder_path}, groups: {len(selection_groups)}")
        
        if not folder_path or not os.path.exists(folder_path):
            print(f"[OPTIMISTIC] ❌ Folder path invalid or doesn't exist: {folder_path}")
            return False
            
        # Get the active selection group or default
        active_group = workspace.get('active_selection_group', 'Default')
        if active_group not in selection_groups:
            active_group = list(selection_groups.keys())[0] if selection_groups else 'Default'
            
        checked_paths = selection_groups.get(active_group, {}).get('checked_paths', [])
        print(f"[OPTIMISTIC] Active group '{active_group}' has {len(checked_paths)} cached paths")
        
        # Convert checked paths to tree items format
        build_start = time.time()
        tree_items = self._build_tree_items_from_paths(folder_path, checked_paths)
        build_time = (time.time() - build_start) * 1000
        print(f"[OPTIMISTIC] Built {len(tree_items)} tree items in {build_time:.2f}ms")
        
        # Emit the tree structure immediately
        emit_start = time.time()
        self.tree_structure_ready.emit(tree_items, folder_path)
        emit_time = (time.time() - emit_start) * 1000
        print(f"[OPTIMISTIC] Emitted tree structure in {emit_time:.2f}ms")
        
        # Start background tokenization for files
        tokenize_start = time.time()
        self._start_background_tokenization(tree_items)
        tokenize_time = (time.time() - tokenize_start) * 1000
        print(f"[OPTIMISTIC] Started background tokenization in {tokenize_time:.2f}ms")
        
        total_time = (time.time() - start_time) * 1000
        print(f"[OPTIMISTIC] ✅ Optimistic loading completed in {total_time:.2f}ms")
        
        return True
        
    def _build_tree_items_from_paths(self, root_path: str, checked_paths: List[str]) -> List[Tuple]:
        """
        Builds tree items from cached workspace paths.
        Returns list of tuples: (path_str, is_dir, is_valid, reason, token_count)
        """
        root_path = os.path.normpath(root_path).replace('\\', '/')
        items = []
        all_paths = set()
        
        # Add root directory
        items.append((root_path, True, True, "", 0))
        all_paths.add(root_path)
        
        # Process each checked path
        for rel_path in checked_paths:
            if rel_path == '.':
                continue
                
            # Convert to absolute path
            abs_path = os.path.join(root_path, rel_path).replace('\\', '/')
            abs_path = os.path.normpath(abs_path).replace('\\', '/')
            
            if abs_path in all_paths:
                continue
                
            # OPTIMISTIC: Trust cached data without file system validation
            # Determine if it's a directory based on path characteristics
            is_dir = not ('.' in os.path.basename(abs_path) and len(os.path.splitext(abs_path)[1]) > 0)
            is_valid = True  # Assume valid for optimistic loading
            reason = ""
            
            # For files, we'll show "Loading..." for token count initially
            token_count = -1 if not is_dir else 0  # -1 indicates "loading"
            
            items.append((abs_path, is_dir, is_valid, reason, token_count))
            all_paths.add(abs_path)
            
            # Add parent directories if they don't exist (optimistically)
            parent_path = os.path.dirname(abs_path)
            while parent_path and parent_path != root_path and parent_path not in all_paths:
                # Optimistically assume parent directories exist
                items.append((parent_path, True, True, "", 0))
                all_paths.add(parent_path)
                parent_path = os.path.dirname(parent_path)
        
        return items
        
    def _start_background_tokenization(self, tree_items: List[Tuple]):
        """Start background tokenization for files that need token counts."""
        import time
        start_time = time.time()
        
        files_to_tokenize = []
        
        for path_str, is_dir, is_valid, reason, token_count in tree_items:
            if not is_dir and is_valid and token_count == -1:  # Files needing tokenization
                files_to_tokenize.append(path_str)
        
        print(f"[TOKENIZER] Found {len(files_to_tokenize)} files needing tokenization")
        
        if files_to_tokenize:
            self._pending_files = files_to_tokenize
            self.loading_progress.emit(0, len(files_to_tokenize))
            
            # Start background tokenizer
            tokenizer_start = time.time()
            self._background_tokenizer = BackgroundTokenizer(files_to_tokenize)
            self._background_tokenizer.token_calculated.connect(self._on_token_calculated)
            self._background_tokenizer.file_validated.connect(self._on_file_validated)
            self._background_tokenizer.finished.connect(self._on_tokenization_finished)
            self._background_tokenizer.start()
            
            tokenizer_time = (time.time() - tokenizer_start) * 1000
            total_time = (time.time() - start_time) * 1000
            print(f"[TOKENIZER] Background tokenizer started in {tokenizer_time:.2f}ms (total: {total_time:.2f}ms)")
        else:
            print(f"[TOKENIZER] No files need tokenization")
    
    def _on_token_calculated(self, file_path: str, token_count: int):
        """Handle token calculation completion for a file."""
        self.token_update.emit(file_path, token_count)
        
        # Update progress
        if file_path in self._pending_files:
            self._pending_files.remove(file_path)
            completed = len([f for f in self._background_tokenizer.files if f not in self._pending_files])
            total = len(self._background_tokenizer.files)
            self.loading_progress.emit(completed, total)
    
    def _on_file_validated(self, file_path: str, is_valid: bool, reason: str):
        """Handle file validation update."""
        self.file_validation_update.emit(file_path, is_valid, reason)
    
    def _on_tokenization_finished(self):
        """Handle completion of background tokenization."""
        self.loading_progress.emit(len(self._background_tokenizer.files), len(self._background_tokenizer.files))
        self._background_tokenizer = None
        self._pending_files = []


class BackgroundTokenizer(QThread):
    """Background thread for calculating file tokens without blocking UI."""
    
    token_calculated = Signal(str, int)  # file_path, token_count
    file_validated = Signal(str, bool, str)  # file_path, is_valid, reason
    
    def __init__(self, files: List[str], parent=None):
        super().__init__(parent)
        self.files = files
        self._should_stop = False
    
    def run(self):
        """Calculate tokens for files in background."""
        from .helpers import calculate_tokens, MAX_FILE_SIZE_BYTES
        
        for file_path in self.files:
            if self._should_stop:
                break
                
            try:
                # Check file validity first
                if not os.path.exists(file_path):
                    self.file_validated.emit(file_path, False, "File not found")
                    self.token_calculated.emit(file_path, 0)
                    continue
                
                # Check file size
                file_size = os.path.getsize(file_path)
                if file_size > MAX_FILE_SIZE_BYTES:
                    self.file_validated.emit(file_path, False, f"File too large ({file_size} bytes)")
                    self.token_calculated.emit(file_path, 0)
                    continue
                
                # Try to read and tokenize
                try:
                    with open(file_path, 'rb') as f:
                        raw_bytes = f.read(MAX_FILE_SIZE_BYTES + 1)
                    
                    content = raw_bytes[:MAX_FILE_SIZE_BYTES].decode('utf-8', errors='replace')
                    token_count = calculate_tokens(content)
                    
                    self.file_validated.emit(file_path, True, "")
                    self.token_calculated.emit(file_path, token_count)
                    
                except (UnicodeDecodeError, OSError) as e:
                    self.file_validated.emit(file_path, False, f"Read error: {str(e)}")
                    self.token_calculated.emit(file_path, 0)
                    
            except Exception as e:
                self.file_validated.emit(file_path, False, f"Error: {str(e)}")
                self.token_calculated.emit(file_path, 0)
            
            # Small delay to prevent overwhelming the system
            self.msleep(5)
    
    def stop(self):
        """Stop the tokenization process."""
        self._should_stop = True
