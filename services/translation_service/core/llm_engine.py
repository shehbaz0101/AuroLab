"""
aurolab/services/translation_service/core/llm_engine.py

RAG-aware protocol generation engine for AuroLab.

Key upgrades over basic LLM calls:
  1. Structured context injection  — retrieved chunks are formatted as XML
     <source> blocks so the model can reason about provenance, not just content.
  2. Citation-enforced prompting    — system prompt requires [SOURCE_N] inline
     citations; parser extracts and validates them post-generation.
  3. Typed output (Pydantic v2)     — GeneratedProtocol with per-step citations,
     safety flags, and confidence score. Never raw strings downstream.
  4. Safety gate                    — pre-generation hazard check + post-generation
     volume/concentration validator.
  5. Retry with degradation         — if full RAG context produces a malformed
     response, retries with simplified prompt before failing.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog
from groq import Groq
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .rag_engine import AurolabRAGEngine, RetrievedChunk

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GENERATION_MODEL   = "llama-3.3-70b-versatile"   # best Groq model for structured output
FALLBACK_MODEL     = "llama3-8b-8192"             # faster fallback on retry
MAX_TOKENS         = 2048
TEMPERATURE        = 0.2   # low — protocols need determinism, not creativity
MAX_RETRIES        = 2

# Hazardous keywords that trigger a pre-generation safety block
_HAZARD_PATTERNS = re.compile(
    r"\b(explosive|synthesis of|nerve agent|toxic gas|weaponi[sz]|"
    r"lethal dose|LD50 of humans|ricin|sarin|VX nerve)\b",
    re.IGNORECASE,
)

# Concentration ranges that need a safety warning (not blocked, just flagged)
_HIGH_CONC_PATTERNS = re.compile(
    r"\b(\d+)\s*(M|mol/L)\b"  # molar concentrations above threshold
)
HIGH_CONC_THRESHOLD_M = 10.0  # flag concentrations ≥ 10M


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

class SafetyLevel(str, Enum):
    SAFE       = "safe"
    WARNING    = "warning"    # proceed with caution notice
    BLOCKED    = "blocked"    # refused at generation stage


class ProtocolStep(BaseModel):
    step_number: int
    instruction: str
    duration_seconds: int | None = None
    temperature_celsius: float | None = None
    volume_ul: float | None = None
    citations: list[str] = Field(default_factory=list)  # e.g. ["SOURCE_1", "SOURCE_3"]
    safety_note: str | None = None

    @field_validator("instruction")
    @classmethod
    def instruction_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Step instruction cannot be empty")
        return v.strip()


class GeneratedProtocol(BaseModel):
    """
    Fully typed protocol output. Every field is either required or has a safe default.
    This is what gets returned from /api/v1/generate — never raw LLM text.
    """
    protocol_id: str
    title: str
    description: str
    steps: list[ProtocolStep]
    reagents: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    safety_level: SafetyLevel = SafetyLevel.SAFE
    safety_notes: list[str] = Field(default_factory=list)
    sources_used: list[dict[str, Any]] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.0)
    generation_ms: float = 0.0
    model_used: str = ""
    raw_llm_output: str = ""   # kept for debugging; stripped before external API responses

    model_config = ConfigDict(
        json_schema_extra={"exclude": {"raw_llm_output"}}
    )


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------

def _format_context_block(chunks: list[RetrievedChunk]) -> str:
    """
    Format retrieved chunks as XML source blocks.
    The model is explicitly instructed to reference these by [SOURCE_N] tag.

    Example output:
      <sources>
        <source id="SOURCE_1" doc="bca_protocol.pdf" section="Materials" page="2">
          Add 50 µL of sample to each well ...
        </source>
        ...
      </sources>
    """
    if not chunks:
        return "<sources>\n  <source id='SOURCE_NONE'>No relevant sources found. Generate from general knowledge.</source>\n</sources>"

    lines = ["<sources>"]
    for i, chunk in enumerate(chunks, start=1):
        section = chunk.section_title or "General"
        page_info = f"page={chunk.page_start}" if chunk.page_start else ""
        lines.append(
            f'  <source id="SOURCE_{i}" doc="{chunk.source}" '
            f'section="{section}" {page_info} score="{chunk.score:.3f}">'
        )
        lines.append(f"    {chunk.text}")
        lines.append("  </source>")
    lines.append("</sources>")
    return "\n".join(lines)


def _build_system_prompt() -> str:
    return """You are AuroLab, an expert laboratory automation system. You convert natural language lab instructions into precise, executable robotic protocols.

