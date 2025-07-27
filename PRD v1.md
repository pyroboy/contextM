Product Requirements Document: Context-M
Version: 2.0

Status: Proposed

Author: Product Team

1. Introduction & Vision 🚀
Context-M is a cross-platform desktop utility for developers, AI engineers, and technical writers. It scans local codebases, enables intelligent file selection, and aggregates the content into a single, token-aware text block, perfectly formatted for use with Large Language Models (LLMs).

Vision Statement: To be the fastest, most intuitive tool for crafting perfect, reproducible LLM context from any local codebase. We bridge the gap between local development environments and generative AI, making context-building a seamless part of the modern developer workflow.

2. Target Audience & Personas
P1: The Pragmatic Developer (Primary)

Needs: Quickly grab a set of files related to a feature or bug, add a short prompt, and paste it into an LLM for debugging, refactoring, or documentation. Values speed and minimal friction above all.

Pain Point: Manually copying and pasting multiple files is tedious, error-prone, and loses file structure context.

P2: The AI Engineer / RAG Specialist

Needs: Repeatable, configurable methods for extracting code and text to build datasets for training, testing, or RAG (Retrieval-Augmented Generation) pipelines. Values precision, configuration, and persistence.

Pain Point: Scripts for data extraction are time-consuming to write and maintain for each new project.

P3: The Technical Writer / QA Engineer

Needs: To capture a precise snapshot of code related to a specific feature or user manual section. They need to be able to save and revisit these selections.

Pain Point: Keeping track of which file versions were used for documentation or bug reports is difficult.

3. Guiding Principles
These principles will guide all design and development decisions.

Performance is a Feature: The application must feel instantaneous. Startup, scanning, and UI updates must be non-blocking and optimized for large codebases.

Clarity Over Clutter: The UI must be clean, intuitive, and self-explanatory. Every feature should serve a clear purpose and be easily discoverable.

Save State, Not Snapshots: The core persistence philosophy. Only user-defined configurations (paths, settings, instructions) are ever saved to disk. All UI artifacts (the file tree, token counts, aggregated text) are ephemeral and regenerated from the source files on every scan. This guarantees the context is always fresh and accurate.

4. Functional Requirements
F1: Workspace Management
A Workspace is the primary unit of organization, representing a saved state for a specific project or task.

F1.1: Create, Rename, Delete: Users can create, rename, and delete workspaces through a dedicated manager UI. A "Default" workspace cannot be deleted.

F1.2: Atomic Switching: Switching between workspaces is an atomic operation. The application must first save the complete state of the current workspace (selections, instructions) before loading the complete state of the destination workspace.

F1.3: State Restoration: On switching to a workspace, the application must automatically restore the saved folder_path, all scan_settings, the active selection_group, and the instructions text.

F1.4: Session Persistence: The application must automatically load the last active workspace on startup.

F2: Directory Scanning Engine
The engine is responsible for reading the file system and providing data to the UI.

F2.1: Non-Blocking Scan: All scanning and tokenization operations must run in a background process to keep the UI 100% responsive at all times.

F2.2: Configurable Ignore Rules: The scan must respect a set of user-configurable ignore rules, including:

Specific folder names (e.g., node_modules, __pycache__).

Hidden files and folders (names starting with a .).

F2.3: .gitignore Support: The scanner must automatically detect and apply the rules found in .gitignore files within the workspace's folder path. This is a baseline expectation for a developer tool.

F2.4: Binary/Large File Handling: The scanner will intelligently skip files that are detected as binary or exceed a size threshold (e.g., 200 KB) to maintain performance. The reason for skipping (e.g., "Binary File", "Too Large") should be displayed in the UI.

F3: File Tree View & Selection
The primary interface for interacting with the scanned codebase.

F3.1: High-Performance Tree: The file tree must be implemented using a Model/View architecture (QTreeView) to handle repositories with 10,000+ files without UI lag.

F3.2: Checkbox Selection: Every file and folder will have a checkbox.

Checking/unchecking a folder recursively applies that state to all its children.

Checking/unchecking a child updates the parent folder's state (checked, unchecked, or partially checked).

F3.3: Token Count Display:

Files: Display the token count calculated via tiktoken cl100k_base.

Folders: Display the sum of tokens of all files within that folder.

F3.4: Selection Groups: Users can save and load different sets of checked files as named "Selection Groups" within a single workspace. This allows for quick switching between different contexts (e.g., "Frontend Files," "API Routes," "Database Schema").

F4: Live File Watcher (Active Monitoring)
Keeps the UI in sync with the file system in real-time.

