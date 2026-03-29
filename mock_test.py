"""
mock_test.py

Standalone smoke test — runs without pytest, no external APIs, no GPU.
Run from AuroLab/ root:
    python mock_test.py

Checks:
  1. All core imports resolve
  2. PDF parsing works on synthetic bytes
  3. Chunker produces valid output
  4. Step parser translates NL to commands
  5. Validator catches missing tip
  6. Mock simulation passes clean sequence
  7. Analytics engine produces a report
  8. RL reward model scores a run
  9. Fleet scheduler assigns tasks
 10. Vision engine mock detection works
"""

from __future__ import annotations

import sys
import traceback
from typing import Callable

PASS = "  PASS"
FAIL = "  FAIL"
results = []


def check(name: str, fn: Callable) -> bool:
    try:
        fn()
        print(f"{PASS} {name}")
        results.append((name, True, None))
        return True
    except Exception as e:
        print(f"{FAIL} {name}")
        print(f"       {type(e).__name__}: {e}")
        results.append((name, False, e))
        return False


print("\n=== AuroLab Smoke Tests ===\n")

# 1. Core imports
def test_imports():
    from services.translation_service.core.chunker import chunk_document
    from services.translation_service.core.pdf_parser import ParsedDocument
    from services.execution_service.core.robot_commands import ExecutionPlan
    from services.execution_service.core.step_parser import parse_step
    from services.execution_service.core.validator import validate_commands
    from services.execution_service.core.isaac_sim_bridge import IsaacSimBridge, SimMode
    from services.analytics_service.core.analytics_engine import AnalyticsEngine
    from services.rl_service.core.rl_engine import RewardModel
    from services.orchestration_service.core.scheduler import RobotFleet
    from services.vision_service.core.vision_engine import VisionEngine, VisionBackend

check("Core imports resolve", test_imports)


# 2. PDF parsing
def test_pdf_parse():
    from services.translation_service.core.pdf_parser import ParsedDocument, ContentBlock, BlockType
    import hashlib
    blocks = [
        ContentBlock(BlockType.HEADING, "1. Protocol", page_number=1, font_size=14, is_bold=True),
        ContentBlock(BlockType.TEXT, "Pipette 50 µL from slot 1 to slot 2.", page_number=1),
    ]
    doc = ParsedDocument(
        source_path="test.pdf", sha256=hashlib.sha256(b"x").hexdigest(),
        page_count=1, title="Test", authors=[], doc_type="protocol",
        blocks=blocks, raw_text="Pipette 50 µL.", parse_strategy="pymupdf",
    )
    assert doc.page_count == 1
    assert len(doc.blocks) == 2

check("PDF ParsedDocument construction", test_pdf_parse)


# 3. Chunker
def test_chunker():
    from services.translation_service.core.chunker import chunk_document
    from services.translation_service.core.pdf_parser import ParsedDocument, ContentBlock, BlockType
    import hashlib
    blocks = [
        ContentBlock(BlockType.HEADING, "Materials", page_number=1, font_size=14, is_bold=True),
        ContentBlock(BlockType.TEXT, "10 mM Tris-HCl, 150 mM NaCl, 1 mM EDTA. Use fresh.", page_number=1),
        ContentBlock(BlockType.TABLE, "Step | Duration\n1 | 10min", page_number=1,
                     table_data=[["Step","Duration"],["1","10min"]]),
    ]
    doc = ParsedDocument(
        source_path="t.pdf", sha256=hashlib.sha256(b"y").hexdigest(),
        page_count=1, title="T", authors=[], doc_type="protocol",
        blocks=blocks, raw_text="", parse_strategy="pymupdf",
    )
    chunks = chunk_document(doc)
    assert len(chunks) > 0
    tables = [c for c in chunks if c.is_table]
    assert len(tables) == 1

check("Chunker produces chunks + atomic tables", test_chunker)