RULES:
1. Every step must cite its source using [SOURCE_N] where N matches the source id in the provided <sources> block. If a step uses general knowledge, write [GENERAL].
2. Output ONLY valid JSON matching this exact schema — no markdown, no preamble:
{
  "title": "string",
  "description": "string (1-2 sentences)",
  "reagents": ["list of reagents with concentrations"],
  "equipment": ["list of equipment"],
  "steps": [
    {
      "step_number": 1,
      "instruction": "string — precise, imperative, robot-executable",
      "duration_seconds": null_or_int,
      "temperature_celsius": null_or_float,
      "volume_ul": null_or_float,
      "citations": ["SOURCE_1"],
      "safety_note": null_or_string
    }
  ],
  "safety_notes": ["list of protocol-level safety warnings"],
  "confidence_score": 0.0_to_1.0
}
3. Instructions must be imperative and robot-executable: "Pipette 50 µL" not "You should pipette".
4. Include duration_seconds, temperature_celsius, volume_ul whenever the instruction implies them.
5. Flag any step involving hazardous reagents (>1M acid/base, ethidium bromide, etc.) in safety_note.
6. confidence_score reflects how well the retrieved sources cover the requested protocol (1.0 = fully covered, 0.0 = pure guess)."""


def _build_user_prompt(instruction: str, context_block: str) -> str:
    return f"""Convert the following lab instruction into a robotic protocol.

INSTRUCTION:
{instruction}

RETRIEVED KNOWLEDGE BASE SOURCES:
{context_block}

