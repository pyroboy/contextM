import pytest
from unittest.mock import MagicMock, patch
import os
import time
from pathlib import Path

# Adjust path to import from 'core'
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from core.watcher import FileWatcher

@pytest.fixture
def temp_watched_dir(tmp_path):
    watch_dir = tmp_path / "watched"
    watch_dir.mkdir()
    return watch_dir

def test_watcher_filters_ignored_files(temp_watched_dir, qtbot):
    """U-11: Ensure the watcher ignores specified glob patterns for files and directories."""
    ignore_rules = ['*.log', 'build/*', '__pycache__']
    watcher = FileWatcher(str(temp_watched_dir), ignore_rules)
    
    # Create a directory to be ignored
    build_dir = temp_watched_dir / "build"
    build_dir.mkdir()

    with qtbot.waitSignal(watcher.fs_event_batch, timeout=1000) as blocker:
        watcher.start()
        # Create files that should trigger events
        (temp_watched_dir / "src").mkdir()
        (temp_watched_dir / "src" / "main.py").touch()
        
        # Create files and folders that should be ignored
        (temp_watched_dir / "app.log").touch()
        (build_dir / "output.bin").touch()
        (temp_watched_dir / "__pycache__").mkdir()
        (temp_watched_dir / "__pycache__" / "cache.bin").touch()

    assert blocker.signal_triggered
    emitted_batch = blocker.args[0]
    
    # Only the creation of 'main.py' should be reported (directories are ignored by default)
    assert len(emitted_batch) == 1
    assert emitted_batch[0]['action'] == 'created'
    assert Path(emitted_batch[0]['src_path']).name == 'main.py'
    
    watcher.stop()

def test_watcher_batches_events(temp_watched_dir, qtbot):
    """Check that a rapid burst of events results in a single batched emission."""
    watcher = FileWatcher(str(temp_watched_dir), [])
    watcher.poll_timer.setInterval(100) # Speed up for test

    with qtbot.waitSignal(watcher.fs_event_batch, timeout=1000) as blocker:
        watcher.start()
        (temp_watched_dir / "file1.txt").touch()
        (temp_watched_dir / "file2.txt").touch()
        (temp_watched_dir / "file3.txt").touch()

    assert blocker.signal_triggered
    emitted_batch = blocker.args[0]
    assert len(emitted_batch) == 3
    
    watcher.stop()

def test_watcher_emits_batch_with_polling_interval(temp_watched_dir, qtbot):
    """Ensure the batch is emitted based on the polling interval."""
    watcher = FileWatcher(str(temp_watched_dir), [])
    watcher.poll_timer.setInterval(150) # 150ms for test

    start_time = time.time()
    with qtbot.waitSignal(watcher.fs_event_batch, timeout=1000) as blocker:
        watcher.start()
        (temp_watched_dir / "a.txt").touch()

    end_time = time.time()
    emission_delay = end_time - start_time

    # The emission should happen after the timer interval.
    # Allow for some processing overhead.
    assert 0.15 <= emission_delay < 0.30
    assert blocker.signal_triggered
    
    watcher.stop()
