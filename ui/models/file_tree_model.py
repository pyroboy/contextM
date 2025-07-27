"""
High-performance file tree model using Qt's Model/View architecture.
Replaces QTreeWidget for scalable performance with large file trees.
"""

import os
from typing import Dict, List, Optional, Any, Tuple, Set
from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, QObject
from PySide6.QtGui import QIcon


class TreeNode:
    def __init__(self, path, is_dir=False, parent=None):
        self.path = path
        self.is_dir = is_dir
        self.parent = parent
        self.children = []  # Always use list for consistency
        self.check_state = Qt.CheckState.Unchecked
        self.token_count = 0
        self.is_valid = True
        self.reason = ""
        self.name = os.path.basename(path) if path else ""
        
    def add_child(self, child):
        """Add a child node."""
        child.parent = self
        self.children.append(child)
        
    @property
    def is_directory(self):
        """Alias for is_dir for compatibility."""
        return self.is_dir
        
    def find_child(self, path):
        """Find direct child by path."""
        for child in self.children:
            if child.path == path:
                return child
        return None
        
    def row(self):
        """Get the row index of this node in its parent's children list."""
        if self.parent:
            return self.parent.children.index(self)
        return 0
        
    def child_count(self):
        """Get the number of children for this node."""
        return len(self.children)
        
    def child_at(self, index):
        """Get child node at the specified index."""
        if 0 <= index < len(self.children):
            return self.children[index]
        return None


