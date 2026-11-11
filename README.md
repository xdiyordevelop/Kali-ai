# Kali AI - Personal AI Computer Assistant

A local-first, modular, extensible personal AI computer assistant engineered specifically for **Kali GNU/Linux Rolling** (GNOME Wayland / Mutter / PipeWire).

## Phase 1 Foundation Overview

Phase 1 provides the production-grade application lifecycle foundation:
* **Lifecycle State Machine**: Strict transition validation (`STARTING`, `IDLE`, `ACTIVE`, `PROCESSING`, `EXECUTING`, `PAUSED`, `STOPPING`, `STOPPED`, `ERROR`).
* **Asynchronous Event Bus**: High-performance pub/sub event bus with handler failure isolation, wildcard subscriptions, and event history ring buffer.
* **Deterministic Hostname-Based Naming**: Automatically derives human-friendly assistant names from the machine hostname while strictly protecting user customizations across system renames.
* **SQLite Configuration Database**: Parameterized, ACID-compliant storage in `data/config.db` using WAL mode and schema migration tracking.
* **Security Policy Foundation**: Tiered permission model (`TIER_0_READ_ONLY` to `TIER_3_HIGH_RISK`) with command blacklisting and emergency stop configuration.
* **Structured Observability**: Dual console and rotating file logging (`logs/kali_ai.log`) with automated credential/key redaction.
* **Zero External Dependencies**: Built entirely on the Python 3.14 standard library (`asyncio`, `dataclasses`, `sqlite3`, `logging`, `pathlib`), consuming <15 MB of RAM and ~0% idle CPU.

---

## Project Structure

