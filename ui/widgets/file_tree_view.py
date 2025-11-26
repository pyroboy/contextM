"""
High-performance file tree view using Qt's Model/View architecture.
Replaces QTreeWidget for scalable performance with large file trees.
"""

import os
import time
from typing import List, Optional, Set
from PySide6.QtCore import QTimer, Qt, Signal, QModelIndex
from PySide6.QtWidgets import QTreeView, QWidget, QVBoxLayout, QLabel, QHeaderView
from PySide6.QtGui import QFont

from ..models.file_tree_model import FileTreeModel, TreeNode


class FileTreeView(QWidget):
    """
    High-performance file tree view widget using Model/View architecture.
    Provides the same functionality as TreePanel but with dramatically better performance.
    """
    
    # Signals
    root_path_changed = Signal(str)
    selection_changed = Signal()
    
    def __init__(self, parent=None):
        """Initialize the file tree view."""
        super().__init__(parent)
        self.root_path = ""
        self._ignore_next_checkbox_signal = False  # Flag to ignore checkbox signals from expansion clicks
        
        # Set size policy for the widget to expand and fill available space
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self._setup_ui()
        self._setup_model()
        
    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create tree view
        self.tree_view = QTreeView()
        self.tree_view.setAlternatingRowColors(True)
        self.tree_view.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)
        self.tree_view.setUniformRowHeights(True)  # Performance optimization
        self.tree_view.setSortingEnabled(False)  # We handle sorting in model
        
        # Ensure expansion arrows are visible and functional
        self.tree_view.setRootIsDecorated(True)  # Show expansion arrows
        self.tree_view.setItemsExpandable(True)  # Allow expansion
        self.tree_view.setExpandsOnDoubleClick(True)  # Double-click to expand
        
        # Set size policy to expand and fill available space
        from PySide6.QtWidgets import QSizePolicy
        self.tree_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Enable checkbox interaction - checkboxes should work by default with ItemIsUserCheckable
        # But we need to ensure the view can handle checkbox state changes
        # Use CurrentChanged trigger which should work for checkboxes
        self.tree_view.setEditTriggers(QTreeView.EditTrigger.CurrentChanged)
        
        # Configure header for proper width stretching
        header = self.tree_view.header()
        header.setStretchLastSection(True)  # Stretch the last section to fill remaining space
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Name column stretches
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Tokens column fits content
        
        # Ensure header takes full width
        header.setDefaultSectionSize(200)  # Minimum width for name column
        header.setMinimumSectionSize(100)  # Minimum section size
        
        # Loading label
        self.loading_label = QLabel("Loading...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("color: gray; font-style: italic;")
        self.loading_label.hide()
        
        layout.addWidget(self.tree_view)
        layout.addWidget(self.loading_label)
        
    def _setup_model(self):
        """Initialize the tree model."""
        self.model = FileTreeModel(self)
        self.tree_view.setModel(self.model)
        
        # Connect signals
        self.tree_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        
        # Override mouse press event to log clicks
        self.tree_view.mousePressEvent = self._on_mouse_press
        
    def _on_selection_changed(self, selected, deselected):
        """Handle selection changes in the tree view."""
        self.selection_changed.emit()
        
    def _on_mouse_press(self, event):
        """Memory-efficient mouse press handler with precise click area detection."""
        from PySide6.QtWidgets import QTreeView, QStyle
        from PySide6.QtCore import Qt
        
        # Get the index at the click position
        index = self.tree_view.indexAt(event.pos())
        
        if not index.isValid() or index.column() != 0:
            # Not a valid item or not in the first column - use default behavior
            QTreeView.mousePressEvent(self.tree_view, event)
            return
            
        node = index.internalPointer()
        rect = self.tree_view.visualRect(index)
        click_x = event.pos().x()
        
        # Calculate precise click areas (memory-efficient - no temporary objects)
        expansion_area_end = rect.left() + 16  # Standard Qt expansion arrow width
        checkbox_area_start = rect.left() + 20  # Checkbox typically starts after expansion
        checkbox_area_end = checkbox_area_start + 16  # Standard checkbox width
        
        # Determine click area with precise boundaries
        if node.is_dir and node.children and click_x < expansion_area_end:
            # Click on expansion arrow - let Qt handle it
            QTreeView.mousePressEvent(self.tree_view, event)
            return
            
        elif checkbox_area_start <= click_x <= checkbox_area_end:
            # Precise checkbox click - toggle state
            self._toggle_checkbox_efficiently(index, node)
            return
            
        else:
            # Click on filename or other area - use default selection behavior
            QTreeView.mousePressEvent(self.tree_view, event)
            return
    
    def _toggle_checkbox_efficiently(self, index, node):
        """Memory-efficient checkbox toggle that handles tri-state logic correctly."""
        from PySide6.QtCore import Qt

        current_state = node.check_state

        # Clicking a folder toggles between checked and unchecked.
        # A partially checked folder becomes fully checked on click.
        if current_state == Qt.CheckState.Checked:
            new_state = Qt.CheckState.Unchecked
        else: # Unchecked or PartiallyChecked
            new_state = Qt.CheckState.Checked

        # Update model data. The model will handle all propagation.
        self.model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
        
    def show_loading(self, show: bool = True):
        """Show or hide loading indicator."""
        if show:
            self.tree_view.hide()
            self.loading_label.show()
        else:
            self.loading_label.hide()
            self.tree_view.show()
            
    def clear_tree(self):
        """Clear all tree data."""
        self.model.clear()
        
    def populate_tree(self, items: List, root_path: str):
        """
        Populate tree with items from BG_scanner.
        This is the key performance improvement - direct model population.
        """
        start_time = time.time()
        print(f"[TREE_VIEW] 🚀 Starting Model/View tree population with {len(items)} items")
        
        # Store root path
        self.root_path = os.path.normpath(root_path).replace('\\', '/')
        
        # Populate model directly (this is FAST!)
        model_start = time.time()
        self.model.populate_from_bg_scanner(items, root_path)
        model_time = (time.time() - model_start) * 1000
        print(f"[TREE_VIEW] 📊 Model population took {model_time:.2f}ms")
        
        # Expand root level
        root_index = self.model.index(0, 0)  # First child of invisible root
        if root_index.isValid():
            self.tree_view.expand(root_index)
            
        # Emit signal
        self.root_path_changed.emit(self.root_path)
        
        # Performance logging
        total_time = (time.time() - start_time) * 1000
        print(f"[TREE_VIEW] ✅ Model/View population completed: {len(items)} items in {total_time:.2f}ms")
        print(f"[TREE_VIEW] 📈 Performance: {len(items)/total_time*1000:.1f} items/second")
        
    def get_checked_paths(self) -> List[str]:
        if self.model:
            return self.model.get_checked_paths()
        return []

    def set_checked_paths(self, paths: Set[str]):
        """Set the checked state for a given set of paths and update parent states."""
        from PySide6.QtCore import Qt
        
        # Clear the cached checked files set
        self.model._checked_files.clear()
        
        # Reset all states first to ensure a clean slate
        for node in self.model.path_to_node.values():
            node.check_state = Qt.CheckState.Unchecked

        # Set the specified file paths to checked
        nodes_to_update_parents_for = []
        for path in paths:
            node = None
            
            # First try direct match against stored paths
            if path in self.model.path_to_node:
                node = self.model.path_to_node[path]
            else:
                # CRITICAL FIX: try a normalized forward-slash variant
                normalized_variant = path.replace('\\', '/')
                if normalized_variant in self.model.path_to_node:
                    node = self.model.path_to_node[normalized_variant]
                # Fix #3: Case-Insensitive Path Matching for Windows
                elif os.name == 'nt':  # Windows - try case-insensitive matching
                    normalized_path = os.path.normcase(normalized_variant)
                    for stored_path, stored_node in self.model.path_to_node.items():
                        if os.path.normcase(stored_path) == normalized_path:
                            node = stored_node
                            print(f"[SELECT] 🔍 Case-insensitive match: '{path}' -> '{stored_path}'")
                            break
            
            if node and not node.is_dir:
                node.check_state = Qt.CheckState.Checked
                # Update cached checked files set with original stored path
                actual_path = node.path  # Use the actual stored path
                self.model._checked_files.add(actual_path)
                nodes_to_update_parents_for.append(node)

        # Update all parent states from the bottom up, starting from the parents of the changed nodes
        # This is more efficient than iterating through all paths again
        unique_parents = {node.parent for node in nodes_to_update_parents_for if node.parent}
        for parent_node in unique_parents:
            self.model._update_parent_states(parent_node)

        # Emit a layout changed signal to refresh the entire view at once
        self.model.layoutChanged.emit()
        
    def expand_to_depth(self, depth: int):
        """Expand tree to specified depth."""
        if depth >= 0:
            self.tree_view.expandToDepth(depth)
            
    def get_selected_token_count(self) -> int:
        """Get total token count for selected/checked items."""
        total_tokens = 0
        for path in self.get_checked_paths():
            node = self.model.get_node_by_path(path)
            if node and not node.is_dir:
                total_tokens += node.token_count
        return total_tokens
        
    def update_folder_token_display(self):
        """Update token display for all folders."""
        # In Model/View architecture, this is handled automatically by the model
        # when data changes. We just need to trigger a refresh.
        self.model.dataChanged.emit(QModelIndex(), QModelIndex())
        
    def populate_tree_optimistic(self, items: List, root_path: str):
        """Optimistic tree population (same as regular for Model/View)."""
        # Model/View is already optimistic by design!
        self.populate_tree(items, root_path)
        
    # File system event handling
    def update_from_fs_events(self, event_batch: List):
        """Handle file system events by delegating to the underlying model."""
        if self.model:
            self.model.handle_fs_events(event_batch)
        
    # Compatibility methods for existing TreePanel interface
    def setUpdatesEnabled(self, enabled: bool):
        """Enable/disable updates (compatibility method)."""
        self.tree_view.setUpdatesEnabled(enabled)
        
    def update(self):
        """Update the view (compatibility method)."""
        self.tree_view.update()
        
    def get_tree_widget(self):
        """Get the underlying tree widget (for compatibility)."""
        return self.tree_view