class FileTreeModel(QAbstractItemModel):
    """
    High-performance tree model for file/directory display.
    Uses lightweight TreeNode objects instead of heavyweight QTreeWidgetItems.
    """
    
    # Custom roles for data access
    PathRole = Qt.ItemDataRole.UserRole + 1
    IsDirRole = Qt.ItemDataRole.UserRole + 2
    TokenCountRole = Qt.ItemDataRole.UserRole + 3
    FileSizeRole = Qt.ItemDataRole.UserRole + 4
    IsValidRole = Qt.ItemDataRole.UserRole + 5
    ReasonRole = Qt.ItemDataRole.UserRole + 6
    
    def __init__(self, parent=None, view=None):
        """Initialize the file tree model."""
        super().__init__(parent)
        self.root_node = TreeNode("", True)  # Invisible root
        self.path_to_node: Dict[str, TreeNode] = {}
        self._checked_files = set()  # Cache of checked file paths for fast aggregation
        self.view = view  # Reference to the view for checking ignore flag
        self.root_path = ""
        
    def clear(self) -> None:
        """Clear all data from the model."""
        self.beginResetModel()
        self.root_node = TreeNode("", True)
        self.path_to_node.clear()
        self._checked_files.clear()  # CRITICAL: Clear cached checked files
        self.root_path = ""
        self.endResetModel()
        
    def populate_from_bg_scanner(self, items: List[Tuple], root_path: str, pending_restore_paths: Optional[Set[str]] = None) -> None:
        """
        Populate model with data from BG_scanner results.
        This is the key performance optimization - direct data loading.
        
        Args:
            items: List of tuples containing file/directory information
            root_path: The root path for the tree
            pending_restore_paths: Optional set of paths to restore as checked after population
        """
        self.beginResetModel()
        
        # Clear existing data - ensure all nodes start with unchecked state
        self.root_node = TreeNode("", True)
        self.path_to_node.clear()
        self._checked_files.clear()  # CRITICAL: Clear cached checked files to ensure clean state
        self.root_path = os.path.normpath(root_path).replace('\\', '/')
        
        # Create root project node (starts unchecked by default)
        project_node = TreeNode(self.root_path, True, self.root_node)
        self.root_node.add_child(project_node)
        self.path_to_node[self.root_path] = project_node
        
        # Sort items: directories first, then files
        sorted_items = sorted(items, key=lambda x: (not x[1], x[0]))  # dirs first, then by path
        
        # Create all directory nodes first (all start unchecked by default)
        for path_str, is_dir, rel_path, file_size, tokens in sorted_items:
            if is_dir:
                norm_path = os.path.normpath(path_str).replace('\\', '/')
                self._ensure_directory_path(norm_path)
        
        # Then add all files (all start unchecked by default)
        for path_str, is_dir, rel_path, file_size, tokens in sorted_items:
            if not is_dir:
                norm_path = os.path.normpath(path_str).replace('\\', '/')
                self._add_file_node(norm_path, file_size, tokens)
        
        # Apply pending paths to restore after population (if provided)
        if pending_restore_paths:
            self._restore_checked_paths(pending_restore_paths)
        
        self.endResetModel()
        
    def _ensure_directory_path(self, dir_path: str) -> TreeNode:
        """Ensure all directories in path exist, creating them if necessary."""
        if dir_path in self.path_to_node:
            return self.path_to_node[dir_path]
            
        # Ensure parent directory exists first
        parent_path = os.path.dirname(dir_path)
        if parent_path and parent_path != dir_path:
            parent_node = self._ensure_directory_path(parent_path)
        else:
            parent_node = self.path_to_node[self.root_path]
            
        # Create this directory node
        dir_node = TreeNode(dir_path, True, parent_node)
        parent_node.add_child(dir_node)
        self.path_to_node[dir_path] = dir_node
        
        return dir_node
        
    def _add_file_node(self, file_path: str, file_size: int, tokens: int) -> None:
        """Add a file node to the appropriate parent directory."""
        parent_path = os.path.dirname(file_path)
        parent_node = self._ensure_directory_path(parent_path)
        
        # Create file node
        file_node = TreeNode(file_path, False, parent_node)
        file_node.file_size = file_size
        file_node.token_count = tokens
        
        parent_node.add_child(file_node)
        self.path_to_node[file_path] = file_node
        
    def _restore_checked_paths(self, pending_restore_paths: Set[str]) -> None:
        """Restore checked state for pending paths after tree population.
        
        This method ensures that:
        1. Only file paths (not directories) are checked
        2. Parent states are properly updated to reflect child selections
        3. The _checked_files cache is properly maintained
        
        Args:
            pending_restore_paths: Set of file paths to restore as checked
        """
        nodes_to_update_parents_for = []
        
        # Set checked state for files that exist in the tree
        for path in pending_restore_paths:
            # Normalize the path to match our storage format
            norm_path = os.path.normpath(path).replace('\\', '/')
            
            if norm_path in self.path_to_node:
                node = self.path_to_node[norm_path]
                # Only restore checked state for files, not directories
                if not node.is_dir:
                    node.check_state = Qt.CheckState.Checked
                    # Update cached checked files set
                    self._checked_files.add(norm_path)
                    nodes_to_update_parents_for.append(node)
        
        # Update parent states efficiently by collecting unique parents
        if nodes_to_update_parents_for:
            unique_parents = {node.parent for node in nodes_to_update_parents_for if node.parent}
            for parent_node in unique_parents:
                self._update_parent_states(parent_node)
        
    # QAbstractItemModel interface implementation
    
    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        """Create model index for given row/column/parent."""
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
            
        if not parent.isValid():
            parent_node = self.root_node
        else:
            parent_node = parent.internalPointer()
            
        child_node = parent_node.child_at(row)
        if child_node:
            return self.createIndex(row, column, child_node)
        else:
            return QModelIndex()
            
    def parent(self, index: QModelIndex) -> QModelIndex:
        """Get parent index for given index."""
        if not index.isValid():
            return QModelIndex()
            
        child_node = index.internalPointer()
        parent_node = child_node.parent
        
        if parent_node == self.root_node or parent_node is None:
            return QModelIndex()
            
        return self.createIndex(parent_node.row(), 0, parent_node)
        
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Get number of rows (children) for given parent."""
        if parent.column() > 0:
            return 0
            
        if not parent.isValid():
            parent_node = self.root_node
        else:
            parent_node = parent.internalPointer()
            
        return parent_node.child_count()
        
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Get number of columns."""
        return 2  # Name, Tokens
        
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Get data for given index and role."""
        if not index.isValid():
            return None
            
        node = index.internalPointer()
        column = index.column()
        
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return node.name
            elif column == 1:
                if node.is_dir:
                    # Calculate total tokens for directory
                    total_tokens = self._calculate_directory_tokens(node)
                    return f"{total_tokens:,} tokens" if total_tokens > 0 else ""
                else:
                    return f"{node.token_count:,} tokens" if node.token_count > 0 else ""
                    
        elif role == Qt.ItemDataRole.CheckStateRole and column == 0:
            return node.check_state
            
        elif role == self.PathRole:
            return node.path
        elif role == self.IsDirRole:
            return node.is_dir
        elif role == self.TokenCountRole:
            return node.token_count
        elif role == self.FileSizeRole:
            return node.file_size
        elif role == self.IsValidRole:
            return node.is_valid
        elif role == self.ReasonRole:
            return node.reason
            
        return None
        
    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        """Set data for given index and role with proper state change detection."""
        if not index.isValid():
            return False
            
        node = index.internalPointer()
        
        if role == Qt.ItemDataRole.CheckStateRole:
            # Convert value to proper CheckState if needed
            if isinstance(value, int):
                check_state = Qt.CheckState(value)
            else:
                check_state = value
                
            # Only proceed if state actually changed
            if node.check_state == check_state:
                return True
                
            # Set the new state
            node.check_state = check_state
            
            # Update cached checked files set for fast aggregation
            if not node.is_dir:
                if check_state == Qt.CheckState.Checked:
                    self._checked_files.add(node.path)
                else:
                    self._checked_files.discard(node.path)
            
            # Debug logging disabled for performance
            # print(f"[CHECKBOX_DEBUG] {node.path}: {check_state.name}")
            
            # Emit data changed for this node
            self.dataChanged.emit(index, index, [role])

            # Propagate changes to children if this is a directory
            if node.is_dir and check_state != Qt.CheckState.PartiallyChecked:
                self._propagate_to_children(node, check_state)
                
            # Update parent states recursively
            self._update_parent_states(node.parent)
            
            return True
            
        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """Get flags for given index."""
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
            
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        
        if index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
            # Auto-tristate is needed for parent/child selection logic
            flags |= Qt.ItemFlag.ItemIsAutoTristate
            
        return flags

    def _propagate_to_children(self, parent_node: 'TreeNode', check_state: Qt.CheckState):
        """Recursively set the check state for all children using optimized bulk strategy."""
        # Collect all nodes that need updating first (bulk strategy)
        nodes_to_update = []
        self._collect_children_for_update(parent_node, check_state, nodes_to_update)
        
        if not nodes_to_update:
            return
        
        # Block signals during bulk state updates to prevent individual emissions
        self.blockSignals(True)
        
        try:
            # Update all node states in memory first (no signals yet)
            for node in nodes_to_update:
                node.check_state = check_state
                
                # Update cached checked files set for fast aggregation
                if not node.is_dir:
                    if check_state == Qt.CheckState.Checked:
                        self._checked_files.add(node.path)
                    else:
                        self._checked_files.discard(node.path)
        finally:
            # Unblock signals
            self.blockSignals(False)
        
        # Emit single dataChanged signal for the entire range to maintain performance
        # This tells the view that checkboxes have changed without individual signals
        if nodes_to_update:
            # Find the parent's index to emit a range-based signal
            try:
                parent_index = self.createIndex(parent_node.row(), 0, parent_node)
                if parent_index.isValid():
                    # Emit dataChanged for the parent and let the view handle the refresh
                    self.dataChanged.emit(parent_index, parent_index, [Qt.ItemDataRole.CheckStateRole])
                    # Also emit layoutChanged to ensure all child checkboxes update
                    self.layoutChanged.emit()
            except (ValueError, IndexError):
                # Fallback: just emit layoutChanged
                self.layoutChanged.emit()
            
    def _collect_children_for_update(self, parent_node: 'TreeNode', check_state: Qt.CheckState, nodes_to_update: list):
        """Recursively collect all children that need state updates."""
        for child in parent_node.children:
            if child.check_state != check_state:
                nodes_to_update.append(child)
                if child.is_dir:
                    self._collect_children_for_update(child, check_state, nodes_to_update)

    def _update_parent_states(self, node: 'TreeNode'):
        """Recursively update the check state of parent nodes using bulk strategy."""
        # Collect all parents that need updating
        parents_to_update = []
        current_node = node
        
        while current_node:
            # Skip nodes without children (leaf nodes don't need state calculation)
            if not current_node.children:
                current_node = current_node.parent
                continue
                
            # Calculate new state based on children
            new_state = self._calculate_parent_state(current_node)
            
            # Only update if state actually changed
            if current_node.check_state != new_state:
                current_node.check_state = new_state
                parents_to_update.append(current_node)
            
            current_node = current_node.parent
            
        # Emit efficient signals for parent updates to ensure UI sync
        if parents_to_update:
            # Block signals during bulk parent updates
            self.blockSignals(True)
            try:
                pass  # States already updated above
            finally:
                self.blockSignals(False)
            
            # Emit single dataChanged signal for all parents at once
            # This is much more efficient than individual signals
            if len(parents_to_update) == 1:
                # Single parent - emit specific signal
                parent = parents_to_update[0]
                try:
                    parent_index = self.createIndex(parent.row(), 0, parent)
                    if parent_index.isValid():
                        self.dataChanged.emit(parent_index, parent_index, [Qt.ItemDataRole.CheckStateRole])
                except (ValueError, IndexError):
                    self.layoutChanged.emit()
            else:
                # Multiple parents - emit layoutChanged for efficiency
                self.layoutChanged.emit()
            
    def _calculate_parent_state(self, parent_node: 'TreeNode') -> Qt.CheckState:
        """Calculate the appropriate check state for a parent based on its children."""
        if not parent_node.children:
            return parent_node.check_state
            
        child_states = [child.check_state for child in parent_node.children]
        
        # Count different states
        checked_count = child_states.count(Qt.CheckState.Checked)
        unchecked_count = child_states.count(Qt.CheckState.Unchecked)
        partial_count = child_states.count(Qt.CheckState.PartiallyChecked)
        
        # Determine parent state based on children
        if partial_count > 0:
            # Any partially checked child means parent is partially checked
            return Qt.CheckState.PartiallyChecked
        elif checked_count > 0 and unchecked_count > 0:
            # Mixed checked/unchecked children means partially checked
            return Qt.CheckState.PartiallyChecked
        elif checked_count > 0 and unchecked_count == 0:
            # All children checked means parent is checked
            return Qt.CheckState.Checked
        else:
            # All children unchecked means parent is unchecked
            return Qt.CheckState.Unchecked

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Get header data."""
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section == 0:
                return "Name"
            elif section == 1:
                return "Tokens"
        return None

    def _calculate_directory_tokens(self, dir_node: TreeNode) -> int:
        """Calculate total tokens for a directory (recursive)."""
        total = 0
        for child in dir_node.children:
            if child.is_dir:
                total += self._calculate_directory_tokens(child)
            else:
                total += child.token_count
        return total
        
    def get_node_by_path(self, path: str) -> Optional[TreeNode]:
        """Get tree node by file path."""
        return self.path_to_node.get(path)
        
    def get_checked_paths(self) -> List[str]:
        """Get a list of all checked file paths, ignoring partially checked folders.
        
        This method traverses the tree dynamically to collect checked file paths
        and ensures the cache is synchronized with the actual tree state.
        """
        # Collect checked file paths by traversing the tree
        checked_paths = []
        self._collect_checked_file_paths(self.root_node, checked_paths)
        
        # Synchronize the cache with the actual tree state
        actual_checked_set = set(checked_paths)
        if self._checked_files != actual_checked_set:
            # Cache is out of sync, update it
            self._checked_files = actual_checked_set.copy()
        
        return checked_paths
        
    def _collect_checked_file_paths(self, node: TreeNode, checked_paths: List[str]) -> None:
        """Recursively collect checked file paths (not directory paths).
        
        This method only collects paths for files that are checked, ignoring
        directories even if they are checked or partially checked.
        """
        # Only collect file paths (not directory paths) that are checked
        if not node.is_dir and node.check_state == Qt.CheckState.Checked and node.path:
            checked_paths.append(node.path)
        
        # Recursively traverse all children
        for child in node.children:
            self._collect_checked_file_paths(child, checked_paths)
    
    def _collect_checked_paths(self, node: TreeNode, checked_paths: List[str]) -> None:
        """Recursively collect checked paths."""
        if node.is_checked and node.path:
            checked_paths.append(node.path)
        for child in node.children:
            self._collect_checked_paths(child, checked_paths)