# 4. Step parser
def test_step_parser():
    from services.execution_service.core.step_parser import parse_step
    from services.execution_service.core.robot_commands import CommandType
    cmds = parse_step("Pipette 50 µL from slot 1 to slot 2", 1)
    types = {c.command_type for c in cmds}
    assert CommandType.ASPIRATE in types
    assert CommandType.PICK_UP_TIP in types

check("Step parser: pipette → commands", test_step_parser)


# 5. Validator catches missing tip
def test_validator():
    from services.execution_service.core.robot_commands import AspirateCommand, LabwarePosition
    from services.execution_service.core.validator import validate_commands
    cmds = [AspirateCommand(command_index=0, protocol_step_ref=1,
                             volume_ul=50, source=LabwarePosition(deck_slot=1))]
    _, errors = validate_commands(cmds, auto_correct=False)
    codes = [e.error_code for e in errors]
    assert "NO_TIP" in codes

check("Validator: catches missing tip", test_validator)


# 6. Mock simulation
def test_mock_sim():
    from services.execution_service.core.robot_commands import (
        HomeCommand, PickUpTipCommand, AspirateCommand, DispenseCommand, DropTipCommand, LabwarePosition
    )
    from services.execution_service.core.isaac_sim_bridge import _run_mock_simulation
    cmds = [
        HomeCommand(command_index=0, protocol_step_ref=0),
        PickUpTipCommand(command_index=1, protocol_step_ref=1, tip_rack_slot=11),
        AspirateCommand(command_index=2, protocol_step_ref=1, volume_ul=50,
                        source=LabwarePosition(deck_slot=1)),
        DispenseCommand(command_index=3, protocol_step_ref=1, volume_ul=50,
                        destination=LabwarePosition(deck_slot=2)),
        DropTipCommand(command_index=4, protocol_step_ref=1),
    ]
    result = _run_mock_simulation(cmds)
    assert result.passed is True

check("Mock simulation: clean sequence passes", test_mock_sim)


# 7. Analytics
def test_analytics():
    from services.analytics_service.core.analytics_engine import AnalyticsEngine
    plan = {"plan_id": "p1", "estimated_mins": 45.0, "commands": []}
    protocol = {
        "protocol_id": "p1", "title": "BCA",
        "steps": [{"step_number": 1, "instruction": "Pipette 50 µL BCA"}],
        "reagents": ["BCA reagent", "96-well plate"], "equipment": [],
    }
    telemetry = {"tip_changes": 1, "total_volume_aspirated_ul": 50.0,
                 "total_volume_dispensed_ul": 48.0}
    engine = AnalyticsEngine()
    report = engine.compute_report(plan, protocol, telemetry)
    assert report.robot_cost.total_usd > 0

check("Analytics: produces cost report", test_analytics)


# 8. RL reward model
def test_rl_reward():
    from services.rl_service.core.telemetry_store import ExecutionRun
    from services.rl_service.core.rl_engine import RewardModel
    import time as t
    run = ExecutionRun(
        run_id="r1", protocol_id="p1", protocol_title="T",
        timestamp=t.time(), sim_mode="mock", passed=True,
        commands_executed=8, tip_changes=1,
        volume_aspirated_ul=50, volume_dispensed_ul=48,
        total_distance_mm=1200, duration_s=1800,
        collision_detected=False, collision_at=None,
        flow_rate_avg=150.0, centrifuge_rpm_avg=0, incubate_temp_avg=37.0,
        reward=0.0, telemetry_json="{}",
    )
    reward = RewardModel().compute(run)
    assert 0.0 <= reward <= 1.0

check("RL: reward model scores a run", test_rl_reward)


