Product Requirements Document (PRD)  
Application: “Context-M” – A Desktop Code-Aggregation & LLM-Context Builder  

Version: 1.0  
Author: Product Team  
Date: 2025-07-18  

────────────────────────────────────────  
1. Executive Summary  
Context-M is a cross-platform desktop utility that scans a local source-code directory, lets the user cherry-pick files/folders, and then bundles the contents together with a user-supplied prompt (the “context block”) into a single text artifact.  
The artifact is formatted for immediate consumption by Large-Language-Models (ChatGPT, Claude, Gemini, etc.) or for storage in a knowledge-base.  
Key value props:  
• 30-second setup → 1-click copy-to-clipboard  
• Persistent “workspaces” that remember folder, scan rules, file selection, and prompt templates  
• Token-aware UI (tiktoken) to stay inside model limits  
• Extensible “custom instruction” templates to standardise prompts across teams  

────────────────────────────────────────  
2. Vision & Purpose  
“Make any local codebase LLM-ready in under a minute.”  
Engineers, tech-writers, and AI-pair-programmers use Context-M to:  
• Produce concise context packets for bug triage  
• Generate embedding corpora for RAG pipelines  
• Share reproducible code snippets in PRDs or StackOverflow questions  

────────────────────────────────────────  
3. Target Users & Personas  
P1 – Solo Developer  
Needs: quick prompt + selected files → clipboard  
P2 – AI Engineer / Data-Scientist  
Needs: repeatable extraction rules, token budgets, headless usage  
P3 – Technical Writer / QA  
Needs: rich workspace history, diff-friendly snapshots  

────────────────────────────────────────  
4. Core Use-Cases  
UC-1  “One-shot Export”  
1. Launch → Select folder  
2. Scan finishes (visually)  
3. Check desired files  
4. Copy → Paste into ChatGPT  

UC-2  “Workspace Flow”  
1. Create workspace “Backend-v2”  
2. Save scan settings (ignore node_modules, max 200 KB files)  
3. Save prompt template “Add OpenAPI annotations”  
4. Re-open workspace tomorrow → selection & prompt restored  

UC-3  “Template Library”  
1. Open “Manage Instructions”  
2. Add template “Rust Review Checklist”  
3. Team-mates load the template from dropdown  

────────────────────────────────────────  
5. Functional Requirements  
F1  Directory Scanning  
• Recursive walk with configurable ignore list (glob & folder name)  
• Detect text vs binary via libmagic → fallback to UTF-8 heuristic  
• Skip hidden files, respect .gitignore (future)  
• Real-time progress indicator  

F2  Token Calculation  
• tiktoken cl100k_base encoding  
• Display per-file and aggregate token counts  
• Warn if > context-window (user-configurable)  

F3  UI – Tree View  
• Lazy-loaded tree with checkboxes  
• Tri-state folder checkboxes (check/uncheck children)  
• Visual badges: “Skipped – binary”, “Permission denied”  

F4  Aggregation Format  
• Stable deterministic order (alphabetical)  
• File tree header block  
• Each file wrapped in markdown fenced code block with language tag  
• Truncation notice if file > MAX_FILE_SIZE_KB  

F5  Clipboard & File Export  
• Single button “Copy to Clipboard” (pyperclip)  
• Optional “Save as .md” (future)  

F6  Workspace Persistence  
• JSON file: workspaces.json, custom_instructions.json  
• Fields: folder_path, scan_settings, checked_paths (relative), instruction_text  
• Auto-restore on app launch  

F7  Custom Instruction Templates  
• CRUD dialog for named prompts  
• Dropdown insertion into main prompt box  
• “Default” template protected from deletion  

F8  Refresh / Change Detection  
• Manual refresh button triggers re-scan  
• Diff dialog: new files vs missing files → opt-in selection merge  

────────────────────────────────────────  
6. Non-Functional Requirements  
NFR-1  Performance  
• Scan 10 000 files < 3 s on M2 MacBook  
• UI responsive during scan (batch emit every 100 items)  

NFR-2  Compatibility  
• Windows 10+, macOS 12+, Ubuntu 22+  
• Python 3.10+ runtime bundled via PyInstaller / Nuitka  

NFR-3  Extensibility  
• Plugin interface (future) – custom post-processors  

NFR-4  Accessibility  
• Qt high-DPI aware, keyboard navigation  

NFR-5  Security / Privacy  
• No network calls unless user explicitly installs Supabase plugin (see package.json)  
• No telemetry by default (opt-in analytics toggle)  

────────────────────────────────────────  
7. UI/UX Specification  
Visual Style: Dark-first theme, native OS widgets (Qt Fusion style).  
Layout:  
• Left 40 % – collapsible directory tree  
• Right 60 % – vertical splitter  
  – Top: instruction template dropdown + textarea (min-height 80 px)  
  – Bottom: read-only aggregation preview (monospace)  
• Toolbar: Workspaces, Select Folder, Refresh, Copy  

Colours & Icons:  
• Folder – SP_DirIcon  
• File – SP_FileIcon  
• Error – #ff5252  
• Token count label – #00bcd4  

────────────────────────────────────────  
8. Architecture & Tech Stack  
Language: Python 3.10  
GUI: PySide6 (Qt 6)  
Threading: QThread for non-blocking scans  
Key Libraries:  
• tiktoken – token counting  
• python-magic – mime detection  
• pyperclip – clipboard  
Persistence: JSON (human-readable, git-friendly)  
Build: pyinstaller → single executable  

Directory layout (source):  
contextMNew/  
├─ main.py               # QMainWindow, event loop  
├─ directory_scanner.py  # QThread + os.walk  
├─ custom_instructions_dialog.py  
├─ scan_config_dialog.py  
├─ workspace_dialog.py  
├─ helpers.py            # is_text_file, calculate_tokens  
├─ requirements.txt  
└─ *.json (runtime configs)  

────────────────────────────────────────  
9. Open Issues / Future Backlog  
• .gitignore support  
• Watchdog real-time file watcher  
• Headless CLI mode  
• Cloud workspace sync (Supabase integration stub present)  
• Drag-and-drop reordering of files in tree  

────────────────────────────────────────  
10. Success Metrics (6-month post-launch)  
M1  Median time from “open app” to “clipboard” < 45 s (instrumented telemetry)  
M2  ≥ 4.5/5 average rating on internal tooling survey  
M3  ≥ 30 % of engineering org using weekly (workspace count)