```
Kali AI/
├── kali_ai/
│   ├── __init__.py
│   ├── __main__.py
│   ├── main.py                     # CLI entry point (status, voice, ai, set-name, reset-config)
│   ├── core/
│   │   ├── application.py          # Application coordinator & graceful shutdown
│   │   ├── state.py                # StateMachine & ApplicationState enum
│   │   ├── events.py               # Event data model & EventType
│   │   ├── event_bus.py            # Async EventBus with subscriber isolation
│   │   └── exceptions.py           # Exception hierarchy (AIError, ProviderError, etc.)
│   ├── ai/
│   │   ├── __init__.py             # Public AI Router exports
│   │   ├── types.py                # Typed AIMessage, AIRequest, AIResponse, AIUsage
│   │   ├── provider.py             # AIProvider base class & MockAIProvider
│   │   ├── router.py               # AIRouter with role routing, retries, and fallbacks
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── gemini.py           # Google Gemini provider (urllib.request, zero external deps)
│   │       └── openai.py           # OpenAI, Groq, Ollama compatible provider
│   ├── voice/
│   │   ├── audio.py                # PipeWire pw-record audio input
│   │   ├── vad.py                  # Energy-based Voice Activity Detection
│   │   ├── wake_word.py            # Offline Vosk small grammar wake-word detector
│   │   ├── pipeline.py             # VoicePipeline state machine & capture coordinator
│   │   ├── stt.py                  # STT abstraction & MockSTT
│   │   └── tts.py                  # TTS abstraction & MockTTS
│   ├── vision/
│   │   ├── __init__.py             # Public Vision subsystem exports
│   │   ├── types.py                # ScreenFrame, UIElement, UIElementType
│   │   ├── capture.py              # Wayland Mutter + PipeWire capture & MockScreenCapture
│   │   ├── cache.py                # Frame SHA-256 ObservationCache with TTL
│   │   ├── analyzer.py             # Multimodal AIVisionAnalyzer & MockVisionAnalyzer
│   │   ├── observer.py             # ScreenObserver (ObservationProvider)
│   │   └── verifier.py             # VisualTaskVerifier (TaskVerifier)
│   ├── control/
│   │   ├── __init__.py             # Public Computer Control exports
│   │   ├── types.py                # ControlAction, MouseButton, Coordinates, Result
│   │   ├── coordinates.py          # CoordinateMapper (canonical scaling & clamping)
│   │   ├── keys.py                 # KeyCodeMapper (XKB keysyms & hotkey parsing)
│   │   ├── interface.py            # ComputerControlInterface abstract base class
│   │   ├── lock.py                 # ComputerControlLock (single task concurrency lock)
│   │   ├── idle.py                 # HumanPriorityMonitor (Mutter IdleMonitor preemption)
│   │   ├── stale.py                # StaleCoordinateGuard (freshness threshold check)
│   │   ├── safety.py               # SecurityControlGate (permission tiers & blacklists)
│   │   ├── manager.py              # ComputerControlManager unified orchestrator
│   │   └── drivers/
│   │       ├── mutter.py           # WaylandMutterDriver (D-Bus RemoteDesktop session)
│   │       └── mock.py             # MockComputerControl (deterministic testing driver)
│   ├── config/

│   │   ├── schema.py               # Typed schemas (AppConfig, ScreenConfig, VisionConfig)
│   │   ├── settings.py             # Default paths and environment constants
│   │   └── manager.py              # Configuration manager with SQLite backing
│   ├── identity/
│   │   └── naming.py               # Deterministic naming engine from socket hostname
│   ├── storage/
│   │   ├── database.py             # SQLite manager with WAL mode and migrations
│   │   └── repositories.py         # ConfigRepository and SecurityPolicyRepository
│   ├── security/
│   │   └── policy.py               # PermissionTier and SecurityPolicyConfig
│   └── observability/
│       └── logging.py              # Structured logging and secret redactor
├── data/
│   ├── config.db                   # Permanent SQLite configuration database
│   ├── tasks.db                    # Permanent SQLite tasks database
│   ├── models/                     # Offline local models (Vosk small en-us)
│   └── artifacts/                  # Optional date-partitioned artifact directory
├── logs/
│   └── kali_ai.log                 # Rotating application log file
├── scripts/
│   ├── run_status.sh               # Run status command
│   └── run_tests.sh                # Run unit test suite
├── tests/
│   ├── test_state.py               # State machine transition tests
│   ├── test_event_bus.py           # Async pub/sub and isolation tests
│   ├── test_naming.py              # Naming derivation and customization tests
│   ├── test_config.py              # Configuration validation and persistence tests
│   ├── test_database.py            # SQLite transactions and migrations tests
│   ├── test_app.py                 # Full bootstrap and shutdown tests
│   ├── test_voice.py               # PipeWire mic, VAD, Vosk wake-word tests
│   ├── test_ai_router.py           # Multi-model routing, retries, fallbacks tests
│   ├── test_task_engine.py         # Task execution engine, planner, storage tests
│   └── test_vision.py              # Screen perception, Wayland capture, cache, analyzer tests
├── pyproject.toml                  # Package configuration
└── README.md
```

---

## Quick Start & CLI Usage

### 1. Check System Status & Diagnostics
```bash
python3 -m kali_ai status
```

### 2. Multi-Model AI Router Management
```bash
# View router status, configured providers, and capability slots
python3 -m kali_ai ai status

# List providers, endpoints, and credential status
python3 -m kali_ai ai providers

# View model routing assignments and fallback chains
python3 -m kali_ai ai models

# Test dispatch through the AI router
python3 -m kali_ai ai test --role fast --prompt "Hello! Respond with 'System OK'."
```

### 3. Voice Subsystem & Offline Wake-Word
```bash
# View voice status and detected microphone
python3 -m kali_ai voice status

# Local microphone hardware diagnostic (zero network, zero AI)
python3 -m kali_ai voice test

# Interactive live listening session
python3 -m kali_ai voice listen
```

### 4. Task Engine Management (Phase 4)
```bash
# List recent tasks
python3 -m kali_ai task list

# Filter tasks by status
python3 -m kali_ai task list --status COMPLETED

# Inspect detailed step-by-step report for a task
python3 -m kali_ai task status <task_id>

# Run interactive execution test (Observe -> Think -> Act -> Verify)
python3 -m kali_ai task test --mock-ai --goal "Verify system memory and swap usage"

# Pause, resume, or cancel a task
python3 -m kali_ai task pause <task_id>
python3 -m kali_ai task resume <task_id>
python3 -m kali_ai task cancel <task_id>
```

