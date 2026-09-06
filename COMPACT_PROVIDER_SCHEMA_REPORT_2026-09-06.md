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

## Provider schema 1.4.0: exact facets and durable HTTP 200 responses

A later HTTP 200 exposed a mismatch in schema 1.3.0: the provider accepted any number of
generic `{key, values}` facets, while the deterministic expander required every master
facet exactly once. One shot omitted `composition`; expansion therefore failed locally
after the paid inference had completed.

Schema 1.4.0 keeps the same 46 property declarations and reference-free shape. Each
section now supplies its own allowed-key enum and exact `minItems`/`maxItems` count. Prompt
`ads_art_reference_intelligence_v9_exact_facets` derives and lists required keys directly
from `_SECTION_FIELDS`, `_SHOT_SCALAR_FIELDS` and `_SHOT_LIST_FIELDS`. Duplicate, missing
and unknown facets remain hard local errors; the expander never synthesizes content.

| Metric | 1.3.0 | 1.4.0 |
|---|---:|---:|
| serialized bytes | 3,820 | 5,707 |
| property declarations | 46 | 46 |
| constraint declarations | 20 | 38 |
| schema objects | 83 | 83 |
| maximum structural depth | 10 | 10 |

The added bytes are enums and exact cardinalities, not a return to the 104-property
master schema.

Provider-request and local-materialization fingerprints are now separate. A successful
provider JSON is atomically stored under
`analysis/creative_intelligence/provider_responses/<provider_request_fingerprint>.json`
before expansion, validation or evidence extraction. Changing only the expander/master
validation reprocesses that record locally; changing provider schema, prompt, model or
request inputs prevents incompatible reuse.

The state machine distinguishes `provider_response_received`, `expansion_failed`,
`master_validation_failed`, `materialization_failed` and `completed`, with separate
counters for generate attempts/successes, received responses and both local failure
classes.

The raw JSON from the real `composition` failure was recovered from its legacy
`failed_provider` record and archived in the new store. Its usage, cost, response ID and
detailed timings were never persisted by the old code and remain explicitly unavailable.
Because it lacks mandatory semantic content and belongs to provider schema 1.3.0, it
cannot produce a completed 1.4.0 master without inventing content and cannot trigger an
automatic paid retry.

## Provider schema 1.5.0: fixed positions, offline verification

The next real 1.4.0 attempt returned HTTP 400 `INVALID_ARGUMENT` during inference. The
state records one generate attempt, zero successes and zero provider responses. Google
returned only "Request contains an invalid argument." This confirms rejection of that
request, not which individual enum/cardinality/complexity limit was responsible.
The historical 1.4.0 and missing-composition 1.3.0 records remain unchanged in this update.

Version 1.5.0 replaces `{key, values}` collections with two homogeneous array blocks:
`scalar_values` is an exact-length array of strings; `list_values` is an exact-length
array of string arrays. Sections without scalar fields omit that block. No `$defs`,
`$ref`, `prefixItems` or facet-key enums are used. Evidence keeps its two small enums;
the existing explicit Seedance direction object remains part of each shot.

| Section | scalar_values length | list_values length |
|---|---:|---:|
| reference_observation | absent | 4 |
| reference_interpretation | 7 | 5 |
| reference_strategy | 3 | 16 |
| transfer_rules | absent | 4 |
| original_adaptation | 6 | 5 |
| each original shot | 17 | 4 |

In every shot `scalar_values[6]` is `composition` and `[7]` is `framing`. Programmatic
`positional_layout` in prompt `ads_art_reference_intelligence_v10_positional` specifies
all positions in order; expander `1.5.0` maps them without interpretation. Incorrect
lengths/types/unknown blocks or blank scalar values fail. Existing rich master validation
and the eight conceptual sections remain intact. Expander-only updates do not change
the provider prompt. Historical 1.3/1.4 facets require explicit version dispatch; missing
historical content remains missing.

| Metric (same 4–6 shot range) | 1.4.0 | 1.5.0 |
|---|---:|---:|
| serialized bytes | 5,707 | 3,706 |
| property declarations | 46 | 38 |
| constraint declarations | 38 | 34 |
| schema objects | 83 | 73 |
| maximum structural depth | 10 | 8 |

Official [structured-output guidance](https://ai.google.dev/gemini-api/docs/structured-output)
and the [generateContent reference](https://ai.google.dev/api/generate-content) list
`items`, `minItems` and `maxItems` in the supported subset. Google also warns that schema
complexity can cause rejection and schema-compliant values can still be semantically
incorrect. Exact counts reserve slots, but cannot prove that text was assigned to the
right concept; a same-type swap can pass structural validation. No claim of semantic
or provider-acceptance guarantee is made.

Offline verification used the installed ComfyUI `venv_comfy` interpreter with
`google-genai 2.22.0`: 76 tests passed, none skipped. This includes full SDK request
serialization through `httpx.MockTransport` with sockets blocked, deterministic complete
master reconstruction, every positional boundary/type, explicit legacy dispatch,
cache reuse on local changes and suppression of failed/unknown provider retries after
an expander bump. No real Gemini/Higgsfield call was made. Workflows and approved inputs
were not rewritten. The installed paid submission nodes remain disabled with false
confirmations. Restart ComfyUI to load the code; running analysis after the provider
contract change can require a new paid request and is pending explicit authorization.
