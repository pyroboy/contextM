follow the instructions of the following 


Feature Specification – Live File Watcher  
(for AI agent implementation)

Overview  
Whenever the currently open workspace folder is changed by any external process (create, delete, rename, move, permission change), Context-M must automatically update its tree, token counts, and the aggregation text box without user interaction. The update must respect the same ignore rules already used for the initial scan.

Detailed Behaviour

1. Activation  
   • Controlled by a boolean flag live_watcher stored in each workspace’s scan_settings.  
   • Default value: true.  
   • Flag is surfaced as a checkbox in ScanConfigDialog.

2. Watch Scope  
   • Root path = workspace.folder_path.  
   • Ignore rules = workspace.scan_settings.ignore_folders plus hidden-file rule (name starts with “.”).  
   • Any path whose absolute or relative location matches an ignore rule must be silently discarded before the event reaches the UI layer.

3. Event Sources & Actions  
   Added file/dir → insert into tree, mark unchecked, recompute parent folder tokens.  
   Deleted file/dir → remove tree item, recompute parent folder tokens.  
   Moved file/dir → treat as delete at old path + add at new path; preserve check state if the new path is still valid.  
   Modified file → re-tokenise, update token count, refresh aggregation only if file is currently checked.

4. Batching & Performance  
   • All events received within 200 ms are coalesced into a single batch.  
   • The batch is emitted once via a queued Qt signal to guarantee GUI-thread execution.  
   • CPU spike on large mono-repos must stay < 10 % (tested with 100 000 files).

5. UI Updates  
   • Tree widget reflects new/removed items immediately.  
   • “TOTAL / SELECTED” labels on folders are recalculated.  
   • Aggregation text box is regenerated in the background without user intervention.  
   • Status bar shows a transient message:  
     “Directory updated – 3 added, 1 removed, 0 modified | 2 still missing”  
     Auto-clear after 4 s.

6. Robustness  
   • Network drives: automatically fall back to PollingObserver if root path starts with “\\” or “/mnt/”.  
   • Observer stops cleanly on workspace switch or application exit.  
   • No GUI freezes (all mutations queued to main thread).

7. Persistence  
   • live_watcher flag saved and loaded with the workspace JSON.  
   • If the flag is toggled off, the watcher stops immediately and no events are processed.
1. requirements.txt  
   append line: watchdog~=3.0

2. file_watcher.py (new)  
   • thin QThread wrapper around watchdog Observer  
   • accepts root path + ignore-rules set  
   • filters events against ignore/hidden rules  
   • coalesces bursts with 200 ms timer  
   • emits batched Qt signal: path, action, src_path, dst_path  
   • graceful stop & join on thread exit

3. scan_config_dialog.py (edit)  
   • add checkbox “Enable live file watcher”  
   • load/save boolean “live_watcher” into/ from scan_settings dict

4. main.py (edit)  
   • import FileWatcherThread  
   • new ivar self.file_watcher  
   • start/stop watcher in _switch_workspace and closeEvent according to workspace flag  
   • new slot on_fs_event_batch:  
     – update tree_items via existing helpers  
     – recompute folder token counts  
     – recompute selected tokens  
     – call update_aggregation_and_tokens  
   • new helper show_status(msg, ms) for status-bar messages  
   • format and display “Directory updated – X added, Y removed, Z modified” after every batch

5. workspaces.json schema (implicit)  
   • scan_settings dict now contains boolean key "live_watcher" persisted per workspace