### 5. Screen Perception & Vision Subsystem (Phase 5)
```bash
# View screen perception status, backend availability, and model slots
python3 -m kali_ai vision status

# Capture a single live screen frame (pure RAM, zero disk write)
python3 -m kali_ai vision capture

# Capture and save a screenshot to a specific path
python3 -m kali_ai vision capture --output /tmp/desktop_frame.png

# Test end-to-end screen perception and UI element extraction
python3 -m kali_ai vision test --mock-ai
python3 -m kali_ai vision test --prompt "Identify active windows and terminal status"
```

### 6. Run Automated Test Suite
```bash
python3 -m unittest discover tests -v
# or
./scripts/run_tests.sh
```

---

## Phase 3 Multi-Model AI Router

The Multi-Model Router decouples application components and future agents from specific AI vendors:
* **Capability Roles**: Routes requests by abstract role (`REASONING`, `FAST`, `VISION`, `CODING`).
* **Seamless Fallback Chains**: Automatically cascades through secondary providers if the primary provider fails.
* **Automatic Retry with Backoff**: Transient errors (HTTP 429, 500, 502, 503, socket timeouts) are retried with exponential backoff before triggering fallback.
* **Non-Transient Fast-Fail**: Authentication errors (HTTP 401/403) and invalid requests (HTTP 400) immediately step to the next fallback without burning retries.
* **Zero External HTTP Dependencies**: Built entirely with Python 3.14 standard library `urllib.request` executed asynchronously via thread workers.
* **Zero Credential Leaks**: API keys are resolved exclusively from environment variables (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`) at runtime and are strictly excluded from configuration files, SQLite, logs, and EventBus payloads.

---

## Phase 4 Task Engine (Observe → Think → Act → Verify)

The Task Engine provides structured, autonomous multi-step execution for complex user goals:
* **Core Execution Loop**: Every step executes through `Observe → Think → Act → Verify`.
* **Dynamic Planning**: Deconstructs high-level goals into 1–5 atomic steps via `AITaskPlanner` (backed by Phase 3 `AIRouter` on `CapabilityRole.REASONING`) or deterministic `MockTaskPlanner`.
* **Automatic Retry with Re-observation**: If verification fails or is inconclusive, the engine re-observes the environment and retries up to `max_retries = 2` before failing.
* **Database Isolation**: All tasks, steps, and audit events are stored in dedicated `data/tasks.db` with WAL mode, keeping `data/config.db` clean and contention-free.
* **Crash Recovery**: Automatically detects tasks left in `RUNNING` state upon reboot/crash and transitions them safely to `RECOVERY_REQUIRED`.
* **Runtime Control**: Full support for pausing, resuming, user confirmation prompts (`ASK_USER` entering `WAITING_FOR_USER`), and idempotent cancellation.

---

## Phase 5 Vision & Screen Perception Subsystem

Phase 5 gives the assistant real-time desktop sight on Kali Linux GNOME Wayland while maintaining strict privacy and zero computer control:
* **Native Wayland Mutter + PipeWire Capture**: Leverages `org.gnome.Mutter.ScreenCast` on the user session D-Bus and PipeWire 1.6.8 via GStreamer 1.0 (`pipewiresrc ! videoconvert ! pngenc ! appsink`). Requires **zero root privileges**, **zero /dev/uinput access**, and **zero external pip packages**.
* **Ultra-Fast On-Demand Perception**: Captures 1280x720 PNG frames directly into RAM in ~75–120 ms. Only captures when perception is explicitly triggered (`observe()` or CLI command) — no continuous 60fps streaming or idle CPU load.
* **Strict Privacy Isolation**: Raw binary frame data is held strictly in RAM during perception and is **immediately wiped** (`frame.data = b""`). Screen frames are NEVER written to disk unless explicitly enabled via `artifact_storage_enabled=True`. Raw image bytes are NEVER published into the EventBus.
* **SHA-256 Observation Cache**: Computes the cryptographic SHA-256 hash of each captured frame and caches AI analysis results with a configurable TTL (default 5.0s). Consecutive static frames return instantly without making redundant, expensive AI calls.
* **Structured Multimodal AI Analysis**: Formulates multimodal vision requests across configured provider fallback chains (`CapabilityRole.VISION`: Gemini 2.5 Flash -> OpenAI GPT-4o), returning structured JSON with active applications, window titles, summaries, UI elements (with center coordinates), and visible text.
* **Visual Task Verification**: `VisualTaskVerifier` validates whether actions achieved expected visual results (focused apps, window titles, UI button elements, or terminal text) before marking task steps complete.
* **Strict Scope Boundaries**: Computer control (mouse clicks, typing, shortcuts) is strictly forbidden in Phase 5 and reserved for Phase 6.

---

## Phase 6 Computer Control / Mouse & Keyboard Automation

Phase 6 enables the assistant to safely control desktop inputs (mouse move, click, double-click, right-click, scroll; keyboard key_press, key_release, type_text, hotkey; system commands) on Kali Linux GNOME Wayland while enforcing multi-layered safety guardrails:

* **Native Wayland Mutter RemoteDesktop**: Leverages `org.gnome.Mutter.RemoteDesktop` paired with `org.gnome.Mutter.ScreenCast` on the user session D-Bus. Injects pointer motion (`NotifyPointerMotionAbsolute`), evdev mouse buttons (`NotifyPointerButton`), pointer axis scrolling (`NotifyPointerAxisDiscrete`), and XKB keysyms (`NotifyKeyboardKeysym`) with **zero root/sudo privileges**, **zero /dev/uinput**, and **zero external automation frameworks** (no PyAutoGUI, no Selenium).
* **Canonical Coordinate Scaling & Bounds Clamping**: `CoordinateMapper` translates coordinates across physical resolution ($1920 \times 1080$), Wayland display scaling ($1.25\times$), and normalized model coordinates ($[0..1000] \times [0..1000]$) into clamped logical pixels ($1536 \times 864$), preventing out-of-bounds pointer drift.
* **Human Priority Preemption**: `HumanPriorityMonitor` interfaces directly with `org.gnome.Mutter.IdleMonitor` (`/org/gnome/Mutter/IdleMonitor/Core`). Automatically registers `AddUserActiveWatch()` and checks `GetIdletime()`. If a human user touches the physical mouse or keyboard, automation immediately yields and raises `HumanInterruptionError` — **the human always has absolute priority**.
* **Zero Stuck Keys / Stuck Buttons Guarantee**: All pressed mouse buttons and modifier keys are tracked in active sets and unconditionally released in `finally` blocks, shutdown routines, and emergency stops (`release_all()`).
* **Computer Control Lock**: `ComputerControlLock` acts as an exclusive mutual exclusion gate ensuring only one automated task drives input at any moment, eliminating race conditions.
* **Stale Coordinate Protection**: `StaleCoordinateGuard` verifies the timestamp freshness of visual observations. Target coordinates older than $5.0\text{s}$ are rejected (`StaleCoordinateError`), enforcing re-observation before clicking.
* **Security Permission Tiers & Blacklist**: `SecurityControlGate` enforces security tiers:
  - `TIER_0_READ_ONLY`: Blocks all modifying clicks, typing, and commands.
  - `TIER_1_STANDARD`: Permits standard UI clicks and typing.
  - `TIER_2_SENSITIVE`: Requires confirmation if policy dictates.
  - `TIER_3_HIGH_RISK`: Blocks dangerous commands (`rm -rf /`, `mkfs`) and requires user confirmation.
* **CLI Management**:
  - `kali-ai control status`: Displays driver, display resolution, scaling, idletime, lock state, and security tier.
  - `kali-ai control test [--dry-run] [--x X] [--y Y]`: Runs diagnostic pointer movement and key injection.
  - `kali-ai control emergency-stop`: Immediately force-breaks input locks, releases all virtual keys/buttons, and halts active tasks.
* **Test Suite**: 142/142 tests passing across Phases 1–6 with 100% regression-free backward compatibility.

---

## Phase 7 Multi-Agent System

Phase 7 introduces specialized AI agents that act as domain experts determining *WHAT* should be done, while strictly preserving architectural boundaries:

* **Separation of Responsibilities**:
  - **Agent**: Specialist (*WHAT* should be done — reasoning, domain intent, capability declaration, plan synthesis).
  - **TaskEngine**: Executor (*HOW* the task steps are executed — Observe $\to$ Think $\to$ Act $\to$ Verify cycle).
  - **AIRouter**: Model Selector (*WHICH* AI model helps — `CapabilityRole.CODING`, `REASONING`, `FAST`, `VISION`).
  - **SecurityPolicy**: Authority (*IS* the action allowed — independent permission tier validation, confirmation gates, command blacklists).
  - **ComputerControl**: Actuator (*HOW* the desktop is physically controlled — Mutter RemoteDesktop / ScreenCast).

* **8 Specialized Agents**:
  1. `GeneralAgent` (Fallback coordinator for broad queries and routing handoff; Tier 1)
  2. `CodingAgent` (Code generation, debugging, refactoring, test execution; `CapabilityRole.CODING`; Tier 2)
  3. `ResearchAgent` (Documentation lookup, web research, technical summarization; `CapabilityRole.REASONING`; Tier 0)
  4. `BrowserAgent` (Browser automation, web navigation, DOM/screen interaction; `CapabilityRole.FAST`; Tier 1)
  5. `FileAgent` (Filesystem operations, directory management, reading, copying, moving, safe deletion; Tier 2/3)
  6. `ComputerControlAgent` (Desktop GUI control, mouse clicks, keyboard typing; `CapabilityRole.VISION`; Tier 1)
  7. `SystemAgent` (System monitoring: CPU, RAM, disk, processes, OS diagnostics; Tier 0 Read-Only by default)
  8. `AutomationAgent` (Task scheduling, recurring automations, and workflow orchestration; Tier 2)

* **Multi-Agent Core Engine**:
  - `AgentRegistry`: Central agent management, lookup, duplicate prevention, dynamic config enablement, and health telemetry.
  - `AgentRouter`: Semantic intent analysis + LLM classification (`CapabilityRole.FAST`) matching user goals to domain specialists with structured explainability and disabled agent fallback chains.
  - `AgentCoordinator`: Multi-agent collaboration pipelines (e.g. Research $\to$ Coding $\to$ TaskEngine) enforcing maximum delegation depth ($\le 3$) and rejecting circular loops ($A \to B \to A$) via `AgentDelegationLimitError`.
  - `AgentSecurityGate`: Enforces effective permission $\min(\text{user\_permission}, \text{agent\_permission})$, verifies declared capabilities, protects against privilege escalation, and redacts credentials and tokens.

* **CLI Commands**:
  ```bash
  # List all registered specialist agents
  python3 -m kali_ai agents list

  # Display detailed agent health, capabilities, and lifecycle states
  python3 -m kali_ai agents status

  # Dry-run routing analysis explaining which agent is selected and why
  python3 -m kali_ai agents route "write a python script to parse logs"

  # Run end-to-end multi-agent test execution pipeline via TaskEngine
  python3 -m kali_ai agents test
  python3 -m kali_ai agents test --dry-run
  ```

* **Test Suite**: 167/167 tests passing across Phases 1–7 with 100% regression-free backward compatibility.

---

## Phase 8 Context & Memory System

Phase 8 implements a unified long-term and working memory architecture for Kali AI, enabling contextual recall, cross-agent knowledge sharing, and privacy-conscious retention without heavy external vector databases:

* **Two-Tier Memory Architecture**:
  - **Working Memory (In-RAM)**: Fast bounded ring buffer of recent conversational dialog turns, user goals, and execution thoughts, with automated consolidation of older turns into episodic summaries.
  - **Long-Term Memory (SQLite WAL)**: Dedicated persistent storage in `data/memory.db` with SQLite FTS5 (full-text search) and zero-dependency semantic vector embeddings. Completely isolated from `config.db` and `tasks.db`.

* **Zero-Dependency Semantic Vector Search**:
  - Offline in-process vectorizer using word and subword character 3-gram feature hashing to normalized fixed-dimension vectors ($L_2 = 1.0$).
  - Fast cosine similarity computation in pure Python without heavy ML frameworks (no PyTorch, Hugging Face, ChromaDB, Pinecone, or LangChain).
  - Hybrid retrieval combining SQLite FTS5 BM25 rank, vector cosine similarity, and recency/importance bonuses.

* **Privacy & 14-Day Retention**:
  - Configurable TTL (default 14 days) for conversation history.
  - Permanent preservation for preferences and critical knowledge (`importance >= 0.8`).
  - Automated `cleanup_expired()` removing obsolete entries without user intervention.

* **Secret Hygiene & Boundary Enforcement**:
  - `MemorySecurityFilter` automatically scans and redacts API keys (`sk-...`, `AIza...`, `ghp_...`), Bearer tokens, passwords, and private keys before persistence or logging.
  - Scope boundaries (`GLOBAL`, `AGENT`, `SESSION`) enforce inter-agent namespace isolation and prevent unauthorized cross-agent access.

* **CLI Commands**:
  ```bash
  # Display memory subsystem status, storage stats, and retention settings
  python3 -m kali_ai memory status

  # List stored memories with optional type filter
  python3 -m kali_ai memory list --type preference --limit 10

  # Search memories using hybrid FTS5 and semantic vector retrieval
  python3 -m kali_ai memory search "terminal theme"

  # Store a new fact or preference with automatic secret redaction
  python3 -m kali_ai memory add "User prefers dark mode and fish shell" --type preference --permanent

  # Trigger TTL retention cleanup of expired memories
  python3 -m kali_ai memory cleanup
  ```

* **Test Suite**: 187/187 tests passing across Phases 1–8 with 100% regression-free backward compatibility.

---

## Phase 9 Visual UX — Siri-Style Overlay & Control Center Dashboard

Phase 9 implements a native, modern visual interface for Kali Linux GNOME Wayland:

* **1. Siri-Style Assistant Overlay Window**:
  - Floating, translucent rounded card positioned gracefully on the desktop.
  - Activates automatically when the wake word "Sandy" is spoken, or via CLI.
  - Smooth lifecycle transitions:
    $$\text{✦ Sandy} \to \text{🎙 Listening...} \to \text{⚙ Processing...} \to \text{▶ Executing... [Step } i/N \text{]} \to \text{✓ Done!} \to \text{Auto-dismiss}$$
  - Live progress bar, active task step indicator, and auto-dismiss countdown.

* **2. Control Center / Dashboard Window**:
  - Full desktop control center built with native GTK 4 and Libadwaita (`Adw.ApplicationWindow`).
  - Left navigation sidebar with 8 functional panels:
    1. **Dashboard**: System health, CPU/RAM, active tasks, voice status, quick prompt launcher.
    2. **Tasks**: Live active task list with progress bar, step inspection, Pause / Resume / Cancel controls.
    3. **Screen**: Live screen perception inspector with refresh and element detection list.
    4. **Agents**: Specialist agents registry, capability badges, and interactive routing tester.
    5. **Models**: AI providers and capability model slots status.
    6. **Memory**: Long-term memory browser, FTS5 search, and knowledge addition input.
    7. **Security**: Current permission tier, emergency stop button, and blocked operations audit.
    8. **Logs**: Real-time scrolling system log viewer.

* **3. UI Event Bridge (`kali_ai/ui/bridge.py`)**:
  - Non-blocking, thread-safe synchronization between the asynchronous backend (`EventBus`, asyncio loop) and the GTK4 main loop (`GLib.idle_add`).
  - Seamless bidirectional communication: backend events immediately update the GUI, while GUI button clicks (Pause, Resume, Cancel, Emergency Stop) safely dispatch to the backend asyncio task engine.
  - Zero heavy external frameworks: 100% native PyGObject (`Gtk 4.0`, `Adw 1`, `GLib 2.0`), consuming $< 25\text{ MB}$ RAM.

* **CLI Commands**:
  ```bash
  # Launch the Control Center Dashboard
  python3 -m kali_ai ui
  python3 -m kali_ai ui --tab tasks

  # Launch the Siri-style Assistant Overlay
  python3 -m kali_ai overlay

  # Run the Kali AI background daemon with the Assistant Overlay active
  python3 -m kali_ai run --ui
  ```

* **Test Suite**: **205/205 tests passing** across all 9 phases in 5.3s with zero regressions.

# Kali-ai
