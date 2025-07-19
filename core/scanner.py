import os
from PySide6.QtCore import QObject, Signal, Slot

# The original QThread worker
from .directory_scanner import DirectoryScanner

class Scanner(QObject):
    """A wrapper around DirectoryScanner to simplify its use."""
    scan_complete = Signal(dict) # Emits a dictionary with 'items' and 'errors'

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scanner_thread = None
        self._results = {'items': [], 'errors': []}

    @Slot(str, dict)
    def start_scan(self, root_path, settings):
        """Starts a new scan. Aborts any existing scan."""
        if self._scanner_thread and self._scanner_thread.isRunning():
            print("Stopping previous scan...")
            self._scanner_thread.stop()
            self._scanner_thread.wait() # Wait for it to finish

        print(f"Starting new scan for: {root_path}")
        self._results = {'items': [], 'errors': []}
        
        self._scanner_thread = DirectoryScanner(root_path, settings)
        
        # Connect signals from the worker thread to internal slots
        self._scanner_thread.items_discovered.connect(self._handle_items_discovered)
        self._scanner_thread.error_signal.connect(self._handle_error)
        self._scanner_thread.scan_finished.connect(self._handle_scan_finished)
        
        self._scanner_thread.start()

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
        print("Scan finished. Emitting results.")
        self.scan_complete.emit(self._results)
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
        if self._scanner_thread and self._scanner_thread.isRunning():
            self._scanner_thread.stop()

    def run(self):
        """For unit-test convenience – delegates to internal thread."""
        return self._scanner_thread.run()
