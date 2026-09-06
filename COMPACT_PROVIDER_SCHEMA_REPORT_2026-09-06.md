# Ads Art v2 — compact provider schema report

Date: 2026-09-06

## Result

```text
compact typed provider response
        -> deterministic local expander
        -> rich Creative Intelligence master v2
        -> viewers / drafts / Nano preparation / Seedance preparation
```

No Gemini, Higgsfield, Nano Banana or Seedance request was made while implementing or
testing this change.

## Versions

- Model: `gemini-3.6-flash` (unchanged)
- Transport: Gemini Developer API `generateContent` (unchanged)
- Master schema: `2.0.0` (unchanged)
- Provider schema: `1.3.0`
- Expander: `1.3.0`
- Prompt: `ads_art_reference_intelligence_v8_bounded_output`

All three contract versions enter the cache signature, so an older response cannot be
mixed with the compact provider and new expander.

## Measured complexity

These are descriptive engineering measurements, not claimed Google limits.

| Contract | UTF-8 bytes | Properties | Schema objects | Constraints | Depth |
|---|---:|---:|---:|---:|---:|
| Known-working v1 | 2,293 | 30 | 47 | 13 | 10 |
| Previous rich v2 provider | 8,592 | 104 | 166 | 49 | 8 |
| Rejected compact v2 with `$defs/$ref` | 4,454 | 31 | 60 | 11 | 6 |
| Accepted inline v2; incomplete Seedance | 3,194 | 40 | 76 | 17 | 10 |
| Inline v2 with explicit Seedance object | 3,543 | 46 | 83 | 18 | 10 |
| Inline v2 with canonical evidence enums | 3,820 | 46 | 83 | 20 | 10 |
| Rich v2 master | 8,592 | 104 | 166 | 49 | 8 |

## Synthetic provider excerpt

All eight top-level sections remain required. Repeated fields use typed facets:

```json
{
  "reference_observation": {
    "facets": [
      {"key": "visual_facts", "values": ["A lone performer is held before the cut."]},
      {"key": "editing_facts", "values": ["Pace increases after the hook."]},
      {"key": "audio_facts", "values": ["The score rises before the reveal."]},
      {"key": "product_and_brand_facts", "values": ["Brand material appears near the close."]}
    ]
  },
  "original_shot_plan": [{
    "shot_id": "shot_01",
    "planned_duration_seconds": 5.0,
    "facets": [
      {"key": "purpose", "values": ["Build a new visual premise."]},
      {"key": "character_action", "values": ["She opens an aperture in a mineral wall."]},
      {"key": "nano_banana_prompt", "values": ["Original nocturnal mineral-gallery keyframe."]},
      {"key": "reference_principles_used", "values": ["controlled withholding"]},
      {"key": "literal_reference_elements_avoided", "values": ["performer", "set"]},
      {"key": "differentiation_notes", "values": ["new action and environment"]},
      {"key": "uncertainties", "values": ["Final object geometry needs review."]}
    ],
    "seedance_direction": {
      "performance": "A measured, curious reveal.",
      "camera_movement": "Restrained lateral drift.",
      "pacing": "Slow build and concise reveal.",
      "emotional_goal": "Turn distance into self-possession.",
      "continuity": "Maintain the original world and approved character."
    }
  }]
}
```

This excerpt omits other mandatory sections and facets only for readability. A real
response with an omission is rejected.

## Expanded master excerpt

```json
{
  "reference_observation": {
    "visual_facts": ["A lone performer is held before the cut."],
    "editing_facts": ["Pace increases after the hook."],
    "audio_facts": ["The score rises before the reveal."],
    "product_and_brand_facts": ["Brand material appears near the close."]
  },
  "original_shot_plan": [{
    "shot_id": "shot_01",
    "planned_duration_seconds": 5.0,
    "purpose": "Build a new visual premise.",
    "character_action": "She opens an aperture in a mineral wall.",
    "reference_principles_used": ["controlled withholding"],
    "literal_reference_elements_avoided": ["performer", "set"],
    "differentiation_notes": ["new action and environment"],
    "nano_banana_prompt": "Original nocturnal mineral-gallery keyframe.",
    "seedance_direction": {"performance": "A measured, curious reveal."},
    "uncertainties": ["Final object geometry needs review."]
  }]
}
```

The expander only relocates values supplied by Gemini. It never synthesizes defaults.
Unknown, duplicate, missing, cross-type or malformed facets fail locally. The rich
validator then checks evidence ranges and coverage, shot count, total duration,
provenance prefixes and originality guards.

## Request and state safeguards

Before API-key access or network, Ads Art checks the provider schema against the
documented keyword subset. `$schema` remains removed. Metrics for both provider and
master contracts are persisted with successful results.

New state records distinguish `analysis_attempts`, `model_preflight_attempts`,
`upload_attempts` and `generate_content_attempts`. Historical `inference_attempts`
meant node-level recorded openings, not proven POSTs. It is not rewritten; if a future
state is derived from such a marker its old value is retained as
`legacy_inference_attempts`.

## Remaining risk

Provider schema `1.0.0` was rejected by a real `generateContent` call. Version `1.1.0`
removed `$defs`, `$ref` and large key enums and was accepted, resolving the 400, but the
model omitted generic Seedance facets and local validation stopped completion. Version
`1.2.0` makes the five Seedance fields an explicit required object while retaining the
typed `{key, values[]}` contract elsewhere. Rejected raw provider responses are now
persisted for diagnosis without a repeat call. Local tests prove
request serialization, supported keywords, deterministic expansion
and downstream validation. Only one controlled real call can prove provider acceptance
and reliable completion of every facet. Automatic retries remain disabled.

Schema 1.2.0 was accepted and returned all required creative fields, but used free-form
evidence support labels. Schema 1.3.0 makes both `evidence_kind` and `supports` canonical
enums and tells the model to cover every support category collectively. The preserved
1.2.0 response proved that these were the only remaining validation blockers.

The first 1.3.0 response reached about 32 KB but was not parseable at its end, consistent
with the configured 8,192-token output ceiling. The Creative Intelligence call is now
bounded at 16,384 output tokens and asks for concise facet values. Future parse failures
persist raw text, usage and finish reason before stopping; the v1 default remains 8,192.

## Controlled verification after the fix

The single authorized verification with provider schema `1.3.0` and a 16,384-token
ceiling completed successfully. Model preflight, upload, remote processing and
`generateContent` each ran exactly once; the uploaded file was deleted afterward.
Gemini reported 16,493 input tokens and 7,748 output tokens. The expanded master result
passed local validation and was saved in the project cache. This confirms that the
earlier 400 was eliminated by the reference-free compact contract; it does not prove
that every documented `$defs`/`$ref` combination is rejected generally.

The persisted creative brief used by this diagnostic still specified 4–7 shots, so the
result contains four shots. No second provider call was made to change that independent
brief setting.
