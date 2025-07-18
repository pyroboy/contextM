import pytest
from unittest.mock import MagicMock, patch
import os
import time
from pathlib import Path

# Adjust path to import from 'core'
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from core.watcher import FileWatcherThread

@pytest.fixture
def temp_watched_dir(tmp_path):
    watch_dir = tmp_path / "watched"
    watch_dir.mkdir()
    return watch_dir

def test_watcher_filters_ignored_and_hidden_files(temp_watched_dir):
    """Ensure the watcher ignores specified patterns and hidden files."""
    ignore_patterns = ["*.log", "__pycache__/*"]
    watcher = FileWatcherThread(str(temp_watched_dir), ignore_patterns)
    
    # Simulate file events
    (temp_watched_dir / "important.txt").touch()
    (temp_watched_dir / "debug.log").touch()
    (temp_watched_dir / ".hidden_file").touch()
    (temp_watched_dir / "__pycache__").mkdir()
    (temp_watched_dir / "__pycache__" / "cache.bin").touch()

    with patch.object(watcher.signals.files_changed, 'emit') as mock_emit:
        # This is a simplified way to test the logic without a real backend
        watcher.process_event(str(temp_watched_dir / "important.txt"))
        watcher.process_event(str(temp_watched_dir / "debug.log"))
        watcher.process_event(str(temp_watched_dir / ".hidden_file"))
        watcher.process_event(str(temp_watched_dir / "__pycache__/cache.bin"))
        time.sleep(0.3) # Wait for debounce

        mock_emit.assert_called_once()
        emitted_files = mock_emit.call_args[0][0]
        assert len(emitted_files) == 1
        assert "important.txt" in emitted_files[0]

def test_watcher_debounces_event_bursts(temp_watched_dir):
    """Check that a rapid burst of events results in a single emission."""
    watcher = FileWatcherThread(str(temp_watched_dir), [])
    
    with patch.object(watcher.signals.files_changed, 'emit') as mock_emit:
        watcher.start()
        (temp_watched_dir / "file1.txt").touch()
        time.sleep(0.05)
        (temp_watched_dir / "file2.txt").touch()
        time.sleep(0.05)
        (temp_watched_dir / "file3.txt").touch()
        
        time.sleep(0.3) # Wait for debounce timer to fire
        
        mock_emit.assert_called_once()
        emitted_files = mock_emit.call_args[0][0]
        assert len(emitted_files) == 3
        watcher.stop()
        watcher.wait()

def test_watcher_emits_batch_within_200ms(temp_watched_dir):
    """Ensure the batch is emitted shortly after the last event."""
    watcher = FileWatcherThread(str(temp_watched_dir), [])
    watcher.DEBOUNCE_DELAY = 0.1 # 100ms for test

    with patch.object(watcher.signals.files_changed, 'emit') as mock_emit:
        watcher.start()
        (temp_watched_dir / "a.txt").touch()
        start_time = time.time()
        
        # Wait for the debounce to complete
        while not mock_emit.called:
            time.sleep(0.01)
            if time.time() - start_time > 0.5: # Timeout
                pytest.fail("Watcher did not emit in time.")

        end_time = time.time()
        emission_delay = end_time - start_time

        assert emission_delay < 0.2 # Should be around 100ms + processing time
        mock_emit.assert_called_once()
        watcher.stop()
        watcher.wait()
