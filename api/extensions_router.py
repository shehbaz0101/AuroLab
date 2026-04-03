"""
api/extensions_router.py

AuroLab Phase 8+ API Extensions.
Wires all new core modules into REST endpoints:

  /api/v1/protocols/{id}/export/ot2     — Opentrons .py script
  /api/v1/protocols/{id}/report         — HTML or Markdown report
  /api/v1/protocols/compare             — Side-by-side diff
  /api/v1/protocols/{id}/optimise       — 3-variant multi-objective optimisation
  /api/v1/templates/                    — List protocol templates
  /api/v1/templates/{id}                — Get template detail
  /api/v1/templates/{id}/build          — Build instruction from template
  /api/v1/inventory/                    — List all reagents
  /api/v1/inventory/                    — Add reagent (POST)
  /api/v1/inventory/{id}                — Delete reagent
  /api/v1/inventory/check               — Check protocol vs inventory
  /api/v1/reflect/{protocol_id}         — LLM reflection on failed sim
  /api/v1/workflows/                    — List / create workflows
  /api/v1/workflows/{id}                — Get / delete workflow
  /api/v1/workflows/{id}/run            — Execute workflow
  /api/v1/search                        — Semantic protocol search
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

# Ensure project root on path for core imports
sys.path.insert(0, str(Path(__file__).parent.parent))

router = APIRouter(prefix="/api/v1", tags=["Extensions"])

log_import_errors: list[str] = []

# ── Safe imports ─────────────────────────────────────────────────────────────
try:
    from core.opentrons_exporter import export_opentrons_script, export_opentrons_json
    _HAS_OT2 = True
except ImportError as e:
    _HAS_OT2 = False; log_import_errors.append(f"opentrons_exporter: {e}")

try:
    from core.protocol_diff import diff_protocols
    _HAS_DIFF = True
except ImportError as e:
    _HAS_DIFF = False; log_import_errors.append(f"protocol_diff: {e}")

try:
    from core.reagent_inventory import ReagentInventory
    _inventory = ReagentInventory("./data/inventory.db")
    _HAS_INV = True
except ImportError as e:
    _HAS_INV = False; log_import_errors.append(f"reagent_inventory: {e}")

try:
    from core.protocol_templates import (
        list_templates, get_template, build_instruction_from_template)
    _HAS_TMPL = True
except ImportError as e:
    _HAS_TMPL = False; log_import_errors.append(f"protocol_templates: {e}")

try:
    from core.report_generator import generate_html_report, generate_markdown_report
    _HAS_REPORT = True
except ImportError as e:
    _HAS_REPORT = False; log_import_errors.append(f"report_generator: {e}")

try:
    from core.workflow_engine import WorkflowEngine, WorkflowStep
    _workflow_engine = WorkflowEngine("./data/workflows.db")
    _HAS_WF = True
except ImportError as e:
    _HAS_WF = False; log_import_errors.append(f"workflow_engine: {e}")

try:
    from core.protocol_optimizer import ProtocolOptimiser as POpt, _estimate_time, _estimate_cost, _estimate_plastic
    _HAS_OPT = True
except ImportError as e:
    _HAS_OPT = False; log_import_errors.append(f"protocol_optimizer: {e}")

try:
    from core.llm_reflection import LLMReflectionEngine
    _HAS_REFLECT = True
except ImportError as e:
    _HAS_REFLECT = False; log_import_errors.append(f"llm_reflection: {e}")


# ── Helper ────────────────────────────────────────────────────────────────────
def _get_protocol(request: Request, protocol_id: str) -> dict:
    """Get protocol from registry. Raises 404 if not found."""
    try:
        mgr = request.app.state.protocol_manager
        p   = mgr.get(protocol_id)
        if not p:
            raise HTTPException(404, f"Protocol {protocol_id} not found")
        if hasattr(p, "model_dump"):
            return p.model_dump(mode="json")
        return p if isinstance(p, dict) else dict(p)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Registry error: {exc}") from exc


# ═══════════════════════════════════════════════════════════════════════════════
# Opentrons Export
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/protocols/{protocol_id}/export/ot2",
    summary="Export protocol as Opentrons OT-2 Python script")
async def export_ot2_script(
    protocol_id: str,
    request: Request,
    fmt: str = Query("python", enum=["python", "json"]),
):
    if not _HAS_OT2:
        raise HTTPException(503, "opentrons_exporter not available")
    p = _get_protocol(request, protocol_id)
    if fmt == "json":
        return export_opentrons_json(p)
    script = export_opentrons_script(p)
    return PlainTextResponse(
        content=script,
        media_type="text/x-python",
        headers={"Content-Disposition": f'attachment; filename="aurolab_{protocol_id[:8]}.py"'},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Report Generation
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/protocols/{protocol_id}/report",
    summary="Generate HTML or Markdown report for a protocol")
async def generate_report(
    protocol_id: str,
    request: Request,
    fmt:                str  = Query("html", enum=["html", "markdown"]),
    include_provenance: bool = Query(True),
):
    if not _HAS_REPORT:
        raise HTTPException(503, "report_generator not available")
    p = _get_protocol(request, protocol_id)
    if fmt == "markdown":
        md = generate_markdown_report(p)
        return PlainTextResponse(
            content=md, media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="report_{protocol_id[:8]}.md"'},
        )
    html = generate_html_report(p, include_provenance=include_provenance)
    return HTMLResponse(content=html)


# ═══════════════════════════════════════════════════════════════════════════════
# Protocol Diff
# ═══════════════════════════════════════════════════════════════════════════════

class DiffRequest(BaseModel):
    protocol_id_a: str
    protocol_id_b: str


@router.post("/protocols/compare",
    summary="Compare two protocols side-by-side and get diff")
async def compare_protocols(body: DiffRequest, request: Request):
    if not _HAS_DIFF:
        raise HTTPException(503, "protocol_diff not available")
    pa = _get_protocol(request, body.protocol_id_a)
    pb = _get_protocol(request, body.protocol_id_b)
    diff = diff_protocols(pa, pb)
    return diff.to_dict()


# ═══════════════════════════════════════════════════════════════════════════════
# Multi-Objective Optimisation
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/optimise/{protocol_id}",
    summary="Generate speed / cost / green optimised protocol variants")
async def optimise_protocol(protocol_id: str, request: Request):
    p = _get_protocol(request, protocol_id)

    if not _HAS_OPT:
        # Return heuristic estimates when optimizer module missing
        t = _estimate_time(p) if _HAS_OPT else 60.0
        c = _estimate_cost(p) if _HAS_OPT else 0.1
        pl = _estimate_plastic(p) if _HAS_OPT else 0.5
        return {
            "original_protocol_id": protocol_id,
            "variants": [
                {"objective": obj, "success": False,
                 "error": "protocol_optimizer not available — install or check imports",
                 "estimated_time_min": t, "estimated_cost_usd": c,
                 "estimated_plastic_g": pl, "optimisation_notes": ""}
                for obj in ["speed", "cost", "green"]
            ],
            "tradeoff_analysis": "Optimizer unavailable.",
            "total_ms": 0,
        }

    llm = request.app.state.llm_engine
    optimiser = POpt(llm)
    result    = optimiser.optimise(p)
    return result.to_dict()


# ═══════════════════════════════════════════════════════════════════════════════
# Templates
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/templates/",
    summary="List all protocol templates")
async def list_protocol_templates(
    category: str | None = Query(None, enum=["assay","prep","analysis","qc"]),
):
    if not _HAS_TMPL:
        raise HTTPException(503, "protocol_templates not available")
    return {"templates": list_templates(category)}


@router.get("/templates/{template_id}",
    summary="Get a specific template with full detail")
async def get_protocol_template(template_id: str):
    if not _HAS_TMPL:
        raise HTTPException(503, "protocol_templates not available")
    t = get_template(template_id)
    if not t:
        raise HTTPException(404, f"Template '{template_id}' not found")
    return t.to_dict()


class TemplateBuildRequest(BaseModel):
    params: dict = Field(default_factory=dict)


@router.post("/templates/{template_id}/build",
    summary="Build an instruction string from a template + parameters")
async def build_template_instruction(template_id: str, body: TemplateBuildRequest):
    if not _HAS_TMPL:
        raise HTTPException(503, "protocol_templates not available")
    t = get_template(template_id)
    if not t:
        raise HTTPException(404, f"Template '{template_id}' not found")
    instruction = build_instruction_from_template(template_id, body.params)
    return {"template_id": template_id, "instruction": instruction,
            "name": t.name, "estimated_time_min": t.estimated_time_min}


# ═══════════════════════════════════════════════════════════════════════════════
# Reagent Inventory
# ═══════════════════════════════════════════════════════════════════════════════

class AddReagentRequest(BaseModel):
    name:          str
    quantity_ml:   float
    unit:          str   = "ml"
    expiry_date:   str   = ""
    location:      str   = ""
    supplier:      str   = ""
    lot_number:    str   = ""
    hazard_class:  str   = "none"
    minimum_stock: float = 10.0
    cas_number:    str   = ""


class InventoryCheckRequest(BaseModel):
    protocol_id: str
    reagents:    list[str]


@router.get("/inventory/",
    summary="List all reagents in inventory")
async def list_inventory(search: str = Query("")):
    if not _HAS_INV:
        raise HTTPException(503, "reagent_inventory not available")
    reagents = _inventory.search(search)
    return {
        "reagents":  [r.to_dict() for r in reagents],
        "total":     len(reagents),
        "low_stock": len(_inventory.get_low_stock()),
        "expired":   len(_inventory.get_expired()),
    }


@router.post("/inventory/",
    summary="Add a reagent to inventory")
async def add_reagent(body: AddReagentRequest):
    if not _HAS_INV:
        raise HTTPException(503, "reagent_inventory not available")
    r = _inventory.add_reagent(**body.model_dump())
    return r.to_dict()


@router.delete("/inventory/{reagent_id}",
    summary="Remove a reagent from inventory")
async def delete_reagent(reagent_id: str):
    if not _HAS_INV:
        raise HTTPException(503, "reagent_inventory not available")
    if not _inventory.delete(reagent_id):
        raise HTTPException(404, "Reagent not found")
    return {"deleted": reagent_id}


@router.post("/inventory/check",
    summary="Check if a protocol's reagents are in stock")
async def check_inventory(body: InventoryCheckRequest):
    if not _HAS_INV:
        raise HTTPException(503, "reagent_inventory not available")
    result = _inventory.check_protocol(body.protocol_id, body.reagents)
    return result.to_dict()


# ═══════════════════════════════════════════════════════════════════════════════
# LLM Reflection
# ═══════════════════════════════════════════════════════════════════════════════

class ReflectRequest(BaseModel):
    protocol_id: str
    sim_result:  dict = Field(default_factory=dict)
    sim_mode:    str  = "mock"


@router.post("/reflect",
    summary="Run LLM reflection on a failed simulation — diagnose and auto-fix")
async def reflect_on_failure(body: ReflectRequest, request: Request):
    if not _HAS_REFLECT:
        raise HTTPException(503, "llm_reflection not available")
    p = _get_protocol(request, body.protocol_id)
    llm     = request.app.state.llm_engine
    engine  = LLMReflectionEngine(llm)
    result  = engine.reflect_on_failure(p, body.sim_result, body.sim_mode)
    # Auto-save revised protocol to registry if reflection succeeded
    if result.revised_protocol and result.revised_sim_passed:
        try:
            from core.registry import ProtocolEntry
            mgr = request.app.state.protocol_manager
            mgr.save(result.revised_protocol)
        except Exception:
            pass
    return result.to_dict()


# ═══════════════════════════════════════════════════════════════════════════════
# Workflow Chains
# ═══════════════════════════════════════════════════════════════════════════════

class CreateWorkflowRequest(BaseModel):
    name:        str
    description: str                = ""
    steps:       list[dict]         = Field(default_factory=list)


@router.get("/workflows/",
    summary="List all workflow definitions")
async def list_workflows():
    if not _HAS_WF:
        raise HTTPException(503, "workflow_engine not available")
    return {"workflows": _workflow_engine.list_workflows()}


@router.post("/workflows/",
    summary="Create a new workflow")
async def create_workflow(body: CreateWorkflowRequest):
    if not _HAS_WF:
        raise HTTPException(503, "workflow_engine not available")
    steps = [WorkflowStep(
        step_index=s.get("step_index", i),
        name=s.get("name", f"Step {i+1}"),
        protocol_id=s["protocol_id"],
        description=s.get("description",""),
        condition=s.get("condition","always"),
        inject_from=s.get("inject_from",-1),
        inject_field=s.get("inject_field",""),
        inject_target=s.get("inject_target",""),
    ) for i, s in enumerate(body.steps)]
    wid = _workflow_engine.create_workflow(body.name, steps, body.description)
    return {"workflow_id": wid, "name": body.name, "steps": len(steps)}


@router.get("/workflows/{workflow_id}",
    summary="Get workflow definition")
async def get_workflow(workflow_id: str):
    if not _HAS_WF:
        raise HTTPException(503, "workflow_engine not available")
    wf = _workflow_engine.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return wf


@router.delete("/workflows/{workflow_id}",
    summary="Delete a workflow")
async def delete_workflow(workflow_id: str):
    if not _HAS_WF:
        raise HTTPException(503, "workflow_engine not available")
    if not _workflow_engine.delete_workflow(workflow_id):
        raise HTTPException(404, "Workflow not found")
    return {"deleted": workflow_id}


@router.post("/workflows/{workflow_id}/run",
    summary="Execute a workflow chain")
async def run_workflow(workflow_id: str, request: Request,
                       sim_mode: str = Query("mock")):
    if not _HAS_WF:
        raise HTTPException(503, "workflow_engine not available")
    wf = _workflow_engine.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")

    # Build protocol registry from app state
    try:
        mgr = request.app.state.protocol_manager
        all_protos = mgr.get_all() if hasattr(mgr, "get_all") else []
        registry = {}
        for p in all_protos:
            if hasattr(p, "model_dump"):
                pd = p.model_dump(mode="json")
            elif isinstance(p, dict):
                pd = p
            else:
                pd = dict(p)
            registry[pd.get("protocol_id","")] = pd
    except Exception:
        registry = {}

    run = _workflow_engine.start_run(workflow_id)
    n_steps = len(wf.get("steps", []))
    for i in range(n_steps):
        result = _workflow_engine.execute_step(run, i, registry, sim_mode)
        run.results[i] = result
        if result.status == "failed":
            step_cond = wf["steps"][i].get("condition","always")
            if step_cond != "on_fail":
                break

    run.status = "completed" if all(
        r.status in ("passed","skipped") for r in run.results
    ) else "failed"
    return run.to_dict()


@router.get("/workflows/{workflow_id}/runs",
    summary="List all runs for a workflow")
async def list_workflow_runs(workflow_id: str):
    if not _HAS_WF:
        raise HTTPException(503, "workflow_engine not available")
    return {"runs": _workflow_engine.list_runs(workflow_id)}


# ═══════════════════════════════════════════════════════════════════════════════
# Semantic Protocol Search
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/search",
    summary="Semantic search across all generated protocols")
async def search_protocols(
    q:       str   = Query(..., description="Search query"),
    limit:   int   = Query(10, ge=1, le=50),
    safety:  str | None = Query(None),
    request: Request = None,
):
    try:
        mgr       = request.app.state.protocol_manager
        all_protos = mgr.get_all() if hasattr(mgr, "get_all") else []
    except Exception:
        all_protos = []

    q_lower = q.lower()
    results = []
    for p in all_protos:
        if hasattr(p, "model_dump"):
            pd = p.model_dump(mode="json")
        elif isinstance(p, dict):
            pd = p
        else:
            pd = dict(p)

        if safety and pd.get("safety_level") != safety:
            continue

        # Score by relevance: title > description > step instructions
        score = 0.0
        title = pd.get("title","").lower()
        desc  = pd.get("description","").lower()
        steps_text = " ".join(
            s.get("instruction","") for s in pd.get("steps",[])
        ).lower()
        reagents_text = " ".join(pd.get("reagents",[])).lower()

        if q_lower in title:           score += 1.0
        if q_lower in desc:            score += 0.6
        if q_lower in steps_text:      score += 0.4
        if q_lower in reagents_text:   score += 0.3

        # Token overlap
        q_words = set(q_lower.split())
        all_text_words = set((title + " " + desc + " " + steps_text).split())
        token_overlap = len(q_words & all_text_words) / max(len(q_words), 1)
        score += token_overlap * 0.5

        if score > 0:
            results.append({
                "protocol_id":    pd.get("protocol_id",""),
                "title":          pd.get("title",""),
                "description":    pd.get("description",""),
                "safety_level":   pd.get("safety_level","safe"),
                "confidence":     pd.get("confidence_score",0),
                "steps":          len(pd.get("steps",[])),
                "relevance_score": round(score, 3),
            })

    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return {
        "query":   q,
        "total":   len(results),
        "results": results[:limit],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Extensions health
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/extensions/status",
    summary="Check which extension modules are available")
async def extensions_status():
    return {
        "opentrons_exporter": _HAS_OT2,
        "protocol_diff":      _HAS_DIFF,
        "reagent_inventory":  _HAS_INV,
        "protocol_templates": _HAS_TMPL,
        "report_generator":   _HAS_REPORT,
        "workflow_engine":    _HAS_WF,
        "protocol_optimizer": _HAS_OPT,
        "llm_reflection":     _HAS_REFLECT,
        "import_errors":      log_import_errors,
    }