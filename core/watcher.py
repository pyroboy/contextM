import time
import threading
import os
import queue
from watchdog.observers.polling import PollingObserver as Observer
import fnmatch
from watchdog.events import FileSystemEventHandler, FileSystemMovedEvent
from PySide6.QtCore import QObject, Signal, QTimer
from .tokenizer import count_tokens

class _EventHandler(FileSystemEventHandler):
    def __init__(self, event_queue, ignore_rules):
        super().__init__()
        self.queue = event_queue
        self.ignore_rules = ignore_rules

    def on_any_event(self, event):
        if event.is_directory or self._is_ignored(event.src_path):
            return
        
        # Just put the raw event data in the queue
        event_data = {
            'action': event.event_type,
            'src_path': event.src_path,
            'dst_path': event.dest_path if isinstance(event, FileSystemMovedEvent) else None
        }
        self.queue.put(event_data)

    def _is_ignored(self, path):
        """Check if a path matches any of the glob-style ignore rules."""
        for pattern in self.ignore_rules:
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(os.path.basename(path), pattern):
                return True
        return False

class FileWatcher(QObject):
    fs_event_batch = Signal(list)
    file_token_changed = Signal(str, int)  # file_path, token_diff

    def __init__(self, root_path, ignore_rules):
        super().__init__()
        self.root_path = root_path
        # Ensure we get a set of patterns
        self.ignore_rules = set(ignore_rules or [])
        self.event_queue = queue.Queue()
        self.token_cache = {}
        self._stop_event = threading.Event()
        self._thread = None

        # This timer will poll the queue from the main Qt thread
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._process_queue)
        self.poll_timer.setInterval(150)

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
        observer = Observer()
        observer.schedule(event_handler, self.root_path, recursive=True)
        observer.start()
        while not self._stop_event.is_set():
            time.sleep(0.1)
        observer.stop()
        observer.join()

    def _process_queue(self):
        """This method runs in the main Qt thread."""
        if self.event_queue.empty():
            return

        fs_events = []
        while not self.event_queue.empty():
            try:
                event = self.event_queue.get_nowait()
                if event['action'] == 'modified':
                    # Handle token changes here in the main thread
                    path = event['src_path']
                    old_tokens = self.token_cache.get(path, count_tokens(path))
                    new_tokens = count_tokens(path)
                    token_diff = new_tokens - old_tokens
                    self.token_cache[path] = new_tokens
                    if token_diff != 0:
                        self.file_token_changed.emit(path, token_diff)
                else:
                    fs_events.append(event)
                    # Update token cache for moves/deletes
                    if event['action'] == 'deleted' and event['src_path'] in self.token_cache:
                        del self.token_cache[event['src_path']]
                    elif event['action'] == 'moved' and event['src_path'] in self.token_cache:
                        self.token_cache[event['dst_path']] = self.token_cache.pop(event['src_path'])

            except queue.Empty:
                break
        
        if fs_events:
            self.fs_event_batch.emit(fs_events)
