# Selection Manager Dirty State Tracking

## Overview

This implementation adds proper dirty state tracking for the selection manager when checkboxes are toggled in the file tree. This ensures users are prompted to save changes when they modify selections, preventing accidental loss of unsaved changes.

## Implementation Details

### 1. Signal Connections

The implementation connects the FileTreeModel's `dataChanged` signal to the selection manager's dirty state tracking:

**In `MainWindow._setup_ui()` (lines 161-173):**
```python
# Connect signals (Model/View TreePanel uses same interface)
if hasattr(self.tree_panel, 'item_checked_changed'):
    # Old TreePanel - connect to item_checked_changed signal
    self.tree_panel.item_checked_changed.connect(self._on_checkbox_changed)
else:
    # Model/View TreePanel - connect to model's dataChanged signal
    if hasattr(self.tree_panel, 'file_tree_view') and hasattr(self.tree_panel.file_tree_view, 'model'):
        self.tree_panel.file_tree_view.model.dataChanged.connect(self._on_model_data_changed)
```

### 2. Event Handlers

Two new event handlers were added to `MainWindow`:

**`_on_checkbox_changed()` - For old TreePanel:**
```python
@Slot()
def _on_checkbox_changed(self):
    """Handle checkbox state changes for dirty state tracking."""
    self.selection_manager_panel.set_dirty(True)
    print(f"[SELECTION] 🔄 Checkbox changed - selection manager marked as dirty")
```

**`_on_model_data_changed()` - For Model/View TreePanel:**
```python
@Slot()
def _on_model_data_changed(self, top_left, bottom_right, roles):
    """Handle model data changes, specifically checkbox state changes."""
    from PySide6.QtCore import Qt
    
    # Check if this was a checkbox state change
    if Qt.ItemDataRole.CheckStateRole in roles:
        self.selection_manager_panel.set_dirty(True)
        print(f"[SELECTION] 🔄 Model checkbox changed - selection manager marked as dirty")
```

### 3. Existing Clean State Logic

The selection controller already had proper clean state logic in place:

**In `SelectionController.on_group_changed()` (line 74):**
```python
# Reset dirty state when switching groups
self.mw.selection_manager_panel.set_dirty(False)
```

## Signal Flow

1. **User toggles checkbox** in file tree
2. **FileTreeModel.setData()** is called with `CheckStateRole`
3. **Model emits `dataChanged` signal** with `CheckStateRole` in roles
4. **MainWindow._on_model_data_changed()** receives the signal
5. **Selection manager is marked as dirty** via `set_dirty(True)`
6. **Save button becomes enabled** to prompt user to save changes

## Compatibility

This implementation works with both:
- **Old TreePanel**: Uses `item_checked_changed` signal
- **Model/View TreePanel**: Uses `model.dataChanged` signal with role filtering

## Testing

The implementation was validated with a test script that:
1. ✅ Verifies `dataChanged` signal is emitted when checkboxes are toggled
2. ✅ Confirms selection manager is marked dirty on checkbox changes
3. ✅ Validates dirty state is cleared when switching groups

## Benefits

- **Prevents data loss**: Users are prompted to save changes before switching groups
- **Clear visual feedback**: Save button is enabled when there are unsaved changes
- **Consistent behavior**: Works with both old and new tree panel implementations
- **Performance**: Minimal overhead with role-based filtering of signals
