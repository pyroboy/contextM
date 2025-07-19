import os
from PySide6.QtCore import QObject, Signal, Slot

from .directory_scanner import DirectoryScanner
from .helpers import calculate_tokens, MAX_FILE_SIZE_BYTES
from .smart_file_handler import SmartFileHandler
from .qt_thread_tokenizer import QtThreadTokenizer

class Scanner(QObject):
    """A wrapper around DirectoryScanner to simplify its use."""
    scan_complete = Signal(dict) # Emits a dictionary with 'items' and 'errors'

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scanner_thread = None
        self._results = {'items': [], 'errors': []}
        self.is_scanning = False
        self.should_stop = False
        self.qt_tokenizer = QtThreadTokenizer(self)
        
        # Batching for UI responsiveness
        self._update_batch_count = 0
        self._batch_size = 5  # Update UI every 5 files instead of every file
        
        print(f"[SCANNER] 🧵 Created QThread-based tokenizer (robust, Qt-native)")
        print(f"[SCANNER] 📦 UI updates batched every {self._batch_size} files for responsiveness")
        
        # Connect Qt tokenizer signals
        self.qt_tokenizer.token_update.connect(self._on_token_update)
        self.qt_tokenizer.file_validation_update.connect(self._on_file_validation_update)
        self.qt_tokenizer.progress_update.connect(self._on_tokenization_progress)
        self.qt_tokenizer.status_update.connect(self._on_tokenization_status)

    @Slot(str, dict)
    def start_scan(self, root_path, settings):
        """Starts a new scan. Aborts any existing scan."""
        import time
        start_time = time.time()
        
        print(f"[SCANNER] 🚀 start_scan called for: {root_path}")
        print(f"[SCANNER] 📊 Settings: {settings}")
        print(f"[SCANNER] 📱 UI thread responsive: {self.parent().isVisible() if self.parent() else 'No parent'}")
        
        if self._scanner_thread and self._scanner_thread.isRunning():
            print("[SCANNER] ⏹️ Stopping previous scan...")
            stop_start = time.time()
            self._scanner_thread.stop()
            self._scanner_thread.wait() # Wait for it to finish
            stop_time = (time.time() - stop_start) * 1000
            print(f"[SCANNER] ✅ Previous scan stopped in {stop_time:.2f}ms")

        print(f"[SCANNER] 📁 Starting new scan for: {root_path}")
        print(f"[SCANNER] 🧾 Clearing previous results...")
        self._results = {'items': [], 'errors': []}
        
        thread_start = time.time()
        self._scanner_thread = DirectoryScanner(root_path, settings)
        
        # Connect signals from the worker thread to internal slots
        self._scanner_thread.items_discovered.connect(self._handle_items_discovered)
        self._scanner_thread.error_signal.connect(self._handle_error)
        self._scanner_thread.scan_finished.connect(self._handle_scan_finished)
        
        self._scanner_thread.start()
        thread_time = (time.time() - thread_start) * 1000
        
        total_time = (time.time() - start_time) * 1000
        print(f"[SCANNER] Scanner thread created and started in {thread_time:.2f}ms (total: {total_time:.2f}ms)")

    @Slot(list)
    def _handle_items_discovered(self, item_batch):
        """Collects discovered items from the worker."""
        self._results['items'].extend(item_batch)

    @Slot(str, str)
    def _handle_error(self, path, error_message):
        """Collects errors from the worker."""
        self._results['errors'].append((path, error_message))

    @Slot()
    def _handle_scan_finished(self):
        """Called when the worker thread is finished. Emits the final signal."""
        import time
        emit_start = time.time()
        
        total_items = len(self._results['items'])
        total_errors = len(self._results['errors'])
        print(f"[SCANNER] ✅ Scan finished. Found {total_items} items, {total_errors} errors. Emitting results...")
        
        # Emit initial results (with -1 token counts for files needing tokenization)
        self.scan_complete.emit(self._results)
        
        # Start worker process tokenization for files that need it
        files_to_tokenize = []
        for path, is_dir, is_valid, reason, token_count in self._results['items']:
            if not is_dir and is_valid and token_count == -1:  # Files marked for tokenization
                files_to_tokenize.append(path)
        
        if files_to_tokenize:
            print(f"[SCANNER] 🧵 Starting QThread tokenization for {len(files_to_tokenize)} files...")
            self.qt_tokenizer.tokenize_files(files_to_tokenize, batch_size=3)  # Small batches for responsiveness
        else:
            print(f"[SCANNER] ℹ️ No files need tokenization (all skipped or cached)")
        
        emit_time = (time.time() - emit_start) * 1000
        print(f"[SCANNER] Results emitted in {emit_time:.2f}ms")
        self._scanner_thread = None # Allow thread to be garbage collected

    def is_running(self):
        """Checks if a scan is currently in progress."""
        return self._scanner_thread and self._scanner_thread.isRunning()

    def wait_for_completion(self, timeout=None):
        """Blocks until the current scan is finished."""
        if self.is_running():
            return self._scanner_thread.wait(timeout) if timeout else self._scanner_thread.wait()

    def stop(self):
        """Public method to stop the scan if needed."""
        print(f"[SCANNER] 🛑 Stop requested - cleaning up scanner and tokenizer...")
        
        # Stop the directory scanner thread
        if self._scanner_thread and self._scanner_thread.isRunning():
            print(f"[SCANNER] ⏹️ Stopping directory scanner thread...")
            self._scanner_thread.stop()
        
        # Stop the QThread tokenizer
        if self.qt_tokenizer:
            print(f"[SCANNER] 🧵 Stopping QThread tokenizer...")
            self.qt_tokenizer.stop()
        
        print(f"[SCANNER] ✅ Scanner cleanup completed")

    def _on_token_update(self, file_path: str, token_count: int):
        """Handle token count update from worker process."""
        print(f"[SCANNER] 📥 Received token update: {os.path.basename(file_path)} -> {token_count} tokens")
        
        # Update the results with new token count
        updated = False
        for i, (path, is_dir, is_valid, reason, old_count) in enumerate(self._results['items']):
            if path == file_path and not is_dir:
                self._results['items'][i] = (path, is_dir, is_valid, reason, token_count)
                updated = True
                print(f"[SCANNER] ✅ Updated {os.path.basename(file_path)} from {old_count} to {token_count} tokens")
                break
        
        if not updated:
            print(f"[SCANNER] ⚠️ Could not find {os.path.basename(file_path)} in results to update")
        
        # Batched UI updates for responsiveness
        self._update_batch_count += 1
        if self._update_batch_count >= self._batch_size:
            print(f"[SCANNER] 📦 Batch complete ({self._batch_size} files) - emitting UI update...")
            self.scan_complete.emit(self._results)
            self._update_batch_count = 0  # Reset batch counter
        else:
            print(f"[SCANNER] 🔄 Batching update ({self._update_batch_count}/{self._batch_size})...")
    
    def _on_file_validation_update(self, file_path: str, is_valid: bool, reason: str):
        """Handle file validation update from worker process."""
        # Update the results with validation info
        for i, (path, is_dir, old_valid, old_reason, token_count) in enumerate(self._results['items']):
            if path == file_path and not is_dir:
                self._results['items'][i] = (path, is_dir, is_valid, reason, token_count)
                break
        
        # Emit updated results
        self.scan_complete.emit(self._results)
    
    def _on_tokenization_progress(self, current: int, total: int):
        """Handle tokenization progress updates."""
        progress_percent = (current / total * 100) if total > 0 else 0
        print(f"[SCANNER] 📈 Tokenization progress: {current}/{total} ({progress_percent:.1f}%)")
    
    def _on_tokenization_status(self, status: str):
        """Handle tokenization status updates."""
        print(f"[SCANNER] 💬 Tokenization status: {status}")
        
        # If tokenization is completed, emit final UI update for any remaining batched items
        if "completed" in status.lower():
            if self._update_batch_count > 0:
                print(f"[SCANNER] 🏁 Final UI update for remaining {self._update_batch_count} batched items...")
                self.scan_complete.emit(self._results)
                self._update_batch_count = 0
            print(f"[SCANNER] ✅ All tokenization and UI updates completed!")

    def run(self):
        """For unit-test convenience – delegates to internal thread."""
        return self._scanner_thread.run()
