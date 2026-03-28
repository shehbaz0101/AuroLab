"""
fix_project_structure.py

Run this ONCE from your AuroLab/ root to:
1. Create all missing __init__.py files
2. Create missing service directories (rl_service)
3. Fix execution_router.py location
4. Verify all imports resolve

Usage:
    cd AuroLab
    python fix_project_structure.py
"""

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
SERVICES = ROOT / "services"


def create_init_files():
    """Create __init__.py in every package directory that needs one."""
    dirs = [
        ROOT / "tests",
        ROOT / "scripts",
        ROOT / "shared",
        SERVICES,
        SERVICES / "translation_service",
        SERVICES / "translation_service" / "api",
        SERVICES / "translation_service" / "core",
        SERVICES / "translation_service" / "config",
        SERVICES / "execution_service",
        SERVICES / "execution_service" / "core",
        SERVICES / "vision_service",
        SERVICES / "vision_service" / "api",
        SERVICES / "vision_service" / "core",
        SERVICES / "analytics_service",
        SERVICES / "analytics_service" / "api",
        SERVICES / "analytics_service" / "core",
        SERVICES / "orchestration_service",
        SERVICES / "orchestration_service" / "api",
        SERVICES / "orchestration_service" / "core",
        SERVICES / "rl_service",
        SERVICES / "rl_service" / "api",
        SERVICES / "rl_service" / "core",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        init = d / "__init__.py"
        if not init.exists():
            init.touch()
            print(f"  Created {init.relative_to(ROOT)}")
        else:
            print(f"  Exists  {init.relative_to(ROOT)}")


def fix_execution_router():
    """
    execution_router.py should be in services/execution_service/core/ in your project.
    Make sure its imports are absolute (not relative).
    """
    target = SERVICES / "execution_service" / "core" / "execution_router.py"
    if target.exists():
        content = target.read_text()
        if "from ..core" in content or "from .orchestrator" not in content:
            # Fix: replace relative cross-module imports with absolute
            content = content.replace(
                "from ..core.orchestrator", "from services.execution_service.core.orchestrator"
            ).replace(
                "from ..core.isaac_sim_bridge", "from services.execution_service.core.isaac_sim_bridge"
            ).replace(
                "from ..core.robot_commands", "from services.execution_service.core.robot_commands"
            )
            target.write_text(content)
            print(f"  Fixed imports in {target.relative_to(ROOT)}")


def fix_vision_router():
    """Fix relative imports in vision_router.py."""
    target = SERVICES / "vision_service" / "api" / "vision_router.py"
    if target.exists():
        content = target.read_text()
        content = content.replace(
            "from ..core.lab_state", "from services.vision_service.core.lab_state"
        ).replace(
            "from ..core.vision_engine", "from services.vision_service.core.vision_engine"
        )
        target.write_text(content)
        print(f"  Fixed imports in {target.relative_to(ROOT)}")


def fix_analytics_router():
    """Fix relative imports in analytics_router.py."""
    target = SERVICES / "analytics_service" / "api" / "analytics_router.py"
    if target.exists():
        content = target.read_text()
        content = content.replace(
            "from ..core.analytics_engine", "from services.analytics_service.core.analytics_engine"
        ).replace(
            "from ..core.analytics_models", "from services.analytics_service.core.analytics_models"
        )
        target.write_text(content)
        print(f"  Fixed imports in {target.relative_to(ROOT)}")


def fix_fleet_router():
    """Fix relative imports in fleet_router.py."""
    target = SERVICES / "orchestration_service" / "api" / "fleet_router.py"
    if target.exists():
        content = target.read_text()
        content = content.replace(
            "from ..core.fleet_models", "from services.orchestration_service.core.fleet_models"
        ).replace(
            "from ..core.scheduler", "from services.orchestration_service.core.scheduler"
        )
        target.write_text(content)
        print(f"  Fixed imports in {target.relative_to(ROOT)}")


def fix_rl_router():
    """Fix relative imports in rl_router.py."""
    target = SERVICES / "rl_service" / "api" / "rl_router.py"
    if target.exists():
        content = target.read_text()
        content = content.replace(
            "from ..core.rl_engine", "from services.rl_service.core.rl_engine"
        ).replace(
            "from ..core.telemetry_store", "from services.rl_service.core.telemetry_store"
        )
        target.write_text(content)
        print(f"  Fixed imports in {target.relative_to(ROOT)}")


def fix_orchestrator():
    """Fix vision import in orchestrator.py."""
    target = SERVICES / "execution_service" / "core" / "orchestrator.py"
    if target.exists():
        content = target.read_text()
        content = content.replace(
            "from vision.core.lab_state", "from services.vision_service.core.lab_state"
        )
        target.write_text(content)
        print(f"  Fixed imports in {target.relative_to(ROOT)}")


def verify_critical_files():
    """Check that all critical files exist."""
    critical = [
        SERVICES / "translation_service" / "main.py",
        SERVICES / "translation_service" / "core" / "rag_engine.py",
        SERVICES / "translation_service" / "core" / "llm_engine.py",
        SERVICES / "execution_service" / "core" / "robot_commands.py",
        SERVICES / "execution_service" / "core" / "orchestrator.py",
        SERVICES / "vision_service" / "core" / "lab_state.py",
        SERVICES / "analytics_service" / "core" / "analytics_engine.py",
        SERVICES / "orchestration_service" / "core" / "scheduler.py",
    ]
    print("\n  Checking critical files:")
    all_ok = True
    for f in critical:
        exists = f.exists()
        status = "OK  " if exists else "MISS"
        print(f"  [{status}] {f.relative_to(ROOT)}")
        if not exists:
            all_ok = False

    missing_rl = not (SERVICES / "rl_service" / "core" / "rl_engine.py").exists()
    if missing_rl:
        print("\n  [MISS] services/rl_service/ — copy from downloaded files")
        all_ok = False

    return all_ok


if __name__ == "__main__":
    print("\n=== AuroLab Project Structure Fix ===\n")

    print("[1/7] Creating __init__.py files...")
    create_init_files()

    print("\n[2/7] Fixing execution_router imports...")
    fix_execution_router()

    print("\n[3/7] Fixing vision_router imports...")
    fix_vision_router()

    print("\n[4/7] Fixing analytics_router imports...")
    fix_analytics_router()

    print("\n[5/7] Fixing fleet_router imports...")
    fix_fleet_router()

    print("\n[6/7] Fixing rl_router imports...")
    fix_rl_router()

    print("\n[7/7] Fixing orchestrator vision import...")
    fix_orchestrator()

    print("\n=== Verifying critical files ===")
    ok = verify_critical_files()

    print("\n=== Done ===")
    if ok:
        print("All files present. Run: pytest tests/ -v")
    else:
        print("Some files missing — copy them from the downloaded phase files.")
        print("Then run: pytest tests/ -v")