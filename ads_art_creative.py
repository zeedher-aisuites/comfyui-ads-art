"""Schema, prompt and validation for reference-driven advertising intelligence.

This module deliberately contains no ComfyUI or provider side effects.  Reference
evidence, interpretation, transfer strategy and original proposals are separate
objects so an observed fact can never silently become a generation instruction.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .ads_art_core import AdsArtError, json_dumps
from .ads_art_gemini import GEMINI_GENERATION_CONFIG, GEMINI_MODEL_ID


CREATIVE_PROMPT_VERSION = "ads_art_reference_intelligence_v10_positional"
CREATIVE_SCHEMA_VERSION = "2.0.0"
CREATIVE_PROVIDER_SCHEMA_VERSION = "1.5.0"
CREATIVE_EXPANDER_VERSION = "1.5.0"
CREATIVE_PROVIDER_MAX_OUTPUT_TOKENS = 16384
EVIDENCE_SUPPORTS = {
    "opening_hook",
    "hook_mechanism",
    "psychology",
    "visual_grammar",
    "camera_language",
    "lighting_language",
    "editing_rhythm",
    "audio_strategy",
    "product_reveal_strategy",
    "brand_memory_strategy",
    "emotional_progression",
}
EVIDENCE_KIND_ALIASES = {
    "visual": "visual",
    "observed_visual": "visual",
    "editing": "editing",
    "observed_editing": "editing",
    "audio": "audio",
    "observed_audio": "audio",
    "product_brand": "product_brand",
    "observed_product_brand": "product_brand",
    "mixed": "mixed",
    "observed_mixed": "mixed",
}


def _strings(*, minimum: int = 0, maximum: int | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if minimum:
        value["minItems"] = minimum
    if maximum is not None:
        value["maxItems"] = maximum
    return value


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required or list(properties),
    }


def creative_intelligence_schema(min_shots: int, max_shots: int) -> dict[str, Any]:
    """Return the strict master schema used for the original-ad workflow."""

    if not 1 <= int(min_shots) <= int(max_shots) <= 16:
        raise AdsArtError("El rango de tomas originales debe cumplir 1 <= min <= max <= 16.")
    visual_language = _object(
        {
            "principles": _strings(minimum=1),
            "composition_patterns": _strings(),
            "distance_and_framing": _strings(),
            "color_and_texture": _strings(),
        }
    )
    reference_observation = _object(
        {
            "visual_facts": _strings(minimum=1),
            "editing_facts": _strings(minimum=1),
            "audio_facts": _strings(),
            "product_and_brand_facts": _strings(),
        }
    )
    reference_interpretation = _object(
        {
            "core_concept": {"type": "string"},
            "creative_thesis": {"type": "string"},
            "opening_hook": {"type": "string"},
            "hook_mechanism": {"type": "string"},
            "emotional_promise": {"type": "string"},
            "audience_desire": {"type": "string"},
            "character_archetype": {"type": "string"},
            "status_signals": _strings(),
            "aspirational_mechanisms": _strings(),
            "psychological_mechanisms": _strings(minimum=1),
            "retention_mechanisms": _strings(minimum=1),
            "emotional_progression": _strings(minimum=1),
        }
    )
    reference_strategy = _object(
        {
            "visual_grammar": visual_language,
            "camera_language": _object(
                {
                    "principles": _strings(minimum=1),
                    "framing_patterns": _strings(),
                    "lens_or_perspective_patterns": _strings(),
                    "movement_patterns": _strings(),
                }
            ),
            "lighting_language": _object(
                {
                    "principles": _strings(minimum=1),
                    "contrast_and_direction": _strings(),
                    "motivated_sources": _strings(),
                }
            ),
            "editing_rhythm": _object(
                {
                    "pace": {"type": "string"},
                    "progression": _strings(minimum=1),
                    "shot_duration_patterns": _strings(),
                }
            ),
            "audio_strategy": _object(
                {
                    "observed_structure": _strings(),
                    "interpreted_function": _strings(),
                    "transferable_audio_principles": _strings(),
                }
            ),
            "product_reveal_strategy": {"type": "string"},
            "brand_memory_strategy": {"type": "string"},
        }
    )
    evidence = _object(
        {
            "evidence_id": {"type": "string"},
            "timestamp_seconds": {"type": "number", "minimum": 0},
            "shot_start_seconds": {"type": "number", "minimum": 0},
            "shot_end_seconds": {"type": "number", "minimum": 0},
            "candidate_timestamps": {
                "type": "array",
                "items": {"type": "number", "minimum": 0},
                "minItems": 1,
                "maxItems": 5,
            },
            "evidence_kind": {
                "type": "string",
                "enum": ["visual", "editing", "audio", "product_brand", "mixed"],
            },
            "observed_fact": {"type": "string"},
            "supports": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(EVIDENCE_SUPPORTS)},
                "minItems": 1,
            },
        }
    )
    transfer_rules = _object(
        {
            "transferable_principles": _strings(minimum=1),
            "literal_elements_to_avoid": _strings(minimum=1),
            "similarity_risks": _strings(minimum=1),
            "brand_specific_elements_not_to_inherit": _strings(minimum=1),
        }
    )
    original_adaptation = _object(
        {
            "creative_thesis": {"type": "string"},
            "new_hook": {"type": "string"},
            "new_character_role": {"type": "string"},
            "character_behavior": {"type": "string"},
            "new_brand_world": {"type": "string"},
            "new_product_role": {"type": "string"},
            "emotional_arc": _strings(minimum=1),
            "visual_rules": _strings(minimum=1),
            "audio_rules": _strings(),
            "editing_rules": _strings(minimum=1),
            "differentiation_from_reference": _strings(minimum=1),
        }
    )
    shot = _object(
        {
            "shot_id": {"type": "string"},
            "planned_duration_seconds": {"type": "number", "minimum": 0},
            "purpose": {"type": "string"},
            "psychological_function": {"type": "string"},
            "retention_function": {"type": "string"},
            "character_action": {"type": "string"},
            "expression": {"type": "string"},
            "environment": {"type": "string"},
            "composition": {"type": "string"},
            "framing": {"type": "string"},
            "camera": {"type": "string"},
            "lens_or_perspective": {"type": "string"},
            "movement": {"type": "string"},
            "lighting": {"type": "string"},
            "color_and_texture": {"type": "string"},
            "product_presence": {"type": "string"},
            "audio_function": {"type": "string"},
            "continuity_notes": {"type": "string"},
            "reference_principles_used": _strings(minimum=1),
            "literal_reference_elements_avoided": _strings(minimum=1),
            "differentiation_notes": _strings(minimum=1),
            "nano_banana_prompt": {"type": "string"},
            "seedance_direction": _object(
                {
                    "performance": {"type": "string"},
                    "camera_movement": {"type": "string"},
                    "pacing": {"type": "string"},
                    "emotional_goal": {"type": "string"},
                    "continuity": {"type": "string"},
                }
            ),
            "uncertainties": _strings(),
        }
    )
    provenance = _object(
        {
            "user_provided": _strings(),
            "ai_proposed": _strings(),
            "approved": _strings(),
            "unresolved_inputs": _strings(),
        }
    )
    return {
        "title": "Ads Art reference-driven creative intelligence",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reference_observation": reference_observation,
            "reference_interpretation": reference_interpretation,
            "reference_strategy": reference_strategy,
            "evidence": {"type": "array", "items": evidence, "minItems": 1, "maxItems": 24},
            "transfer_rules": transfer_rules,
            "original_adaptation": original_adaptation,
            "original_shot_plan": {
                "type": "array",
                "items": shot,
                "minItems": int(min_shots),
                "maxItems": int(max_shots),
            },
            "provenance": provenance,
        },
        "required": [
            "reference_observation",
            "reference_interpretation",
            "reference_strategy",
            "evidence",
            "transfer_rules",
            "original_adaptation",
            "original_shot_plan",
            "provenance",
        ],
    }


_SECTION_FIELDS = {
    "reference_observation": {
        "scalar": (),
        "list": (
            "visual_facts", "editing_facts", "audio_facts", "product_and_brand_facts",
        ),
    },
    "reference_interpretation": {
        "scalar": (
            "core_concept", "creative_thesis", "opening_hook", "hook_mechanism",
            "emotional_promise", "audience_desire", "character_archetype",
        ),
        "list": (
            "status_signals", "aspirational_mechanisms", "psychological_mechanisms",
            "retention_mechanisms", "emotional_progression",
        ),
    },
    "reference_strategy": {
        "scalar": (
            "editing_rhythm.pace", "product_reveal_strategy", "brand_memory_strategy",
        ),
        "list": (
            "visual_grammar.principles", "visual_grammar.composition_patterns",
            "visual_grammar.distance_and_framing", "visual_grammar.color_and_texture",
            "camera_language.principles", "camera_language.framing_patterns",
            "camera_language.lens_or_perspective_patterns", "camera_language.movement_patterns",
            "lighting_language.principles", "lighting_language.contrast_and_direction",
            "lighting_language.motivated_sources", "editing_rhythm.progression",
            "editing_rhythm.shot_duration_patterns", "audio_strategy.observed_structure",
            "audio_strategy.interpreted_function", "audio_strategy.transferable_audio_principles",
        ),
    },
    "transfer_rules": {
        "scalar": (),
        "list": (
            "transferable_principles", "literal_elements_to_avoid", "similarity_risks",
            "brand_specific_elements_not_to_inherit",
        ),
    },
    "original_adaptation": {
        "scalar": (
            "creative_thesis", "new_hook", "new_character_role", "character_behavior",
            "new_brand_world", "new_product_role",
        ),
        "list": (
            "emotional_arc", "visual_rules", "audio_rules", "editing_rules",
            "differentiation_from_reference",
        ),
    },
}

_SHOT_SCALAR_FIELDS = (
    "purpose", "psychological_function", "retention_function", "character_action",
    "expression", "environment", "composition", "framing", "camera",
    "lens_or_perspective", "movement", "lighting", "color_and_texture",
    "product_presence", "audio_function", "continuity_notes", "nano_banana_prompt",
)
_SHOT_LIST_FIELDS = (
    "reference_principles_used", "literal_reference_elements_avoided",
    "differentiation_notes", "uncertainties",
)
_SEEDANCE_FIELDS = (
    "performance", "camera_movement", "pacing", "emotional_goal", "continuity",
)


def creative_positional_layout() -> dict[str, dict[str, list[str]]]:
    """Order is part of the provider contract; changing it requires a schema bump."""

    fields_by_section = {
        **_SECTION_FIELDS,
        "original_shot_plan": {"scalar": _SHOT_SCALAR_FIELDS, "list": _SHOT_LIST_FIELDS},
    }
    return {
        name: {
            block: list(fields[kind])
            for block, kind in (("scalar_values", "scalar"), ("list_values", "list"))
            if fields[kind]
        }
        for name, fields in fields_by_section.items()
    }


def creative_intelligence_provider_schema(min_shots: int, max_shots: int) -> dict[str, Any]:
    """Compact, typed provider contract; the rich v2 contract remains local."""

    if not 1 <= int(min_shots) <= int(max_shots) <= 16:
        raise AdsArtError("El rango de tomas originales debe cumplir 1 <= min <= max <= 16.")
    # Homogeneous, exact-length arrays avoid repeated key enums and tuple schemas.
    # The programmatic prompt layout assigns meaning to each position. Cardinality
    # guarantees slots, not semantic correctness; strict local validation follows.
    layout = creative_positional_layout()

    def positional_section(name: str) -> dict[str, Any]:
        return _object({
            block: {
                "type": "array",
                "items": {"type": "string"} if block == "scalar_values" else _strings(),
                "minItems": len(keys),
                "maxItems": len(keys),
            }
            for block, keys in layout[name].items()
        })
    evidence = _object(
        {
            "evidence_id": {"type": "string"},
            "timestamp_seconds": {"type": "number"},
            "shot_start_seconds": {"type": "number"},
            "shot_end_seconds": {"type": "number"},
            "candidate_timestamps": {"type": "array", "items": {"type": "number"}},
            "evidence_kind": {
                "type": "string",
                "enum": ["visual", "editing", "audio", "product_brand", "mixed"],
            },
            "observed_fact": {"type": "string"},
            "supports": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(EVIDENCE_SUPPORTS)},
            },
        }
    )
    shot = _object(
        {
            "shot_id": {"type": "string"},
            "planned_duration_seconds": {"type": "number"},
            **positional_section("original_shot_plan")["properties"],
            "seedance_direction": _object(
                {
                    "performance": {"type": "string"},
                    "camera_movement": {"type": "string"},
                    "pacing": {"type": "string"},
                    "emotional_goal": {"type": "string"},
                    "continuity": {"type": "string"},
                }
            ),
        }
    )
    provenance = _object(
        {
            "user_provided": _strings(),
            "ai_proposed": _strings(),
            "approved": _strings(),
            "unresolved_inputs": _strings(),
        }
    )
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reference_observation": positional_section("reference_observation"),
            "reference_interpretation": positional_section("reference_interpretation"),
            "reference_strategy": positional_section("reference_strategy"),
            "evidence": {"type": "array", "items": evidence},
            "transfer_rules": positional_section("transfer_rules"),
            "original_adaptation": positional_section("original_adaptation"),
            "original_shot_plan": {
                "type": "array", "items": shot,
                "minItems": int(min_shots), "maxItems": int(max_shots),
            },
            "provenance": provenance,
        },
        "required": [
            "reference_observation", "reference_interpretation", "reference_strategy",
            "evidence", "transfer_rules", "original_adaptation", "original_shot_plan",
            "provenance",
        ],
    }


def _expand_facets(
    section: Any,
    *,
    label: str,
    scalar_fields: tuple[str, ...],
    list_fields: tuple[str, ...],
) -> dict[str, Any]:
    if not isinstance(section, dict):
        raise AdsArtError(f"{label} provider debe ser objeto.")
    _require_keys(section, {"facets"}, f"{label} provider")
    if set(section) != {"facets"}:
        raise AdsArtError(f"{label} provider contiene campos no contratados.")
    result: dict[str, Any] = {}
    seen: set[str] = set()

    def assign(path: str, value: Any) -> None:
        if path in seen:
            raise AdsArtError(f"{label}: faceta duplicada {path!r}.")
        seen.add(path)
        target = result
        parts = path.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = copy.deepcopy(value)

    items = section.get("facets")
    if not isinstance(items, list):
        raise AdsArtError(f"{label}: facets debe ser un array.")
    for item in items:
        if not isinstance(item, dict) or set(item) != {"key", "values"}:
            raise AdsArtError(f"{label}: faceta inválida.")
        key = str(item["key"])
        if not isinstance(item["values"], list) or any(not isinstance(v, str) for v in item["values"]):
            raise AdsArtError(f"{label}.{key}: values debe ser una lista de texto.")
        if key in scalar_fields:
            if len(item["values"]) != 1:
                raise AdsArtError(f"{label}.{key}: la faceta escalar requiere exactamente un valor.")
            assign(key, item["values"][0])
        elif key in list_fields:
            assign(key, item["values"])
        else:
            raise AdsArtError(f"{label}: faceta desconocida {key!r}.")
    missing = (set(scalar_fields) | set(list_fields)) - seen
    if missing:
        raise AdsArtError(f"{label}: faltan facetas obligatorias: {', '.join(sorted(missing))}")
    return result


def _expand_positions(
    section: Any, *, label: str, scalar_fields: tuple[str, ...], list_fields: tuple[str, ...]
) -> dict[str, Any]:
    blocks = {
        block: keys
        for block, keys in (("scalar_values", scalar_fields), ("list_values", list_fields))
        if keys
    }
    if not isinstance(section, dict) or set(section) != set(blocks):
        raise AdsArtError(f"{label}: bloques posicionales requeridos: {', '.join(blocks)}.")
    result: dict[str, Any] = {}
    for block, keys in blocks.items():
        values = section[block]
        if not isinstance(values, list) or len(values) != len(keys):
            raise AdsArtError(f"{label}.{block}: longitud exacta requerida {len(keys)}; no se rellenan posiciones.")
        for index, key in enumerate(keys):
            value = values[index]
            if block == "scalar_values":
                if not isinstance(value, str) or not value.strip():
                    raise AdsArtError(f"{label}.{key}: posición {index} requiere texto no vacío.")
            elif not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise AdsArtError(f"{label}.{key}: posición {index} requiere una lista de texto.")
            target = result
            parts = key.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = copy.deepcopy(value)
    return result


def expand_provider_creative_intelligence(
    provider_response: dict[str, Any], *, provider_schema_version: str | None = None
) -> dict[str, Any]:
    """Deterministically reorganize provider facets into the stable rich v2 master."""

    version = provider_schema_version or CREATIVE_PROVIDER_SCHEMA_VERSION
    if version not in {"1.3.0", "1.4.0", "1.5.0"}:
        raise AdsArtError(f"Provider schema no compatible para expansión local: {version}.")
    positional = version == "1.5.0"
    expand_section = _expand_positions if positional else _expand_facets
    if not isinstance(provider_response, dict):
        raise AdsArtError("La respuesta compacta del proveedor debe ser un objeto.")
    required = set(_SECTION_FIELDS) | {"evidence", "original_shot_plan", "provenance"}
    _require_keys(provider_response, required, "respuesta compacta del proveedor")
    if set(provider_response) != required:
        raise AdsArtError("La respuesta compacta contiene secciones no contratadas.")
    master: dict[str, Any] = {}
    for name, fields in _SECTION_FIELDS.items():
        master[name] = expand_section(
            provider_response[name], label=name,
            scalar_fields=fields["scalar"], list_fields=fields["list"],
        )
    if not isinstance(provider_response["evidence"], list):
        raise AdsArtError("evidence provider debe ser un array.")
    master["evidence"] = copy.deepcopy(provider_response["evidence"])
    for item in master["evidence"]:
        if isinstance(item, dict):
            raw_kind = str(item.get("evidence_kind", ""))
            if raw_kind not in EVIDENCE_KIND_ALIASES:
                raise AdsArtError(f"evidence provider contiene evidence_kind desconocido: {raw_kind!r}.")
            item["evidence_kind"] = EVIDENCE_KIND_ALIASES[raw_kind]
    plan = provider_response["original_shot_plan"]
    if not isinstance(plan, list):
        raise AdsArtError("original_shot_plan provider debe ser un array.")
    master_plan = []
    for index, provider_shot in enumerate(plan, 1):
        if not isinstance(provider_shot, dict):
            raise AdsArtError(f"original_shot_plan provider [{index}] debe ser objeto.")
        blocks = {"scalar_values", "list_values"} if positional else {"facets"}
        required_shot = {"shot_id", "planned_duration_seconds", "seedance_direction"} | blocks
        _require_keys(provider_shot, required_shot, f"original_shot_plan provider [{index}]")
        if set(provider_shot) != required_shot:
            raise AdsArtError(f"original_shot_plan provider [{index}] contiene campos no contratados.")
        expanded = expand_section(
            {block: provider_shot[block] for block in blocks},
            label=f"original_shot_plan[{index}]",
            scalar_fields=_SHOT_SCALAR_FIELDS,
            list_fields=_SHOT_LIST_FIELDS,
        )
        seedance = provider_shot["seedance_direction"]
        if not isinstance(seedance, dict) or set(seedance) != set(_SEEDANCE_FIELDS):
            raise AdsArtError(
                f"original_shot_plan provider [{index}].seedance_direction debe contener "
                + ", ".join(_SEEDANCE_FIELDS)
            )
        master_plan.append(
            {
                "shot_id": (
                    f"shot_{int(match.group(1)):02d}"
                    if (match := re.fullmatch(r"shot_(\d+)", str(provider_shot["shot_id"])))
                    else copy.deepcopy(provider_shot["shot_id"])
                ),
                "planned_duration_seconds": copy.deepcopy(provider_shot["planned_duration_seconds"]),
                **expanded,
                "seedance_direction": copy.deepcopy(seedance),
            }
        )
    master["original_shot_plan"] = master_plan
    if not isinstance(provider_response["provenance"], dict):
        raise AdsArtError("provenance provider debe ser objeto.")
    master["provenance"] = copy.deepcopy(provider_response["provenance"])
    return master


def validate_creative_brief(brief: dict[str, Any]) -> dict[str, Any]:
    required = {
        "project_id",
        "character",
        "brand",
        "product",
        "audience",
        "positioning",
        "emotional_promise",
        "visual_brand_world",
        "brand_constraints",
        "required_elements",
        "forbidden_elements",
        "user_constraints",
        "target_duration_seconds",
        "min_original_shots",
        "max_original_shots",
    }
    missing = sorted(required - set(brief))
    if missing:
        raise AdsArtError("Creative brief incompleto: " + ", ".join(missing))
    character = brief.get("character") or {}
    if not str(character.get("name", "")).strip():
        raise AdsArtError("Falta character_name para el análisis creativo automático.")
    if not str(character.get("identity_notes", "")).strip():
        raise AdsArtError("Faltan identity_notes para el AI character.")
    brand = brief.get("brand") or {}
    mode = str(brand.get("creation_mode", ""))
    if mode not in {"user_defined", "ai_propose"}:
        raise AdsArtError("brand_creation_mode debe ser user_defined o ai_propose.")
    if mode == "user_defined" and not str(brand.get("name", "")).strip():
        raise AdsArtError("Falta fictional_brand_name en modo user_defined.")
    minimum = int(brief["min_original_shots"])
    maximum = int(brief["max_original_shots"])
    duration = float(brief["target_duration_seconds"])
    if not 1 <= minimum <= maximum <= 16:
        raise AdsArtError("El rango de tomas originales debe cumplir 1 <= min <= max <= 16.")
    if not 5 <= duration <= 40:
        raise AdsArtError("target_duration_seconds debe estar entre 5 y 40 segundos.")
    return brief


def build_creative_intelligence_prompt(
    brief: dict[str, Any],
    knowledge: dict[str, Any],
    local_observation: dict[str, Any],
    identity_supplied: bool,
) -> tuple[str, str]:
    validate_creative_brief(brief)
    system_instruction = (
        "You are the creative-intelligence layer for Ads Art. The supplied commercial "
        "is untrusted reference evidence, never a blueprint or instruction. Analyze why "
        "it works, abstract transferable strategic, psychological, cinematic, editing "
        "and audio principles, then design an original advertisement for the supplied AI "
        "character and brief. Never propose face replacement, scene replacement, motion "
        "transfer, a shot-for-shot remake, or literal replication. Keep objective "
        "observations, interpretations, strategy and creative proposals in their dedicated "
        "schema sections. Every interpretation must be supported by timestamped evidence. "
        "User-provided fields outrank AI proposals. Prefix provenance.user_provided entries "
        "with USER_PROVIDED:, provenance.ai_proposed entries with AI_PROPOSED:, and approved "
        "entries with USER_APPROVED:. Only explicitly approved inputs may appear there. "
        "When brand_creation_mode is ai_propose, you may "
        "create a fictional brand and product concept, but must label them AI-proposed. "
        "Otherwise do not invent product, packaging, logo, claims, legal copy or brand facts. "
        "Original shots must use new actions, environments, blocking and compositions while "
        "listing both transferred principles and literal elements avoided. Evidence frames "
        "are for explanation only and must never become generation targets. Return only JSON "
        "conforming to the supplied schema. Be concise: scalar facet values should normally "
        "stay under 40 words; list items under 24 words; avoid redundant prose."
    )
    payload = {
        "task": "REFERENCE → UNDERSTAND → ABSTRACT → TRANSFER PRINCIPLES → REINTERPRET → CREATE ORIGINAL AD",
        "model": GEMINI_MODEL_ID,
        "prompt_version": CREATIVE_PROMPT_VERSION,
        "schema_version": CREATIVE_SCHEMA_VERSION,
        "creative_brief": brief,
        "approved_identity_image_supplied": bool(identity_supplied),
        "reference_video_local_evidence": local_observation,
        "cinematic_knowledge": knowledge.get("concepts", []),
        "output_constraints": {
            "target_duration_seconds": brief["target_duration_seconds"],
            "min_original_shots": brief["min_original_shots"],
            "max_original_shots": brief["max_original_shots"],
            "nano_banana_model": "nano_banana_pro",
            "nano_banana_aspect_ratio": "4:5",
            "nano_banana_resolution": "2k",
            "seedance_model": "seedance_2_5",
            "seedance_mode": "omni_reference",
            "reference_video_or_audio_sent_to_seedance": False,
            "visual_approval_inferred": False,
        },
        "required_distinctions": [
            "reference_observation contains only visible/audible/measured facts",
            "reference_interpretation contains meaning inferred from evidence",
            "reference_strategy contains abstracted mechanisms",
            "original_adaptation and original_shot_plan contain new creative proposals",
        ],
        "compact_provider_contract": {
            "provider_schema_version": CREATIVE_PROVIDER_SCHEMA_VERSION,
            "max_output_tokens": CREATIVE_PROVIDER_MAX_OUTPUT_TOKENS,
            "positional_layout": creative_positional_layout(),
            "positional_rule": (
                "For each section and each original shot, follow positional_layout in exactly the "
                "listed order (zero-based indexing). scalar_values contains one nonempty string per "
                "scalar field; list_values contains one array of strings per list field. "
                "Return only values, never field names or key/value objects. Do not skip, shift, "
                "duplicate or add positions. Keep an empty list in the assigned slot when a list "
                "has no items. Give an explicit evidence-grounded uncertainty when a scalar cannot "
                "be determined, and record it in uncertainties; do not invent content. Review "
                "each position against its field before returning JSON. Array lengths are exact."
            ),
            "seedance_fields": _SEEDANCE_FIELDS,
            "evidence_kind_values": ["visual", "editing", "audio", "product_brand", "mixed"],
            "evidence_support_values": sorted(EVIDENCE_SUPPORTS),
            "evidence_coverage_rule": (
                "Across all evidence items, supports must collectively include every evidence_support_value."
            ),
            "expansion_rule": "Fixed positions are mapped locally without adding or interpreting content.",
        },
    }
    return system_instruction, json_dumps(payload)


def _require_keys(value: dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - set(value))
    if missing:
        raise AdsArtError(f"Respuesta creative intelligence incompleta en {label}: {', '.join(missing)}")


def _require_string_list(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AdsArtError(f"{label} debe ser una lista de texto.")
    result = [item.strip() for item in value if item.strip()]
    if nonempty and not result:
        raise AdsArtError(f"{label} no puede quedar vacío.")
    return result


_LITERAL_REMAKE = re.compile(
    r"\b(recreate|remake|copy|replicate|replace (?:the )?(?:face|character|scene)|"
    r"same (?:pose|composition|blocking|movement|shot)|match (?:the )?reference exactly|"
    r"motion transfer|timestamp|at \d+(?:\.\d+)?\s*s(?:econds?)?)\b",
    re.IGNORECASE,
)


def validate_creative_intelligence(
    response: dict[str, Any],
    *,
    duration_seconds: float,
    target_duration_seconds: float,
    min_shots: int,
    max_shots: int,
) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise AdsArtError("Gemini no devolvió un objeto creative intelligence JSON.")
    root_required = {
        "reference_observation",
        "reference_interpretation",
        "reference_strategy",
        "evidence",
        "transfer_rules",
        "original_adaptation",
        "original_shot_plan",
        "provenance",
    }
    _require_keys(response, root_required, "raíz")
    for section in root_required - {"evidence", "original_shot_plan"}:
        if not isinstance(response.get(section), dict):
            raise AdsArtError(f"{section} debe ser un objeto separado.")

    evidence = response.get("evidence")
    if not isinstance(evidence, list) or not evidence or len(evidence) > 24:
        raise AdsArtError("evidence debe contener evidencia timestamped.")
    evidence_ids: set[str] = set()
    covered: set[str] = set()
    for index, item in enumerate(evidence, 1):
        if not isinstance(item, dict):
            raise AdsArtError(f"evidence[{index}] debe ser un objeto.")
        _require_keys(
            item,
            {"evidence_id", "timestamp_seconds", "shot_start_seconds", "shot_end_seconds", "candidate_timestamps", "evidence_kind", "observed_fact", "supports"},
            f"evidence[{index}]",
        )
        evidence_id = str(item["evidence_id"]).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", evidence_id) or evidence_id in evidence_ids:
            raise AdsArtError(f"evidence_id inválido o duplicado: {evidence_id!r}")
        evidence_ids.add(evidence_id)
        start = float(item["shot_start_seconds"])
        end = float(item["shot_end_seconds"])
        timestamp = float(item["timestamp_seconds"])
        if start < 0 or end <= start or end > float(duration_seconds) + 0.05 or not start <= timestamp <= end:
            raise AdsArtError(f"Evidencia {evidence_id}: timestamp/intervalo fuera del video.")
        candidates = item.get("candidate_timestamps")
        if not isinstance(candidates, list) or not candidates or len(candidates) > 5:
            raise AdsArtError(f"Evidencia {evidence_id}: candidate_timestamps inválido.")
        normalized = []
        for candidate in candidates:
            value = float(candidate)
            if not start <= value <= end or value > float(duration_seconds):
                raise AdsArtError(f"Evidencia {evidence_id}: candidato fuera de su intervalo.")
            normalized.append(round(value, 6))
        if not str(item.get("observed_fact", "")).strip():
            raise AdsArtError(f"Evidencia {evidence_id}: observed_fact vacío.")
        if item.get("evidence_kind") not in {"visual", "editing", "audio", "product_brand", "mixed"}:
            raise AdsArtError(f"Evidencia {evidence_id}: evidence_kind desconocido.")
        supports = set(_require_string_list(item.get("supports"), f"{evidence_id}.supports", nonempty=True))
        if not supports <= EVIDENCE_SUPPORTS:
            raise AdsArtError(f"Evidencia {evidence_id}: supports contiene categorías desconocidas.")
        covered.update(supports)
        item["shot_start_seconds"] = round(start, 6)
        item["shot_end_seconds"] = round(end, 6)
        item["timestamp_seconds"] = round(timestamp, 6)
        item["candidate_timestamps"] = normalized
    required_coverage = set(EVIDENCE_SUPPORTS)
    if not required_coverage <= covered:
        raise AdsArtError("La interpretación carece de evidencia para: " + ", ".join(sorted(required_coverage - covered)))

    plan = response.get("original_shot_plan")
    if not isinstance(plan, list) or not int(min_shots) <= len(plan) <= int(max_shots):
        raise AdsArtError("original_shot_plan quedó fuera del rango configurado.")
    shot_ids: set[str] = set()
    total = 0.0
    generation_fields = (
        "purpose", "psychological_function", "retention_function", "character_action",
        "expression", "environment", "composition", "framing", "camera",
        "lens_or_perspective", "movement", "lighting", "color_and_texture",
        "product_presence", "audio_function", "continuity_notes", "nano_banana_prompt",
    )
    for index, shot in enumerate(plan, 1):
        if not isinstance(shot, dict):
            raise AdsArtError(f"original_shot_plan[{index}] debe ser objeto.")
        schema_required = set(creative_intelligence_schema(min_shots, max_shots)["properties"]["original_shot_plan"]["items"]["required"])
        _require_keys(shot, schema_required, f"original_shot_plan[{index}]")
        shot_id = str(shot["shot_id"]).strip()
        if not re.fullmatch(r"shot_[0-9]{2}", shot_id) or shot_id in shot_ids:
            raise AdsArtError(f"shot_id original inválido o duplicado: {shot_id!r}")
        shot_ids.add(shot_id)
        planned = float(shot["planned_duration_seconds"])
        if planned <= 0:
            raise AdsArtError(f"{shot_id}: duración no positiva.")
        total += planned
        for field in generation_fields:
            value = str(shot.get(field, "")).strip()
            if not value:
                raise AdsArtError(f"{shot_id}.{field} no puede quedar vacío.")
            if _LITERAL_REMAKE.search(value):
                raise AdsArtError(f"{shot_id}.{field} contiene una instrucción de copia literal.")
        for field in ("reference_principles_used", "literal_reference_elements_avoided", "differentiation_notes"):
            shot[field] = _require_string_list(shot.get(field), f"{shot_id}.{field}", nonempty=True)
        seedance = shot.get("seedance_direction")
        if not isinstance(seedance, dict):
            raise AdsArtError(f"{shot_id}.seedance_direction debe ser objeto.")
        _require_keys(seedance, {"performance", "camera_movement", "pacing", "emotional_goal", "continuity"}, f"{shot_id}.seedance_direction")
        if any(not str(seedance.get(key, "")).strip() for key in seedance):
            raise AdsArtError(f"{shot_id}.seedance_direction contiene campos vacíos.")
        if _LITERAL_REMAKE.search(" ".join(str(value) for value in seedance.values())):
            raise AdsArtError(f"{shot_id}.seedance_direction contiene una instrucción de copia literal.")
        shot["uncertainties"] = _require_string_list(shot.get("uncertainties"), f"{shot_id}.uncertainties")
        shot["planned_duration_seconds"] = round(planned, 3)
    tolerance = max(0.25, float(target_duration_seconds) * 0.05)
    if abs(total - float(target_duration_seconds)) > tolerance:
        raise AdsArtError(
            f"La suma del plan ({total:.3f}s) no coincide con target_duration_seconds "
            f"({float(target_duration_seconds):.3f}s)."
        )

    provenance = response["provenance"]
    for field in ("user_provided", "ai_proposed", "approved", "unresolved_inputs"):
        provenance[field] = _require_string_list(provenance.get(field), f"provenance.{field}")
    prefixes = {
        "user_provided": "USER_PROVIDED:",
        "ai_proposed": "AI_PROPOSED:",
        "approved": "USER_APPROVED:",
    }
    for field, prefix in prefixes.items():
        invalid = [item for item in provenance[field] if not item.startswith(prefix)]
        if invalid:
            raise AdsArtError(f"provenance.{field} debe etiquetar cada entrada con {prefix}")
    response["validation"] = {
        "schema_version": CREATIVE_SCHEMA_VERSION,
        "separation_validated": True,
        "evidence_ranges_validated": True,
        "evidence_support_coverage_validated": True,
        "originality_guard_validated": True,
        "target_duration_validated": True,
        "visual_approval_inferred": False,
    }
    return response


def creative_provider_request_signature(
    *,
    video_sha256: str,
    video_bytes: int,
    identity_sha256: str,
    brief: dict[str, Any],
    knowledge_sha256: str,
    local_detector: dict[str, Any],
) -> dict[str, Any]:
    """Fingerprint only inputs that can change the paid provider request."""

    return {
        "product_paradigm": "reference_driven_advertising_intelligence_original_generation",
        "video_sha256": video_sha256,
        "video_bytes": int(video_bytes),
        "identity_sha256": identity_sha256,
        "creative_brief": brief,
        "knowledge_sha256": knowledge_sha256,
        "model": GEMINI_MODEL_ID,
        "generation_config": GEMINI_GENERATION_CONFIG,
        "prompt_version": CREATIVE_PROMPT_VERSION,
        "provider_schema_version": CREATIVE_PROVIDER_SCHEMA_VERSION,
        "max_output_tokens": CREATIVE_PROVIDER_MAX_OUTPUT_TOKENS,
        "local_detector": local_detector,
    }


def creative_materialization_signature(provider_request_fingerprint: str) -> dict[str, Any]:
    """Fingerprint local expansion/validation independently from the paid request."""

    return {
        "provider_request_fingerprint": provider_request_fingerprint,
        "schema_version": CREATIVE_SCHEMA_VERSION,
        "expander_version": CREATIVE_EXPANDER_VERSION,
    }


def creative_signature(**kwargs: Any) -> dict[str, Any]:
    """Backward-compatible full signature used by older callers and records."""

    provider = creative_provider_request_signature(**kwargs)
    return {
        **provider,
        "schema_version": CREATIVE_SCHEMA_VERSION,
        "expander_version": CREATIVE_EXPANDER_VERSION,
    }
