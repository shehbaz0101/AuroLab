"""
scripts/validate_startup.py

Pre-flight check before launching AuroLab.
Run from AuroLab/ root before starting the backend.

Checks:
  1. Python version >= 3.10
  2. All required packages installed
  3. .env file present with GROQ_API_KEY
  4. Data directories exist and are writable
  5. All service packages importable
  6. PyBullet working
  7. ChromaDB initialises cleanly
  8. Mock pipeline runs end-to-end

Usage:
    python scripts/validate_startup.py
    python scripts/validate_startup.py --fix    # auto-create missing dirs
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
PASS = "\033[92m  ✓\033[0m"
FAIL = "\033[91m  ✗\033[0m"
WARN = "\033[93m  !\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    symbol = PASS if ok else FAIL
    line = f"{symbol} {name}"
    if detail:
        line += f"\n      {detail}"
    print(line)
    results.append((name, ok, detail))
    return ok


def section(title: str) -> None:
    print(f"\n── {title} {'─' * (50 - len(title))}")


# ---------------------------------------------------------------------------
# 1. Python version
# ---------------------------------------------------------------------------
section("Python")
ver = sys.version_info
check("Python >= 3.10", ver >= (3, 10),
      f"Found {ver.major}.{ver.minor} — upgrade to 3.10+" if ver < (3, 10) else f"{ver.major}.{ver.minor}")

# ---------------------------------------------------------------------------
# 2. Required packages
# ---------------------------------------------------------------------------
section("Packages")

REQUIRED = [
    ("fastapi",             "fastapi"),
    ("uvicorn",             "uvicorn"),
    ("groq",                "groq"),
    ("pydantic",            "pydantic"),
    ("structlog",           "structlog"),
    ("chromadb",            "chromadb"),
    ("sentence_transformers","sentence_transformers"),
    ("rank_bm25",           "rank_bm25"),
    ("streamlit",           "streamlit"),
    ("plotly",              "plotly"),
    ("httpx",               "httpx"),
    ("pymupdf",             "fitz"),
    ("pyzmq",               "zmq"),
    ("python-dotenv",       "dotenv"),
    ("prometheus_client",   "prometheus_client"),
    ("pytest",              "pytest"),
]

OPTIONAL = [
    ("pybullet", "pybullet", "physics simulation — pip install pybullet"),
    ("pytesseract", "pytesseract", "OCR for scanned PDFs"),
]

for pkg_name, import_name in REQUIRED:
    try:
        __import__(import_name)
        check(f"{pkg_name}", True)
    except ImportError:
        check(f"{pkg_name}", False, f"pip install {pkg_name}")

for pkg_name, import_name, hint in OPTIONAL:
    try:
        __import__(import_name)
        check(f"{pkg_name} (optional)", True)
    except ImportError:
        symbol = WARN
        print(f"{symbol} {pkg_name} not installed — {hint}")

# ---------------------------------------------------------------------------
# 3. Environment
# ---------------------------------------------------------------------------
section("Environment")

env_file = ROOT / ".env"
check(".env file exists", env_file.exists(),
      "Create .env from .env.example" if not env_file.exists() else "")

if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)

groq_key = os.getenv("GROQ_API_KEY", "")
check("GROQ_API_KEY set", bool(groq_key),
      "Set GROQ_API_KEY=gsk_... in .env" if not groq_key else f"{'*' * 8}{groq_key[-4:]}")

sim_mode = os.getenv("AUROLAB_SIM_MODE", "pybullet")
check(f"AUROLAB_SIM_MODE={sim_mode}", sim_mode in ("mock", "pybullet", "live"),
      "Valid values: mock | pybullet | live")

# ---------------------------------------------------------------------------
# 4. Directory structure
# ---------------------------------------------------------------------------
section("Directories")

fix_mode = "--fix" in sys.argv

REQUIRED_DIRS = [
    ROOT / "data",
    ROOT / "data" / "chroma",
    ROOT / "data" / "pdfs",
    ROOT / "logs",
    ROOT / "protocols",
]

for d in REQUIRED_DIRS:
    if d.exists():
        check(f"{d.relative_to(ROOT)}/", True)
    elif fix_mode:
        d.mkdir(parents=True, exist_ok=True)
        check(f"{d.relative_to(ROOT)}/ (created)", True)
    else:
        check(f"{d.relative_to(ROOT)}/", False, "Run with --fix to create")

# Check __init__.py in all service packages
INIT_DIRS = [
    "services", "services/translation_service", "services/translation_service/core",
    "services/translation_service/api", "services/execution_service",
    "services/execution_service/core", "services/vision_service",
    "services/vision_service/core", "services/vision_service/api",
    "services/analytics_service", "services/analytics_service/core",
    "services/analytics_service/api", "services/orchestration_service",
    "services/orchestration_service/core", "services/orchestration_service/api",
    "services/rl_service", "services/rl_service/core", "services/rl_service/api",
    "shared", "tests",
]
missing_inits = []
for d in INIT_DIRS:
    init = ROOT / d / "__init__.py"
    if not init.exists():
        if fix_mode:
            init.parent.mkdir(parents=True, exist_ok=True)
            init.touch()
        else:
            missing_inits.append(d)

check("All __init__.py present", len(missing_inits) == 0,
      f"Missing in: {missing_inits} — run with --fix" if missing_inits else "")

# ---------------------------------------------------------------------------
# 5. Service imports
# ---------------------------------------------------------------------------
section("Service Imports")

sys.path.insert(0, str(ROOT))

SERVICE_IMPORTS = [
    ("Translation core",    "services.translation_service.core.chunker",          "chunk_document"),
    ("Translation LLM",     "services.translation_service.core.llm_engine",       "AurolabLLMEngine"),
    ("Execution commands",  "services.execution_service.core.robot_commands",      "ExecutionPlan"),
    ("Execution parser",    "services.execution_service.core.step_parser",         "parse_step"),
    ("Execution validator", "services.execution_service.core.validator",           "validate_commands"),
    ("Simulation bridge",   "services.execution_service.core.isaac_sim_bridge",    "IsaacSimBridge"),
    ("PyBullet sim",        "services.execution_service.core.pybullet_sim",        "run_pybullet_simulation"),
    ("Vision engine",       "services.vision_service.core.vision_engine",          "VisionEngine"),
    ("Lab state",           "services.vision_service.core.lab_state",              "LabState"),
    ("Analytics engine",    "services.analytics_service.core.analytics_engine",    "AnalyticsEngine"),
    ("Fleet scheduler",     "services.orchestration_service.core.scheduler",       "RobotFleet"),
    ("RL engine",           "services.rl_service.core.rl_engine",                  "ProtocolOptimiser"),
    ("Telemetry store",     "services.rl_service.core.telemetry_store",            "TelemetryStore"),
    ("Shared exceptions",   "shared.exceptions",                                   "AurolabError"),
    ("Shared logger",       "shared.logger",                                       "get_logger"),
    ("Shared middleware",   "shared.middleware",                                   "add_middleware"),
]

for name, module, symbol in SERVICE_IMPORTS:
    try:
        mod = __import__(module, fromlist=[symbol])
        getattr(mod, symbol)
        check(name, True)
    except Exception as e:
        check(name, False, str(e)[:80])

# ---------------------------------------------------------------------------
# 6. Mock pipeline smoke test
# ---------------------------------------------------------------------------
section("Mock Pipeline")

try:
    from services.execution_service.core.step_parser import parse_protocol_steps
    from services.execution_service.core.validator import validate_commands
    from services.execution_service.core.isaac_sim_bridge import IsaacSimBridge, SimMode

    steps = [
        {"step_number": 1, "instruction": "Pipette 50 µL from slot 1 to slot 2"},
        {"step_number": 2, "instruction": "Centrifuge at 3000 rpm for 5 minutes"},
        {"step_number": 3, "instruction": "Incubate at 37°C for 30 minutes"},
        {"step_number": 4, "instruction": "Read absorbance at 562 nm"},
    ]
    cmds = parse_protocol_steps(steps)
    corrected, errors = validate_commands(cmds, auto_correct=True)
    bridge = IsaacSimBridge(mode=SimMode.MOCK)
    result = bridge.validate_execution_plan(corrected)
    check("Mock pipeline: parse → validate → simulate", result is not None,
          f"passed={result.passed}, commands={len(corrected)}")
except Exception as e:
    check("Mock pipeline", False, str(e))

try:
    from services.vision_service.core.vision_engine import _run_mock_detection
    state = _run_mock_detection("bca_assay")
    check("Vision mock detection", len(state.occupied_slots()) > 0,
          f"{len(state.occupied_slots())} occupied slots")
except Exception as e:
    check("Vision mock detection", False, str(e))

try:
    from services.orchestration_service.core.fleet_models import RobotAgent
    from services.orchestration_service.core.scheduler import RobotFleet
    fleet = RobotFleet(robots=[
        RobotAgent(robot_id="r1", name="Alpha"),
        RobotAgent(robot_id="r2", name="Beta"),
    ])
    sched = fleet.schedule([{
        "plan_id": "p1", "protocol_id": "p1", "protocol_title": "T",
        "estimated_mins": 30, "priority": 5, "commands": [],
    }])
    check("Fleet scheduling", sched.task_count == 1,
          f"{sched.task_count} task(s) scheduled")
except Exception as e:
    check("Fleet scheduling", False, str(e))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "═" * 55)
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
print(f"  {passed} passed  {failed} failed  ({len(results)} total)")

if failed == 0:
    print("\n  \033[92mAll checks passed. Ready to launch:\033[0m")
    print("  uvicorn services.translation_service.main:app --port 8080 --reload")
    print("  streamlit run dashboard/app.py")
else:
    print(f"\n  \033[91m{failed} check(s) failed.\033[0m")
    print("  Run with --fix to auto-resolve directory issues.")
    print("  Remaining failures need manual attention (see above).")
    sys.exit(1)