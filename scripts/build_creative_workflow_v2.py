"""Build the portable Ads Art creative-intelligence v2 workflow deterministically."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "workflows" / "ads_art_creative_intelligence_v2.json"


def load_package():
    spec = importlib.util.spec_from_file_location(
        "ads_art_workflow_builder_package",
        REPO_ROOT / "__init__.py",
        submodule_search_locations=[str(REPO_ROOT)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = package
    assert spec.loader is not None
    spec.loader.exec_module(package)
    return package


PACKAGE = load_package()
PRIMITIVES = {"STRING", "INT", "FLOAT", "BOOLEAN"}


def _type_name(definition: Any) -> str:
    raw = definition[0]
    return "COMBO" if isinstance(raw, list) else str(raw)


def _default(definition: Any) -> Any:
    raw = definition[0]
    options = definition[1] if len(definition) > 1 and isinstance(definition[1], dict) else {}
    if "default" in options:
        return options["default"]
    if isinstance(raw, list):
        return raw[0]
    return {"STRING": "", "INT": 0, "FLOAT": 0.0, "BOOLEAN": False}.get(str(raw))


def custom_node(node_id: int, class_type: str, title: str, pos: tuple[int, int], *, values: dict[str, Any] | None = None, mode: int = 0, size: tuple[int, int] = (390, 420)) -> dict[str, Any]:
    cls = PACKAGE.NODE_CLASS_MAPPINGS[class_type]
    declared = cls.INPUT_TYPES()
    inputs = []
    widgets = []
    values = values or {}
    for section in ("required", "optional"):
        for name, definition in declared.get(section, {}).items():
            input_type = _type_name(definition)
            item: dict[str, Any] = {"name": name, "type": input_type, "link": None}
            raw = definition[0]
            if isinstance(raw, list) or str(raw) in PRIMITIVES:
                item["widget"] = {"name": name}
                widgets.append(values.get(name, _default(definition)))
            inputs.append(item)
    outputs = [
        {"name": name, "type": output_type, "slot_index": index, "links": []}
        for index, (name, output_type) in enumerate(zip(cls.RETURN_NAMES, cls.RETURN_TYPES))
    ]
    return {
        "id": node_id,
        "type": class_type,
        "pos": list(pos),
        "size": list(size),
        "flags": {},
        "order": node_id - 1,
        "mode": mode,
        "inputs": inputs,
        "outputs": outputs,
        "title": title,
        "properties": {"Node name for S&R": class_type},
        "widgets_values": widgets,
    }


def load_image(node_id: int, title: str, pos: tuple[int, int], image: str, *, mode: int = 0) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "LoadImage",
        "pos": list(pos),
        "size": [330, 310],
        "flags": {},
        "order": node_id - 1,
        "mode": mode,
        "inputs": [
            {"name": "image", "type": "COMBO", "widget": {"name": "image"}, "link": None},
            {"name": "upload", "type": "IMAGEUPLOAD", "widget": {"name": "upload"}, "link": None},
        ],
        "outputs": [
            {"name": "IMAGE", "type": "IMAGE", "slot_index": 0, "links": []},
            {"name": "MASK", "type": "MASK", "slot_index": 1, "links": []},
        ],
        "title": title,
        "properties": {"Node name for S&R": "LoadImage"},
        "widgets_values": [image, "image"],
    }


def preview_image(node_id: int, title: str, pos: tuple[int, int]) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "PreviewImage",
        "pos": list(pos),
        "size": [380, 420],
        "flags": {},
        "order": node_id - 1,
        "mode": 0,
        "inputs": [{"name": "images", "type": "IMAGE", "link": None}],
        "outputs": [],
        "title": title,
        "properties": {"Node name for S&R": "PreviewImage"},
        "widgets_values": [],
    }


nodes = [
    custom_node(1, "AdsArtCreativeBrief", "00 — Project / Fictional Brand / AI Character", (40, 80), values={
        "project_id": "ads_art_project_001",
        "character_name": "Madame X",
        "identity_notes": "",
        "character_personality": "Quiet confidence, restrained sensuality and visual exclusivity, translated through the approved Madame X identity without copying the reference performer.",
        "character_archetype": "An enigmatic, self-possessed cultural icon.",
        "character_style_constraints": "Preserve the approved face, profile, long neck, dark auburn hair and black evening-wear identity cues.",
        "brand_creation_mode": "ai_propose",
        "fictional_brand_name": "",
        "product_category": "",
        "product_description": "",
        "audience": "",
        "positioning": "",
        "emotional_promise": "",
        "visual_brand_world": "",
        "brand_constraints": "Everything proposed must remain fictional and visibly differentiated from Dior and J'adore.",
        "required_elements": "One approved AI character; an original hook; an original product/brand proposal clearly labeled AI PROPOSED.",
        "forbidden_elements": "Dior name or logo; J'adore bottle; original performer likeness; literal reference scenes, poses, blocking, composition, claims or packaging.",
        "user_constraints": "Transfer only abstract strategic, psychological, cinematic, editing and audio principles. Create a genuinely original advertisement.",
        "target_duration_seconds": 15,
        "min_original_shots": 4,
        "max_original_shots": 7,
    }, size=(470, 880)),
    load_image(2, "00b — Approved AI Character (Madame X)", (560, 80), "Ads Art - Madame X approved.png"),
    custom_node(3, "AdsArtGeminiCreativeIntelligence", "02 — Automatic Gemini Creative Intelligence", (980, 80), values={
        "reference_video": "J' ADORE - DIOR.mp4",
        "model": "gemini-3.6-flash",
        "analysis_mode": "faithful_principles",
        "scene_threshold": 0.22,
        "min_reference_shot_seconds": 0.5,
        "local_detector_fps": 6.0,
        "identity_approved": True,
        "reuse_matching_analysis": True,
        "allow_retry_after_unknown": False,
        "upload_retries": 1,
        "file_poll_attempts": 60,
    }, size=(430, 610)),
    preview_image(4, "03 — REFERENCE EVIDENCE ONLY — never generation targets", (1460, 80)),
    custom_node(5, "AdsArtCreativeIntelligenceViewer", "03a — Creative DNA / Observation vs Interpretation", (1900, 40), values={"section": "creative_dna"}, size=(390, 240)),
    custom_node(6, "AdsArtCreativeIntelligenceViewer", "03b — Psychology / Hook / Retention", (2320, 40), values={"section": "psychology_and_hooks"}, size=(390, 240)),
    custom_node(7, "AdsArtCreativeIntelligenceViewer", "03c — Visual / Camera / Lighting Grammar", (1900, 330), values={"section": "visual_camera_lighting"}, size=(390, 240)),
    custom_node(8, "AdsArtCreativeIntelligenceViewer", "03d — Editing / Rhythm / Audio Strategy", (2320, 330), values={"section": "editing_and_audio"}, size=(390, 240)),
    custom_node(9, "AdsArtCreativeIntelligenceViewer", "04 — Transfer Rules / Do Not Copy", (1900, 650), values={"section": "transfer_rules"}, size=(390, 240)),
    custom_node(10, "AdsArtCreativeIntelligenceViewer", "04b — Original Adaptation Strategy", (2320, 650), values={"section": "original_adaptation"}, size=(390, 240)),
    custom_node(11, "AdsArtCreativeIntelligenceViewer", "05 — Complete Original Shot Plan", (1900, 940), values={"section": "original_shot_plan"}, size=(390, 240)),
    custom_node(12, "AdsArtCreativeIntelligenceViewer", "05b — User / AI / Approved / Unresolved", (2320, 940), values={"section": "provenance_and_unresolved"}, size=(390, 240)),
    custom_node(13, "AdsArtOriginalShotDraft", "05c — Editable Original Shot 01", (2760, 80), values={"shot_number": 1}, size=(440, 540)),
    custom_node(14, "AdsArtPrepareOriginalKeyframe", "06 — Prepare ORIGINAL Nano Keyframe (local only)", (3240, 80), values={"shot_number": 1, "identity_approved": True, "manual_prompt_adjustments": ""}, size=(430, 390)),
    custom_node(15, "AdsArtSubmitJob", "06b — Nano Banana Pro submit — PAID / OFF", (3710, 80), values={"confirm_paid_submission": False, "minimum_credits_after": 0.0}, mode=2, size=(370, 260)),
    load_image(16, "07 — Approved ORIGINAL keyframe — replace after review", (3240, 560), "Ads Art - Madame X approved.png", mode=2),
    custom_node(17, "AdsArtPrepareOriginalSeedanceShot", "08 — Prepare Seedance from approved ORIGINAL keyframe", (3710, 500), values={
        "shot_id": "shot_01", "keyframe_approved": False, "identity_approved": True,
        "performance": "", "camera_trajectory": "", "rhythm": "", "continuity": "",
        "approved_keyframe_observations": "", "seedance_prompt_adjustments": "",
        "generated_duration_seconds": 5, "final_edit_duration_seconds": 5.0,
        "video_aspect_ratio": "auto", "approve_aspect_adaptation": False,
        "resolution": "1080p", "generate_native_audio": False, "bitrate_mode": "standard",
    }, mode=2, size=(440, 700)),
    custom_node(18, "AdsArtSubmitJob", "08b — Seedance submit — PAID / OFF", (4190, 500), values={"confirm_paid_submission": False, "minimum_credits_after": 0.0}, mode=2, size=(370, 260)),
    custom_node(19, "AdsArtAssembleClips", "09 — Assembly / Final (enable after accepted clips)", (4190, 900), values={
        "accepted_clip_paths": "", "reference_commercial_path": "J' ADORE - DIOR.mp4",
        "audio_treatment": "original", "music_path": "", "output_filename": "ads_art_original_final.mp4",
    }, mode=2, size=(430, 420)),
]


node_by_id = {node["id"]: node for node in nodes}
links: list[list[Any]] = []


def connect(source_id: int, output_name: str, target_id: int, input_name: str) -> None:
    source = node_by_id[source_id]
    target = node_by_id[target_id]
    source_slot = next(index for index, item in enumerate(source["outputs"]) if item["name"] == output_name)
    target_slot = next(index for index, item in enumerate(target["inputs"]) if item["name"] == input_name)
    link_id = len(links) + 1
    link_type = source["outputs"][source_slot]["type"]
    if target["inputs"][target_slot]["type"] != link_type:
        raise ValueError(f"Type mismatch {source_id}.{output_name} -> {target_id}.{input_name}")
    links.append([link_id, source_id, source_slot, target_id, target_slot, link_type])
    source["outputs"][source_slot]["links"].append(link_id)
    target["inputs"][target_slot]["link"] = link_id


connect(1, "creative_project", 3, "creative_project")
connect(2, "IMAGE", 3, "approved_identity")
connect(3, "reference_evidence_frames", 4, "images")
for viewer_id in range(5, 13):
    connect(3, "creative_intelligence", viewer_id, "creative_intelligence")
connect(3, "creative_intelligence", 13, "creative_intelligence")
connect(1, "creative_project", 14, "creative_project")
connect(3, "creative_intelligence", 14, "creative_intelligence")
connect(2, "IMAGE", 14, "approved_identity")
connect(13, "original_shot_draft", 14, "original_shot_draft")
connect(14, "original_keyframe_request", 15, "request")
connect(1, "compatible_project", 17, "project")
connect(16, "IMAGE", 17, "approved_original_keyframe")
connect(2, "IMAGE", 17, "approved_identity")
connect(13, "original_shot_draft", 17, "original_shot_draft")
connect(17, "seedance_request", 18, "request")
connect(1, "compatible_project", 19, "project")


groups = [
    {"id": 1, "title": "00 — PROJECT / FICTIONAL BRAND / AI CHARACTER", "bounding": [10, 20, 900, 980], "color": "#3f789e", "font_size": 24, "flags": {}},
    {"id": 2, "title": "01–02 — REFERENCE COMMERCIAL → AUTOMATIC CREATIVE INTELLIGENCE", "bounding": [930, 20, 930, 760], "color": "#6b4c9a", "font_size": 24, "flags": {}},
    {"id": 3, "title": "03 — REFERENCE EVIDENCE (NOT GENERATION TARGETS)", "bounding": [1410, 20, 430, 520], "color": "#9b6b3f", "font_size": 22, "flags": {}},
    {"id": 4, "title": "03–05 — INSPECT / TRANSFER / ORIGINAL AD PLAN", "bounding": [1870, 0, 880, 1230], "color": "#477a58", "font_size": 24, "flags": {}},
    {"id": 5, "title": "05–06 — ORIGINAL SHOT → NANO KEYFRAME", "bounding": [2730, 20, 1380, 1050], "color": "#8b5e3c", "font_size": 24, "flags": {}},
    {"id": 6, "title": "07–09 — HUMAN APPROVAL → SEEDANCE → ASSEMBLY", "bounding": [3210, 470, 1400, 940], "color": "#6a506e", "font_size": 24, "flags": {}},
]


workflow = {
    "id": "ads-art-creative-intelligence-v2",
    "revision": 1,
    "last_node_id": max(node_by_id),
    "last_link_id": len(links),
    "nodes": nodes,
    "links": links,
    "groups": groups,
    "config": {},
    "extra": {"ds": {"scale": 0.72, "offset": [80, 80]}},
    "version": 0.4,
}

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Built {OUTPUT} ({len(nodes)} nodes, {len(links)} links)")
