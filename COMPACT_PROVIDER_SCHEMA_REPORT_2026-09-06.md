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
- Provider schema: `1.0.0`
- Expander: `1.0.0`
- Prompt: `ads_art_reference_intelligence_v4_compact_provider`

All three contract versions enter the cache signature, so an older response cannot be
mixed with the compact provider and new expander.

## Measured complexity

These are descriptive engineering measurements, not claimed Google limits.

| Contract | UTF-8 bytes | Properties | Schema objects | Constraints | Depth |
|---|---:|---:|---:|---:|---:|
| Known-working v1 | 2,293 | 30 | 47 | 13 | 10 |
| Previous rich v2 provider | 8,592 | 104 | 166 | 49 | 8 |
| Compact v2 provider | 4,454 | 31 | 60 | 11 | 6 |
| Rich v2 master | 8,592 | 104 | 166 | 49 | 8 |

## Synthetic provider excerpt

All eight top-level sections remain required. Repeated fields use typed facets:

```json
{
  "reference_observation": {
    "scalar_facets": [],
    "list_facets": [
      {"key": "visual_facts", "values": ["A lone performer is held before the cut."]},
      {"key": "editing_facts", "values": ["Pace increases after the hook."]},
      {"key": "audio_facts", "values": ["The score rises before the reveal."]},
      {"key": "product_and_brand_facts", "values": ["Brand material appears near the close."]}
    ]
  },
  "original_shot_plan": [{
    "shot_id": "shot_01",
    "planned_duration_seconds": 5.0,
    "scalar_facets": [
      {"key": "purpose", "value": "Build a new visual premise."},
      {"key": "character_action", "value": "She opens an aperture in a mineral wall."},
      {"key": "nano_banana_prompt", "value": "Original nocturnal mineral-gallery keyframe."}
    ],
    "list_facets": [
      {"key": "reference_principles_used", "values": ["controlled withholding"]},
      {"key": "literal_reference_elements_avoided", "values": ["performer", "set"]},
      {"key": "differentiation_notes", "values": ["new action and environment"]},
      {"key": "uncertainties", "values": ["Final object geometry needs review."]}
    ],
    "seedance_facets": [
      {"key": "performance", "value": "A measured, curious reveal."}
    ]
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

Local tests prove request serialization, supported keywords, deterministic expansion
and downstream validation. Only one controlled real call can prove provider acceptance
and reliable completion of every facet. Automatic retries remain disabled.
