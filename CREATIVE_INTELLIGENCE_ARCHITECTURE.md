# Ads Art Creative Intelligence Architecture

```text
Gemini positional provider schema 1.5.0 (offline validated; remote acceptance pending)
  -> raw provider response persisted
  -> deterministic expander 1.5.0
  -> rich master schema 2.0.0
```

The provider boundary isolates Gemini schema complexity without changing downstream
consumers. Positional arrays reserve every scalar/list slot with exact lengths. The
prompt and expander share the same field order. Wrong lengths/types/empty scalars fail
without synthesized defaults. Positions cannot guarantee semantic correctness.
The boundary deliberately avoids `$defs/$ref`: provider schema 1.0.0 used them and was
rejected by a real `gemini-3.6-flash:generateContent` request with `INVALID_ARGUMENT`.
Schema 1.1.0 was accepted but omitted generic Seedance facets; 1.2.0 therefore makes
the five Seedance direction fields an explicit required object.
Schema 1.2.0 then demonstrated successful inference but free-form evidence labels;
1.3.0 constrains evidence kinds/supports to canonical enums and requires full coverage.
1.4.0 added facet-key enums and exact facet counts, but a real request returned 400 with
no field-specific explanation. 1.5.0 removes key/value wrappers and facet-key enums,
keeping small evidence enums and the explicit five-field Seedance direction object.
Provider request identity excludes local expander versions; both raw lookup and failed
attempt suppression use the provider identity, independently of master materialization.

## Decision

Ads Art v2 is a reference-driven advertising intelligence system. The reference
commercial is an analysis corpus; generated assets are original targets derived from
abstract principles and a new character/brand/product brief.

## Boundaries

```text
REFERENCE SIDE                              ORIGINAL GENERATION SIDE

video + audio                               approved AI character
local cuts                                  fictional brand/product brief
timestamped evidence                        original adaptation
        |                                   original shot plan
        v                                           |
Gemini observation / interpretation                v
/ strategy / transfer rules                Nano original keyframe
        |                                           |
        +------ principles only --------------------+
                                                    v
                                          human visual approval
                                                    |
                                                    v
                                             Seedance animation
```

There is no media edge from the reference side to Nano or Seedance. Evidence frame
paths exist only inside the intelligence record and preview output.

## Components

### `ads_art_creative.py`

Pure schema, prompt, brief validation, response validation, provenance rules,
originality guard and semantic cache signature. It has no provider, ComfyUI or media
side effects.

### `ads_art_creative_nodes.py`

- `AdsArtCreativeBrief`: typed user/AI authority and duration/shot controls.
- `AdsArtGeminiCreativeIntelligence`: local preflight, cache-first automatic inference,
  evidence materialization and v2 persistence.
- `AdsArtCreativeIntelligenceViewer`: compact inspection of master sections.
- `AdsArtOriginalShotDraft`: persistent non-empty manual overrides.
- `AdsArtPrepareOriginalKeyframe`: local Nano request containing identity only.
- `AdsArtPrepareOriginalSeedanceShot`: original-keyframe-only Seedance contract.

### Reused v1 infrastructure

- exact Gemini transport and availability preflight;
- video/audio upload behavior, usage and cost extraction;
- local video metadata, cut detection, candidate quality and frame extraction;
- `ProjectStore`, request validation and persistence;
- Higgsfield official CLI submit/poll/recovery/download implementation;
- Nano/Seedance model locks and explicit paid submission gate;
- assembly after accepted clips.

## Automatic state machine

```text
INPUT VALIDATION
   | failure -> STOP (no network)
   v
FINGERPRINT + CACHE LOOKUP
   | completed -> CACHE HIT
   | started/failed/unknown -> STOP unless explicit recovery override
   v
KEY + MODEL PREFLIGHT
   | failure -> STOP before upload
   v
ONE UPLOAD -> FILE ACTIVE -> ONE generateContent
   | uncertain -> persist unknown; no retry
   v
SCHEMA + EVIDENCE + ORIGINALITY VALIDATION
   | failure -> persist failure; no retry
   v
EXTRACT REFERENCE EVIDENCE FRAMES
   v
PERSIST MASTER / ADAPTATION / ORIGINAL SHOT PLAN -> READY
```

Gemini analysis has no human confirmation. Paid generation remains a separate state
transition requiring `confirm_paid_submission=true`.

## Schema evolution

- v1 Gemini response: schema `1.0.0`, reference shots plus generation proposals.
- v2 creative intelligence: schema `2.0.0`, strict reference/proposal boundary.

The v2 cache and persistence roots are new. No in-place conversion is attempted because
the old semantic meaning cannot be safely upgraded without a new model response. Old
records remain readable evidence of prior behavior.

## Validation guarantees and limits

Verified automatically:

- field/type completeness;
- timestamp and interval bounds;
- declared evidence coverage;
- shot range and total planned duration;
- provenance labels;
- literal remake phrases in generation fields;
- no reference media in Nano/Seedance requests;
- no automatic visual approval or paid submission.

Not provable by deterministic validation alone:

- whether every Gemini interpretation is psychologically correct;
- perceptual similarity beyond explicit text/routing rules;
- creative quality of ungenerated keyframes and clips.

Those limits are surfaced as review and approval gates at the asset-generation boundary,
not as a manual gate before creative intelligence.
