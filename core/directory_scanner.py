# --- File: directory_scanner.py ---
import os
import pathlib
import traceback
from PySide6.QtCore import QThread, Signal

# --- Import helpers ---
# from .helpers import is_text_file, calculate_tokens
from .helpers import calculate_tokens, MAX_FILE_SIZE_KB, MAX_FILE_SIZE_BYTES, SCAN_BATCH_SIZE # HACK: Temporarily disable is_text_file
from .smart_file_handler import SmartFileHandler

# --- Worker Thread ---
class DirectoryScanner(QThread):
    items_discovered = Signal(list) # list of tuples: (path_str, is_dir, is_valid, reason, token_count)
    scan_started = Signal()
    scan_finished = Signal()
    error_signal = Signal(str, str) # path, error_message
    progress_update = Signal(int) # number of items found

    def __init__(self, root_path, settings, parent=None):
        super().__init__(parent)
        self.root_path = root_path
        self.settings = settings # Expects {'include_subfolders': bool, 'ignore_folders': set}
        self._is_running = True
        self.item_count = 0

    def run(self):
        self.scan_started.emit()
        self._is_running = True
        item_batch = []
        self.item_count = 0
        # Ensure ignore_folders is a set and lowercase for comparison
        ignore_folders_set = {f.lower() for f in self.settings.get('ignore_folders', set())}
        include_subfolders = self.settings.get('include_subfolders', True)
        print(f"Scanner started. Ignoring folders: {ignore_folders_set}, Subfolders: {include_subfolders}")

        try:
            root_path_obj = pathlib.Path(self.root_path)
            if not root_path_obj.is_dir():
                raise ValueError("Selected path is not a valid directory.")

            # Add root item first
            self.items_discovered.emit([(str(root_path_obj), True, True, "", 0)])
            self.item_count += 1

            # Use os.walk to traverse directory tree
            for root, dirs, files in os.walk(self.root_path, topdown=True, onerror=self._handle_walk_error):
                if not self._is_running: break # Check for stop request
                current_root_path = pathlib.Path(root)

                # --- Filter Directories ---
                # Make a copy to modify dirs in place for os.walk pruning
                dirs_to_process = list(dirs)
                dirs[:] = [] # Clear original list, we'll add back allowed ones

                for name in dirs_to_process:
                    if not self._is_running: break
                    # Basic filtering (hidden, ignored names)
                    if name.startswith('.') or name.lower() in ignore_folders_set:
                         continue

                    dir_path_obj = current_root_path / name
                    dir_path_str = str(dir_path_obj)

                    # Check permissions and add to batch/scan queue
                    try:
                        if not os.access(dir_path_str, os.R_OK | os.X_OK):
                             item_batch.append((dir_path_str, True, False, "Permission denied", 0))
                        else:
                             # Add accessible directory to the tree output
                             item_batch.append((dir_path_str, True, True, "", 0))
                             # If including subfolders, add it back to the list for os.walk to descend
                             if include_subfolders:
                                 dirs.append(name)
                    except OSError as e:
                        # Handle errors getting directory info (e.g., broken symlink)
                        item_batch.append((dir_path_str, True, False, f"OS Error: {e.strerror}", 0))

                    self.item_count += 1
                    # Emit batch if full
                    if len(item_batch) >= SCAN_BATCH_SIZE:
                        self.items_discovered.emit(item_batch)
                        self.progress_update.emit(self.item_count)
                        item_batch = []
                        QThread.msleep(10) # Small sleep to allow GUI updates

                if not self._is_running: break # Check again after processing dirs

                # --- Process Files ---
                for name in files:
                    if not self._is_running: break
                    if name.startswith('.'): # Skip hidden files
                        continue

                    file_path_obj = current_root_path / name
                    file_path_str = str(file_path_obj)

                    # Check file validity (text, size, permissions) using helper
                    is_valid, reason = self._check_file_validity_with_detection(file_path_obj)
                    token_count = 0

                    # NO TOKENIZATION DURING SCAN - All tokenization deferred to worker process
                    if is_valid:
                        try:
                            file_size = file_path_obj.stat().st_size
                            strategy = SmartFileHandler.get_tokenization_strategy(str(file_path_obj), file_size)
                            
                            print(f"[SCANNER] File {file_path_obj.name} ({file_size//1024}KB) -> {strategy} (deferred to worker)")
                            
                            if strategy == 'skip':
                                # Skip tokenization entirely - mark with 0 tokens and reason
                                token_count, reason = SmartFileHandler.get_file_display_info(str(file_path_obj), file_size, strategy)
                                print(f"[SCANNER] Will skip {file_path_obj.name}: {reason}")
                            else:
                                # ALL other files deferred to worker process (mark as -1 for "loading...")
                                token_count = -1
                                print(f"[SCANNER] Deferred {file_path_obj.name} to worker process")
                                
                        except Exception as e:
                            print(f"[SCANNER] Could not process file {file_path_obj} during scan: {e}")
                            # Mark as invalid if processing fails
                            is_valid = False
                            reason = f"Processing Error: {str(e)[:50]}"

                    # Add file item to batch
                    item_batch.append((file_path_str, False, is_valid, reason, token_count))
                    self.item_count += 1
                    # Emit batch if full
                    if len(item_batch) >= SCAN_BATCH_SIZE:
                        self.items_discovered.emit(item_batch)
                        self.progress_update.emit(self.item_count)
                        item_batch = []
                        QThread.msleep(10) # Small sleep

                # Optimization: If not including subfolders, stop os.walk from descending further
                # This is implicitly handled now by only adding allowed dirs back to `dirs` list.
                # if not include_subfolders:
                #    dirs[:] = [] # Not strictly needed with the current dir filtering logic

            # Emit any remaining items after the loop finishes
            if item_batch and self._is_running:
                self.items_discovered.emit(item_batch)
                self.progress_update.emit(self.item_count)

        except ValueError as ve: # Catch specific error for invalid root path
            self.error_signal.emit(self.root_path, str(ve))
        except Exception as e: # Catch unexpected errors during scan
            print(f"Error during scan thread execution for {self.root_path}:\n{traceback.format_exc()}")
            self.error_signal.emit(self.root_path, f"Error during scan: {e}")
        finally:
            # Emit finished signal only if the thread wasn't stopped externally
            if self._is_running:
                self.scan_finished.emit()

    def _handle_walk_error(self, os_error):
        """Callback for os.walk errors (usually permission errors)."""
        print(f"Warning: Permission error accessing {os_error.filename}: {os_error.strerror}")
        # Emit an error signal for the GUI to potentially display
        self.error_signal.emit(os_error.filename, f"Permission error: {os_error.strerror}")
        # Note: We might not add this item to the tree explicitly here,
        # as the main loop's permission check should also catch it if it tries to process it.

    def _check_file_validity_with_detection(self, file_path_obj):
        """Checks if a file meets the criteria (detected as text, size, readable)."""
        try:
            file_path_str = str(file_path_obj) # For is_text_file function and os.access

            # 0. Basic readability (check first)
            if not os.access(file_path_str, os.R_OK):
                 return False, "Permission denied"

            # Get file stats early for size and type check
            try:
                 stat_result = file_path_obj.stat()
                 # Check if it's a regular file (not symlink, device, etc.)
                 is_regular_file = (stat_result.st_mode & 0o170000) == 0o100000
                 if not is_regular_file:
                     return False, "Not a regular file"
                 file_size = stat_result.st_size
            except OSError as e:
                 # Handle errors like file not found if it was deleted between listing and stat
                 return False, f"Cannot get size/stat: {e.strerror}"

            # 1. Check size limit (allow empty files through this check)
            if file_size > MAX_FILE_SIZE_BYTES:
                 return False, f"Exceeds size limit ({MAX_FILE_SIZE_KB} KB)"

            # 2. HACK: Temporarily disabled is_text_file detection
            # if file_size > 0 and not is_text_file(file_path_str):
            #      return False, "Non-text (detected)"

            # If all checks pass (readable, regular file, within size, text detected or empty)
            return True, ""

        except OSError as e: # Catch potential OS errors during checks (e.g., path too long)
             return False, f"OS Error: {e.strerror}"
        except Exception as e: # Catch unexpected errors
             print(f"Unexpected error checking file validity for {file_path_str}: {e}")
             traceback.print_exc()
             return False, f"Error checking file: {e}"

    def stop(self):
        """Signals the thread to stop processing."""
        print("Scanner stop requested.")
        self._is_running = False