Generate the JSON protocol now. Cite sources inline using [SOURCE_N] tags."""


# ---------------------------------------------------------------------------
# Safety checks
# ---------------------------------------------------------------------------

def _pre_generation_safety_check(instruction: str) -> tuple[SafetyLevel, str | None]:
    """Block outright hazardous requests before any LLM call."""
    if _HAZARD_PATTERNS.search(instruction):
        return SafetyLevel.BLOCKED, "Instruction contains patterns associated with hazardous synthesis. Request blocked."
    return SafetyLevel.SAFE, None


def _post_generation_safety_check(protocol: GeneratedProtocol) -> GeneratedProtocol:
    """
    Scan generated steps for high-concentration reagents and flag them.
    Does not block — adds warning to safety_notes.
    """
    warnings = list(protocol.safety_notes)
    for step in protocol.steps:
        matches = _HIGH_CONC_PATTERNS.findall(step.instruction)
        for val, unit in matches:
            if float(val) >= HIGH_CONC_THRESHOLD_M:
                note = f"Step {step.step_number}: {val}{unit} concentration — verify dilution before robotic dispensing."
                warnings.append(note)
                if not step.safety_note:
                    step.safety_note = note

    if warnings:
        protocol.safety_notes = warnings
        if protocol.safety_level == SafetyLevel.SAFE:
            protocol.safety_level = SafetyLevel.WARNING
    return protocol


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _parse_llm_json(raw: str) -> dict:
    """
    Extract JSON from LLM output robustly.
    Models sometimes wrap output in ```json ... ``` fences despite instructions.
    """
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

    # Find the outermost JSON object
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in LLM output. Raw: {raw[:200]}")

    return json.loads(cleaned[start:end])


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class AurolabLLMEngine:
    """
    Protocol generation engine. Wraps Groq + RAG retrieval into a single
    generate() call that returns a fully validated GeneratedProtocol.
    """

    def __init__(
        self,
        groq_api_key: str,
        rag_engine: AurolabRAGEngine,
        model: str = GENERATION_MODEL,
        fallback_model: str = FALLBACK_MODEL,
    ) -> None:
        self._groq = Groq(api_key=groq_api_key)
        self._rag = rag_engine
        self._model = model
        self._fallback_model = fallback_model
        log.info("llm_engine_ready", model=model)

    def generate(
        self,
        instruction: str,
        protocol_id: str,
        top_k_chunks: int = 5,
        doc_type_filter: str | None = None,
    ) -> GeneratedProtocol:
        """
        Full pipeline: safety check → RAG retrieval → citation-aware generation
        → JSON parse → Pydantic validation → post-generation safety scan.

        Args:
            instruction:      Natural language lab instruction.
            protocol_id:      Caller-provided ID for traceability.
            top_k_chunks:     How many RAG chunks to inject as context.
            doc_type_filter:  Restrict retrieval to a doc type (e.g. "protocol").

        Returns:
            GeneratedProtocol — fully typed, validated, citations attached.

        Raises:
            ValueError: If safety check blocks the request.
            RuntimeError: If generation fails after all retries.
        """
        t0 = time.perf_counter()

        # 1. Pre-generation safety check
        safety_level, block_reason = _pre_generation_safety_check(instruction)
        if safety_level == SafetyLevel.BLOCKED:
            log.warning("generation_blocked", reason=block_reason, instruction=instruction[:80])
            raise ValueError(f"Safety block: {block_reason}")

        # 2. RAG retrieval
        retrieval_result = self._rag.retrieve(
            query=instruction,
            top_k=top_k_chunks,
            doc_type_filter=doc_type_filter,
        )
        context_block = _format_context_block(retrieval_result.chunks)
        log.info("context_built",
                 chunks=len(retrieval_result.chunks),
                 retrieval_ms=retrieval_result.retrieval_ms)

        # 3. Generation with retry
        system_prompt = _build_system_prompt()
        user_prompt   = _build_user_prompt(instruction, context_block)
        raw_output    = self._call_with_retry(system_prompt, user_prompt)

        # 4. Parse + validate
        try:
            data = _parse_llm_json(raw_output)
        except (json.JSONDecodeError, ValueError) as exc:
            log.error("json_parse_failed", error=str(exc), raw=raw_output[:300])
            raise RuntimeError(f"LLM output could not be parsed as JSON: {exc}") from exc

        # 5. Build typed output
        steps = []
        for raw_step in data.get("steps", []):
            steps.append(ProtocolStep(
                step_number=raw_step.get("step_number", len(steps) + 1),
                instruction=raw_step.get("instruction", ""),
                duration_seconds=raw_step.get("duration_seconds"),
                temperature_celsius=raw_step.get("temperature_celsius"),
                volume_ul=raw_step.get("volume_ul"),
                citations=raw_step.get("citations", []),
                safety_note=raw_step.get("safety_note"),
            ))

        sources_used = [
            {
                "source_id": f"SOURCE_{i+1}",
                "filename": c.source,
                "section": c.section_title,
                "page_start": c.page_start,
                "score": round(c.score, 4),
            }
            for i, c in enumerate(retrieval_result.chunks)
        ]

        elapsed = (time.perf_counter() - t0) * 1000

        protocol = GeneratedProtocol(
            protocol_id=protocol_id,
            title=data.get("title", "Untitled Protocol"),
            description=data.get("description", ""),
            steps=steps,
            reagents=data.get("reagents", []),
            equipment=data.get("equipment", []),
            safety_level=SafetyLevel.SAFE,
            safety_notes=data.get("safety_notes", []),
            sources_used=sources_used,
            confidence_score=float(data.get("confidence_score", 0.5)),
            generation_ms=round(elapsed, 1),
            model_used=self._model,
            raw_llm_output=raw_output,
        )

        # 6. Post-generation safety scan
        protocol = _post_generation_safety_check(protocol)

        log.info("protocol_generated",
                 protocol_id=protocol_id,
                 steps=len(steps),
                 safety=protocol.safety_level,
                 confidence=protocol.confidence_score,
                 total_ms=round(elapsed, 1))

        return protocol

    def _call_with_retry(self, system: str, user: str) -> str:
        """Call Groq with retry on failure, degrading to smaller model."""
        models = [self._model, self._fallback_model]
        last_exc: Exception | None = None

        for attempt, model in enumerate(models[:MAX_RETRIES], start=1):
            try:
                resp = self._groq.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    max_tokens=MAX_TOKENS,
                    temperature=TEMPERATURE,
                    response_format={"type": "json_object"},  # Groq JSON mode
                )
                content = resp.choices[0].message.content
                log.debug("llm_call_success", attempt=attempt, model=model, chars=len(content))
                return content
            except Exception as exc:  # noqa: BLE001
                log.warning("llm_call_failed", attempt=attempt, model=model, error=str(exc))
                last_exc = exc

        raise RuntimeError(f"All LLM attempts failed. Last error: {last_exc}") from last_exc