F4.1: Automatic Updates: The application will monitor the workspace folder for changes (creations, deletions, modifications, renames).

F4.2: Batched Events: To ensure performance, all file system events detected within a short window (e.g., 200ms) will be coalesced into a single batch for UI processing.

F4.3: Intelligent UI Refresh: The UI will update intelligently. For example, a file modification should only trigger re-tokenization and update the aggregation view if that file is currently checked.

F4.4: UI Indicator: A subtle but clear indicator in the status bar will show when the live watcher is active.

F5: Instructions & Prompt Engineering
The central location for providing context and instructions to the LLM.

F5.1: Instructions Panel: A dedicated text area where the user writes their primary prompt or system instructions. This text is saved per-workspace.

F5.2: Template System: A dropdown menu allows users to quickly insert pre-written text (templates) into the instructions panel.

F5.3: Global & Local Templates: The application will support two scopes for templates:

Global: Stored in custom_instructions.json; available across all workspaces.

Workspace-Specific: Saved within the workspace's data in workspaces.json; only available to that workspace. A checkbox will toggle between the two scopes.

F6: Context Aggregation & Output
Defines the final text artifact generated by the application.

F6.1: Deterministic Output: The aggregated output must be stable and deterministic, with files sorted alphabetically.

F6.2: Standardized Formatting: The final text block will be formatted as follows:

(Optional) System Prompt: The text from the instructions panel.

File Tree Header: An ASCII-art style tree showing the relative paths of all included files.

File Contents: Each file's content will be wrapped in a markdown fenced code block, with the language inferred from the file extension.

Markdown

--- System Prompt ---
[Your instructions here...]

--- File Tree ---
my-project/
├── src/
│   └── main.py
└── README.md

---

`src/main.py`
```python
print("Hello, World!")
README.md

Markdown

# My Project
This is a test project.
F6.3: One-Click Copy: A prominent "Copy to Clipboard" button will place the entire formatted text onto the system clipboard.

F7: Persistence Model
Defines the on-disk data structure, governed by the "Save State, Not Snapshots" principle.

F7.1: workspaces.json Schema: The single source of truth for all user-defined state.

JSON

{
  "schema_version": 1,
  "last_active_workspace": "MyProject",
  "workspaces": {
    "MyProject": {
      "folder_path": "/path/to/my/project",
      "instructions": "Analyze this code for bugs.",
      "scan_settings": {
        "include_subfolders": true,
        "live_watcher": true,
        "ignore_folders": [".git", "node_modules"]
      },
      "active_selection_group": "API Files",
      "selection_groups": {
        "Default": {
          "description": "Default selection",
          "checked_paths": ["README.md"]
        },
        "API Files": {
          "description": "All files for the main API.",
          "checked_paths": ["src/api/server.js", "src/api/routes.js"]
        }
      }
    }
  }
}
F7.2: Atomic Saves & Backups: All saves to workspaces.json must be atomic (write to a temp file, then rename) to prevent corruption. The application will also maintain rolling backups of this file.

5. Non-Functional Requirements
NFR-1: Performance

Cold Start: Application window should be visible and interactive in < 1 second.

Scan Speed: Scan a repository with 10,000 files in < 3 seconds on a modern machine (e.g., Apple M1 or equivalent).

UI Responsiveness: The UI must never freeze or stutter during scanning, file watching, or aggregation. All expensive operations must be off the main thread.

NFR-2: Usability & UX

Layout: A three-pane layout: a persistent left pane for the file tree and selection groups, and a split right pane for instructions and the final aggregation preview.

Theme: Dark-first theme, using native OS widgets where possible for a familiar feel.

Keyboard Navigation: Full keyboard accessibility for navigating the tree, checking/unchecking items, and triggering core actions.

NFR-3: Compatibility

OS: Windows 10+, macOS 12+, Ubuntu 22.04 LTS.

Runtime: Python 3.10+.

6. Future Roadmap (Post-V2.0 Backlog)
Headless CLI Mode: A command-line interface to run scans and generate context non-interactively for scripting and automation.

Cloud Workspace Sync: Optional integration with a service like Supabase to sync workspaces.json across multiple machines.

Diff-Aware Selections: When refreshing a scan, show a diff of new, modified, and deleted files, allowing the user to intelligently merge changes into their existing selection.

7. Success Metrics
M1: Task Completion Rate: >95% of users can successfully select a folder, check at least one file, and copy the context to their clipboard in a new session.

M2: Time to Context: The median time from launching the application to copying the context should be < 45 seconds for a returning user.

M3: User Retention: >30% of users who create more than one workspace return to use the application weekly.