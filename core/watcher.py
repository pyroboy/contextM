import time
import threading
import queue
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler, FileSystemMovedEvent
from PySide6.QtCore import QObject, Signal, QTimer

class _EventHandler(FileSystemEventHandler):
    def __init__(self, event_queue, ignore_rules):
        super().__init__()
        self.queue = event_queue
        self.ignore_rules = ignore_rules

    def on_any_event(self, event):
        if event.is_directory or self._is_ignored(event.src_path):
            return
        
        event_data = {
            'action': event.event_type,
            'src_path': event.src_path,
            'dst_path': event.dest_path if isinstance(event, FileSystemMovedEvent) else None
        }
        self.queue.put(event_data)

    def _is_ignored(self, path):
        return any(rule in path for rule in self.ignore_rules)

class FileWatcher(QObject):
    fs_event_batch = Signal(list)

    def __init__(self, root_path, ignore_rules):
        super().__init__()
        self.root_path = root_path
        self.ignore_rules = ignore_rules
        self.event_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = None

        # This timer will poll the queue from the main Qt thread
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._process_queue)
        self.poll_timer.setInterval(250)

    def start(self):
        if self.isRunning():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_observer)
        self._thread.daemon = True
        self._thread.start()
        self.poll_timer.start()

    def stop(self):
        if not self.isRunning():
            return
        self._stop_event.set()
        self._thread.join(timeout=2)
        self._thread = None
        self.poll_timer.stop()

    def isRunning(self):
        return self._thread is not None and self._thread.is_alive()

    def _run_observer(self):
        """This method runs in the background thread."""
        event_handler = _EventHandler(self.event_queue, self.ignore_rules)
        # Forcing PollingObserver to avoid platform-specific issues with Qt
        observer = Observer()
        observer.schedule(event_handler, self.root_path, recursive=True)
        observer.start()
        self._stop_event.wait() # Wait until stop is called
        observer.stop()
        observer.join()

    def _process_queue(self):
        """This method runs in the main Qt thread."""
        if self.event_queue.empty():
            return

        batch = []
        while not self.event_queue.empty():
            try:
                batch.append(self.event_queue.get_nowait())
            except queue.Empty:
                break
        
        if batch:
            self.fs_event_batch.emit(batch)
