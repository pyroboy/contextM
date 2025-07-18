import unittest
import time
import tempfile
import os
from unittest.mock import Mock, MagicMock

from PySide6.QtCore import QCoreApplication, QTimer

from core.watcher import FileWatcher

class TestFileWatcher(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.watcher = FileWatcher(self.temp_dir.name, ignore_rules=set())
        self.mock_slot = Mock()
        self.watcher.fs_event_batch.connect(self.mock_slot)

    def tearDown(self):
        self.watcher.stop()
        self.temp_dir.cleanup()

    def test_watcher_starts_and_stops(self):
        """Test that the watcher thread starts and stops correctly."""
        self.assertFalse(self.watcher.isRunning())
        self.watcher.start()
        self.assertTrue(self.watcher.isRunning())
        self.watcher.stop()
        self.assertFalse(self.watcher.isRunning())

    def test_file_creation_event(self):
        """Test that creating a new file emits a signal."""
        self.watcher.start()
        time.sleep(0.1)  # Give the observer thread time to start

        file_path = os.path.join(self.temp_dir.name, "test.txt")
        with open(file_path, "w") as f:
            f.write("hello")

        # Wait for the polling timer to process the queue
        for _ in range(10):
            if self.mock_slot.called:
                break
            self.app.processEvents()
            time.sleep(0.1)

        self.mock_slot.assert_called_once()
        call_args = self.mock_slot.call_args[0][0]
        self.assertEqual(len(call_args), 1)
        self.assertEqual(call_args[0]['action'], 'created')
        self.assertEqual(call_args[0]['src_path'], file_path)

if __name__ == '__main__':
    unittest.main()