# 9. Fleet scheduling
def test_fleet():
    from services.orchestration_service.core.fleet_models import RobotAgent
    from services.orchestration_service.core.scheduler import RobotFleet
    fleet = RobotFleet(robots=[
        RobotAgent(robot_id="r1", name="R1"),
        RobotAgent(robot_id="r2", name="R2"),
    ])
    plans = [
        {"plan_id": "p1", "protocol_id": "x", "protocol_title": "A",
         "estimated_mins": 30, "priority": 5, "commands": []},
        {"plan_id": "p2", "protocol_id": "y", "protocol_title": "B",
         "estimated_mins": 45, "priority": 5, "commands": []},
    ]
    schedule = fleet.schedule(plans)
    assert schedule.task_count == 2

check("Fleet: 2 plans scheduled across 2 robots", test_fleet)


# 10. Vision engine mock
def test_vision():
    from services.vision_service.core.vision_engine import VisionEngine, VisionBackend
    engine = VisionEngine(backend=VisionBackend.MOCK)
    state = engine.detect(mock_scenario="bca_assay")
    assert len(state.occupied_slots()) > 0
    assert 0.0 <= state.overall_confidence <= 1.0

check("Vision: mock detection returns LabState", test_vision)


# 11. PyBullet simulation
def test_pybullet():
    from services.execution_service.core.robot_commands import (
        HomeCommand, PickUpTipCommand, AspirateCommand,
        DispenseCommand, DropTipCommand, LabwarePosition,
    )
    from services.execution_service.core.pybullet_sim import run_pybullet_simulation
    cmds = [
        HomeCommand(command_index=0, protocol_step_ref=0),
        PickUpTipCommand(command_index=1, protocol_step_ref=1, tip_rack_slot=11),
        AspirateCommand(command_index=2, protocol_step_ref=1, volume_ul=50,
                        source=LabwarePosition(deck_slot=1)),
        DispenseCommand(command_index=3, protocol_step_ref=1, volume_ul=50,
                        destination=LabwarePosition(deck_slot=2)),
        DropTipCommand(command_index=4, protocol_step_ref=1),
        HomeCommand(command_index=5, protocol_step_ref=0),
    ]
    result = run_pybullet_simulation(cmds)
    assert result.passed is True
    assert "physics_engine" in result.telemetry

check("PyBullet: clean sequence passes physics sim", test_pybullet)


# 12. Full pipeline (NL → ExecutionPlan)
def test_full_pipeline():
    from services.execution_service.core.orchestrator import execute_protocol
    from services.execution_service.core.isaac_sim_bridge import SimMode
    from services.execution_service.core.robot_commands import ExecutionStatus
    from services.vision_service.core.vision_engine import _run_mock_detection

    lab_state = _run_mock_detection("bca_assay")
    protocol = {
        "protocol_id": "smoke-e2e-001", "title": "Smoke E2E",
        "description": "Full pipeline smoke test",
        "steps": [
            {"step_number": 1, "instruction": "Pipette 50 µL from slot 1 to slot 2"},
            {"step_number": 2, "instruction": "Incubate at 37°C for 30 minutes"},
            {"step_number": 3, "instruction": "Read absorbance at 562 nm"},
        ],
        "reagents": ["BCA reagent"], "equipment": ["plate reader"],
        "safety_level": "safe", "safety_notes": [],
        "confidence_score": 0.9, "generation_ms": 10.0, "model_used": "test",
    }
    plan = execute_protocol(protocol, sim_mode=SimMode.MOCK, lab_state=lab_state)
    assert plan.protocol_id == "smoke-e2e-001"
    assert plan.command_count > 0
    assert plan.simulation_result is not None
    assert plan.status in (ExecutionStatus.SIM_PASSED, ExecutionStatus.SIM_FAILED)

check("Full pipeline: NL → ExecutionPlan with vision", test_full_pipeline)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n=== Results ===")
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
print(f"  {passed}/{len(results)} passed", end="")
if failed:
    print(f"  ({failed} failed)")
    print("\nFailed tests:")
    for name, ok, err in results:
        if not ok:
            print(f"  - {name}: {err}")
    sys.exit(1)
else:
    print(" ✓\n")
    print("All smoke tests passed. Run full suite with: pytest tests/ -v\n")