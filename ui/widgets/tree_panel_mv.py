"""
TreePanel with Model/View architecture integration.
This provides a drop-in replacement for the existing TreePanel with dramatically better performance.
"""

import os
import time
from typing import List, Set, Optional, Union
from PySide6.QtCore import QTimer, Qt, Signal, QModelIndex
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from .file_tree_view import FileTreeView


class TreePanelMV(QWidget):
    """
    High-performance TreePanel using Model/View architecture.
    Drop-in replacement for the original TreePanel with the same interface.
    """
    
    # Signals (same as original TreePanel)
    root_path_changed = Signal(str)
    selection_changed = Signal()
    item_checked_changed = Signal()
    file_tokens_changed = Signal(str, int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.root_path = ""
        self._pending_restore_paths = set()
        self._setup_ui()
        
        # Performance tracking
        self._population_start_time = 0
        
    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create the high-performance file tree view
        self.file_tree_view = FileTreeView(self)
        layout.addWidget(self.file_tree_view)
        
        # Connect signals
        self.file_tree_view.root_path_changed.connect(self.root_path_changed.emit)
        self.file_tree_view.selection_changed.connect(self.selection_changed.emit)
        
        # Connect model signals for checkbox changes
        self.file_tree_view.model.dataChanged.connect(self._on_model_data_changed)
        self.file_tree_view.model.layoutChanged.connect(self._on_model_layout_changed)
        
    def show_loading(self, show: bool = True):
        """Show or hide loading indicator."""
        self.file_tree_view.show_loading(show)
        
    def clear_tree(self):
        """Clear all tree data."""
        self.file_tree_view.clear_tree()
        
    def populate_tree(self, items: List, root_path: str):
        """
        Populate tree with items from BG_scanner.
        This is the key performance improvement - Model/View architecture!
        """
        start_time = time.time()
        print(f"[TREE_PANEL] 🚀 Starting tree population with {len(items)} items")

        # Clear existing tree
        self.clear_tree()
        
        # Store root path
        self.root_path = os.path.normpath(root_path).replace('\\', '/')
        
        # Initialize token cache for direct path-to-token mapping
        self._token_cache = {}
        
        # Build token cache during population for efficient lookups
        cache_start = time.time()
        self._build_token_cache(items, root_path)
        cache_time = (time.time() - cache_start) * 1000
        print(f"[TREE_PANEL] 🏗️ Token cache built in {cache_time:.2f}ms")
        
        # Populate using Model/View (this is FAST!)
        view_start = time.time()
        self.file_tree_view.populate_tree(items, root_path)
        view_time = (time.time() - view_start) * 1000
        print(f"[TREE_PANEL] 🌳 View population took {view_time:.2f}ms")
        
        # Expand root level
        self.file_tree_view.expand_to_depth(0)
        
        # Fix #2: Selection Timing Correction - finalize tree population
        self._finalize_tree_population()
        
        total_time = (time.time() - start_time) * 1000
        print(f"[TREE_PANEL] ✅ populate_tree completed in {total_time:.2f}ms")
        
    def _finalize_tree_population(self):
        """Fix #2: Complete tree population with proper selection restoration timing."""
        print(f"[TREE] 🎯 Tree population complete - applying pending selections")
        
        # Restore pending paths after tree is fully populated
        if self._pending_restore_paths:
            print(f"[SELECT] 🔄 Restoring {len(self._pending_restore_paths)} pending paths")
            print(f"[SELECT] 📋 First 3 pending paths: {list(self._pending_restore_paths)[:3]}")
            self.set_checked_paths(self._pending_restore_paths)
            
            # Verify restoration worked
            actual_checked = self.get_checked_paths(return_set=True)
            print(f"[SELECT] ✅ Selection restoration completed - now have {len(actual_checked)} checked files")
            if actual_checked:
                print(f"[SELECT] 📋 First 3 actually checked: {list(actual_checked)[:3]}")
            
            # Clear pending paths after restoration
            self._pending_restore_paths = set()
        else:
            print(f"[SELECT] ℹ️ No pending paths to restore")
        
    def _normalize_path_for_cache(self, path: str) -> str:
        """Normalize path for consistent cache lookup."""
        try:
            # Convert to absolute path and normalize
            abs_path = os.path.abspath(path)
            # Convert to forward slashes for consistent storage/retrieval
            normalized = abs_path.replace('\\', '/')
            return normalized
        except Exception:
            return path.replace('\\', '/')
    
    def _build_token_cache(self, items: List, root_path: str):
        """Build direct token cache from BG_scanner items for efficient lookups."""
        try:
            print(f"[TOKEN_CACHE] 🏗️ Building token cache for {len(items)} items")
            cache_hits = 0
            
            for item in items:
                if len(item) >= 5:  # Ensure item has token count
                    path_str, is_dir, is_valid, reason, token_count = item[:5]
                    
                    if not is_dir and isinstance(token_count, int) and token_count > 0:
                        # Create both absolute and relative path variants
                        abs_path = os.path.join(root_path, path_str) if not os.path.isabs(path_str) else path_str
                        normalized_path = self._normalize_path_for_cache(abs_path)
                        
                        # Store in cache with normalized path
                        self._token_cache[normalized_path] = token_count
                        cache_hits += 1
            
            print(f"[TOKEN_CACHE] ✅ Built token cache with {cache_hits} entries")
            
        except Exception as e:
            print(f"[TOKEN_CACHE] ❌ Error building token cache: {e}")
            self._token_cache = {}
    
    def get_token_cache(self) -> dict:
        """Get the direct token cache for external access."""
        return getattr(self, '_token_cache', {})
        
    def get_checked_paths(self, return_set: bool = False, relative: bool = False):
        """Get list or set of checked file paths."""
        checked_paths = self.file_tree_view.get_checked_paths()

        # Convert to relative paths if requested
        if relative and self.root_path:
            relative_paths = []
            for path in checked_paths:
                try:
                    rel_path = os.path.relpath(path, self.root_path)
                    relative_paths.append(rel_path)
                except ValueError:
                    # If can't make relative, use original path
                    relative_paths.append(path)
            checked_paths = relative_paths
            
        return set(checked_paths) if return_set else checked_paths
        
    def set_checked_paths(self, paths: Union[List[str], Set[str]], relative: bool = False):
        """Set checked paths in the tree, converting to absolute if needed.
        
        Args:
            paths: List or set of file paths to check
            relative: If True, paths are relative to workspace root and need conversion
        """
        if not paths:
            return
            
        # Convert to absolute paths if needed
        absolute_paths = set()
        if relative and self.root_path:
            for rel_path in paths:
                try:
                    abs_path = os.path.normpath(os.path.join(self.root_path, rel_path))
                    absolute_paths.add(abs_path)
                except Exception:
                    # Fallback to original path if conversion fails
                    absolute_paths.add(rel_path)
        else:
            absolute_paths = set(os.path.normpath(p) for p in paths)
        
        # Update model with absolute paths
        self.file_tree_view.set_checked_paths(absolute_paths)
        
        # Expand tree to show selected paths
        if hasattr(self.file_tree_view, 'expand_to_paths'):
            self.file_tree_view.expand_to_paths(absolute_paths)
        
    def set_pending_restore_paths(self, paths):
        """Set pending restore paths (compatibility method)."""
        # Store paths for restoration after tree population
        self._pending_restore_paths = set(paths) if paths else set()
        
    def update_file_token_count(self, file_path: str, token_count: int):
        """Update token count for a specific file (compatibility method)."""
        node = self.file_tree_view.model.get_node_by_path(file_path)
        if node:
            node.token_count = token_count
            # Trigger model update
            self.file_tree_view.model.dataChanged.emit(QModelIndex(), QModelIndex())
            
    def update_file_validation(self, file_path: str, is_valid: bool, reason: str):
        """Update validation status for a specific file (compatibility method)."""
        node = self.file_tree_view.model.get_node_by_path(file_path)
        if node:
            node.is_valid = is_valid
            node.reason = reason
            # Trigger model update
            self.file_tree_view.model.dataChanged.emit(QModelIndex(), QModelIndex())
        
    def update_folder_token_display(self):
        """Update token display for all folders."""
        # Model/View handles this automatically, but we can trigger refresh
        self.file_tree_view.update_folder_token_display()
        
    def populate_tree_optimistic(self, items: List, root_path: str):
        """Optimistic tree population."""
        # Model/View is inherently optimistic!
        self.populate_tree(items, root_path)
        
    # File system event handling
    def update_from_fs_events(self, event_batch: List):
        """Handle file system events."""
        self.file_tree_view.update_from_fs_events(event_batch)
        # Keep the token cache in sync with filesystem changes to avoid
        # stale entries leaking into aggregation logic.
        if not hasattr(self, '_token_cache'):
            self._token_cache = {}

        for event in event_batch:
            try:
                action = event.get('action')
                src_path = event.get('src_path')
                if not src_path:
                    continue

                normalized_src = self._normalize_path_for_cache(src_path)

                if action in ('deleted', 'moved'):
                    # Remove any cached token entry for the old path
                    self._token_cache.pop(normalized_src, None)

                elif action == 'modified':
                    # We currently don't have an updated token count here; drop
                    # the cache entry so the next aggregation forces a refresh.
                    self._token_cache.pop(normalized_src, None)
            except Exception:
                # Cache maintenance errors should never break the UI
                continue
        
    # Compatibility methods for existing interface
    def setUpdatesEnabled(self, enabled: bool):
        """Enable/disable updates."""
        self.file_tree_view.setUpdatesEnabled(enabled)
        
    def update(self):
        """Update the view."""
        self.file_tree_view.update()
        
    def get_selected_token_count(self) -> int:
        """Get total token count for selected/checked items."""
        return self.file_tree_view.get_selected_token_count()
        
    def get_checked_paths(self, relative: bool = False, return_set: bool = False):
        """Get list of checked file paths.
        
        Args:
            relative: If True, return paths relative to root_path
                     If False, return absolute paths
            return_set: If True, return a set instead of list
        
        Returns:
            List or set of checked file paths
        """
        # Delegate to the model's get_checked_paths method
        checked_paths = self.file_tree_view.model.get_checked_paths()
        
        if not relative or not self.root_path:
            return set(checked_paths) if return_set else checked_paths
            
        # Convert to relative paths
        relative_paths = []
        for path in checked_paths:
            try:
                rel_path = os.path.relpath(path, self.root_path)
                relative_paths.append(rel_path)
            except (ValueError, OSError):
                # If relative path conversion fails, use the original path
                relative_paths.append(path)
                
        return set(relative_paths) if return_set else relative_paths
        
    def get_aggregated_content(self):
        """Aggregates content from checked files using the specified format."""
        # Get checked paths (now O(1) thanks to caching)
        checked_absolute_paths = self.get_checked_paths(return_set=True, relative=False)
        
        if not checked_absolute_paths:
            return "", 0
        
        # Pre-allocate list with estimated size for better performance
        aggregated_parts = []
        total_tokens = 0
        
        # Pre-compute root path for relative path calculations
        root_path_normalized = os.path.normpath(self.root_path)
        
        # Get model reference once to avoid repeated attribute lookups
        model = self.file_tree_view.model
        
        # Process files in sorted order
        for path_str in sorted(checked_absolute_paths):
            try:
                # Quick file existence check without creating Path object
                if not os.path.isfile(path_str):
                    continue
                
                # Calculate relative path once
                try:
                    relative_path_str = os.path.relpath(path_str, root_path_normalized)
                except ValueError:
                    # Fallback if relpath fails (different drives on Windows)
                    relative_path_str = os.path.basename(path_str)
                
                # Get file extension for language identifier
                file_extension = os.path.splitext(relative_path_str)[1]
                language_identifier = file_extension[1:].lower() if file_extension else ""
                
                # Read file content with size limit for performance
                try:
                    # Check file size before reading to avoid memory issues
                    file_size = os.path.getsize(path_str)
                    if file_size > 10 * 1024 * 1024:  # 10MB limit
                        content = f"[File too large: {file_size:,} bytes - skipped for performance]"
                    else:
                        with open(path_str, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()
                        
                        # Only sanitize if content contains backticks (performance optimization)
                        if '```' in content:
                            content = content.replace("```", "``·")
                except (OSError, IOError) as e:
                    content = f"[Error reading file: {e}]"
                
                # Build file section efficiently
                file_section = f"{relative_path_str}\n```{language_identifier}\n{content}\n```\n\n"
                aggregated_parts.append(file_section)
                
                # Get token count from cached model data (O(1) lookup)
                node = model.get_node_by_path(path_str)
                if node:
                    total_tokens += node.token_count
                    
            except Exception as e:
                # Handle any unexpected errors gracefully
                error_section = f"[Error processing file {path_str}: {e}]\n\n"
                aggregated_parts.append(error_section)
        
        # Join all parts at once for better performance than multiple appends
        aggregated_content = "".join(aggregated_parts)
        
        return aggregated_content, total_tokens
        
    def _on_model_data_changed(self, top_left, bottom_right, roles):
        """Handle model data changes, especially checkbox state changes."""
        from PySide6.QtCore import Qt
        
        # Check if this was a checkbox state change
        if Qt.ItemDataRole.CheckStateRole in roles:
            # Emit the item_checked_changed signal for compatibility
            self.item_checked_changed.emit()

    def _on_model_layout_changed(self):
        """Handle model layout changes (bulk updates) as checked changes."""
        # Layout changes often imply bulk checkbox updates or structure changes
        # that affect selection, so we trigger the checked changed signal.
        self.item_checked_changed.emit()
            
    def _log_selected_files(self):
        """Log currently selected files and all checked files from the model perspective."""
        try:
            print("[SELECTION STATUS] ====================================")
            
            # 1. Log currently selected files with improved detection
            selection_model = self.file_tree_view.tree_view.selectionModel()
            selected_files = []
            
            if selection_model:
                # Get all selected indexes (Qt can have multiple selections)
                selected_indexes = selection_model.selectedIndexes()
                
                # Use a set to avoid duplicates from multiple columns
                unique_nodes = set()
                for index in selected_indexes:
                    if index.isValid() and index.column() == 0:  # Only first column
                        node = index.internalPointer()
                        if node and hasattr(node, 'path') and node.path:
                            unique_nodes.add(node)
                
                # Convert to relative paths for clean output
                for node in unique_nodes:
                    if self.root_path and node.path.startswith(self.root_path):
                        try:
                            relative_path = os.path.relpath(node.path, self.root_path)
                            # Handle root directory case
                            if relative_path == '.':
                                relative_path = '[ROOT]'
                            selected_files.append(relative_path)
                        except ValueError:
                            # Fallback if relpath fails
                            selected_files.append(node.path)
                    else:
                        selected_files.append(node.path)
            
            # Sort for consistent output
            selected_files.sort()
            
            if selected_files:
                print(f"[SELECTION STATUS] Currently SELECTED ({len(selected_files)}):")
                for file_path in selected_files:
                    print(f"  ▶ {file_path}")
            else:
                print("[SELECTION STATUS] No files currently selected")
            
            # 2. Log all checked files (checkbox propagation)
            try:
                checked_paths = self.get_checked_paths(return_set=False, relative=True)
                if checked_paths:
                    # Sort for consistent output
                    checked_paths_sorted = sorted(checked_paths)
                    print(f"[SELECTION STATUS] All CHECKED ({len(checked_paths_sorted)}):")
                    for file_path in checked_paths_sorted:
                        print(f"  ✓ {file_path}")
                else:
                    print("[SELECTION STATUS] No files currently checked")
            except Exception as e:
                print(f"[SELECTION STATUS] Error getting checked paths: {e}")
                
            print("[SELECTION STATUS] ====================================")
                
        except Exception as e:
            print(f"[SELECTION STATUS] Error logging files: {e}")
            
    # Properties for compatibility
    @property
    def tree_widget(self):
        """Get the underlying tree widget (for compatibility)."""
        return self.file_tree_view.get_tree_widget()
        
    def expandToDepth(self, depth: int):
        """Expand tree to specified depth (compatibility method)."""
        self.file_tree_view.expand_to_depth(depth)


# Factory function for easy migration
def create_tree_panel(use_model_view: bool = True, parent=None):
    """
    Factory function to create either the old TreePanel or new Model/View TreePanel.
    This allows for easy A/B testing and gradual migration.
    """
    if use_model_view:
        return TreePanelMV(parent)
    else:
        # Import here to avoid circular imports
        from .tree_panel import TreePanel
        return TreePanel(parent)
