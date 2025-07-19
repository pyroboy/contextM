"""
TreePanel with Model/View architecture integration.
This provides a drop-in replacement for the existing TreePanel with dramatically better performance.
"""

import os
import time
from typing import List, Set, Optional
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
        # Clear existing tree
        self.clear_tree()
        
        # Store root path
        self.root_path = os.path.normpath(root_path).replace('\\', '/')
        
        # Populate using Model/View (this is FAST!)
        self.file_tree_view.populate_tree(items, root_path)
        
        # Expand root level
        self.file_tree_view.expand_to_depth(0)
        
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
        
    def set_checked_paths(self, paths: Set[str]):
        """Set checked state for given paths."""
        self.file_tree_view.set_checked_paths(paths)
        
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
        
    def get_aggregated_content(self):
        """Aggregates content from checked files using the specified format."""
        import pathlib
        
        aggregated_lines = []
        total_tokens = 0
        # We need absolute paths for reading files
        checked_absolute_paths = self.get_checked_paths(return_set=True, relative=False)

        for path_str in sorted(list(checked_absolute_paths)):
            path_obj = pathlib.Path(path_str)
            if not path_obj.is_file():
                continue

            try:
                # 1. Build the header line (relative path)
                relative_path_str = os.path.relpath(path_str, self.root_path)
                aggregated_lines.append(relative_path_str)

                # 2. Build the opening code-fence with language identifier
                _, file_extension = os.path.splitext(relative_path_str)
                language_identifier = file_extension.lstrip('.').lower() if file_extension else ""
                aggregated_lines.append(f"```{language_identifier}")

                # 3. Append the file's actual content
                with open(path_obj, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                
                # Sanitize content to avoid breaking the markdown block
                sanitized_content = content.replace("```", "``·")
                aggregated_lines.append(sanitized_content)

                # 4. Close the code block
                aggregated_lines.append("```")
                aggregated_lines.append("")  # Blank line between files

                # Add to total tokens from model data
                node = self.file_tree_view.model.get_node_by_path(path_str)
                if node:
                    total_tokens += node.token_count

            except Exception as e:
                aggregated_lines.append(f"[Error reading file {relative_path_str}: {e}]")
                aggregated_lines.append("")

        return "\n".join(aggregated_lines), total_tokens
        
    def _on_model_data_changed(self, top_left, bottom_right, roles):
        """Handle model data changes, especially checkbox state changes."""
        from PySide6.QtCore import Qt
        
        # Check if this was a checkbox state change
        if Qt.ItemDataRole.CheckStateRole in roles:
            # Emit the item_checked_changed signal for compatibility
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
