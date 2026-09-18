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
│   ├── main.py                     # CLI entry point (status, run, set-name, reset-config)
│   ├── core/
│   │   ├── application.py          # Application coordinator & graceful shutdown
│   │   ├── state.py                # StateMachine & ApplicationState enum
│   │   ├── events.py               # Event data model & EventType
│   │   ├── event_bus.py            # Async EventBus with subscriber isolation
│   │   └── exceptions.py           # Custom exception hierarchy
│   ├── config/
│   │   ├── schema.py               # Typed schemas (AppConfig, SystemConfig, ModelSlotConfig)
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
│   └── artifacts/                  # Decoupled filesystem directory for future media
├── logs/
│   └── kali_ai.log                 # Rotating application log file
├── scripts/
│   ├── run_status.sh               # Run status command
│   └── run_tests.sh                # Run unit test suite
├── tests/
│   ├── test_state.py               # State machine transition and callback tests
│   ├── test_event_bus.py           # Async pub/sub and isolation tests
│   ├── test_naming.py              # Naming derivation and customization protection
│   ├── test_config.py              # Configuration validation and persistence
│   ├── test_database.py            # SQLite transactions, migrations, and reopen tests
│   └── test_app.py                 # Full bootstrap, shutdown, and redaction tests
├── pyproject.toml                  # Package configuration
└── README.md
```

---

## Quick Start & CLI Usage

### 1. Check System Status & Diagnostics
```bash
python3 -m kali_ai status
# or
./scripts/run_status.sh
```

### 2. Customize Assistant Name
```bash
python3 -m kali_ai set-name "Athena"
```

### 3. Reset Configuration to Factory Defaults
```bash
python3 -m kali_ai reset-config
```

### 4. Run Assistant Daemon (Idle Mode)
```bash
python3 -m kali_ai
```

### 5. Run Automated Test Suite
```bash
python3 -m unittest discover tests -v
# or
./scripts/run_tests.sh
```

---

## Phase 2 Extension Points

Phase 1 exposes the following clean interfaces ready for Phase 2 (Voice & Wake-Word):
1. `AppConfig.voice`: Placeholder schema for wake word, STT provider, TTS provider, and VAD sensitivity.
2. `EventBus`: Ready to subscribe to `voice.wake_word_detected`, `voice.command_captured`, and `voice.speech_finished`.
3. `StateMachine`: Transitions `IDLE -> ACTIVE` upon verified wake detection and returns to `IDLE` upon completion.
4. `ConfigRepository`: Persists user-configured voice models, custom wake words, and audio preferences.
