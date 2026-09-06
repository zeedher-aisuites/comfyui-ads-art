"""Install Ads Art v2 without deleting or modifying the historical v1 workflow."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = REPO_ROOT.parents[1]
TEMPLATE = REPO_ROOT / "workflows" / "ads_art_creative_intelligence_v2.json"
INSTALLED = COMFY_ROOT / "user" / "default" / "workflows" / "Ads Art" / TEMPLATE.name
V1_INSTALLED = COMFY_ROOT / "user" / "default" / "workflows" / "Ads Art" / "ads_art_prepare_v1.json"


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def widget_map(node: dict[str, Any]) -> dict[str, Any]:
    names = [item["widget"]["name"] for item in node.get("inputs", []) if item.get("widget")]
    values = list(node.get("widgets_values", []))
    return {name: values[index] for index, name in enumerate(names) if index < len(values)}


def set_widget(node: dict[str, Any], name: str, value: Any) -> None:
    names = [item["widget"]["name"] for item in node.get("inputs", []) if item.get("widget")]
    if name not in names:
        raise ValueError(f"Node {node['id']} has no widget {name}")
    node["widgets_values"][names.index(name)] = value


def merge(template: dict[str, Any], installed: dict[str, Any] | None, v1: dict[str, Any] | None) -> dict[str, Any]:
    result = copy.deepcopy(template)
    if installed:
        prior = {int(node["id"]): node for node in installed.get("nodes", [])}
        for node in result["nodes"]:
            old = prior.get(int(node["id"]))
            if not old or old.get("type") != node.get("type"):
                continue
            prior_widgets = widget_map(old)
            names = [item["widget"]["name"] for item in node.get("inputs", []) if item.get("widget")]
            node["widgets_values"] = [prior_widgets.get(name, value) for name, value in zip(names, node["widgets_values"])]

    brief = next(node for node in result["nodes"] if node["type"] == "AdsArtCreativeBrief")
    identity = next(node for node in result["nodes"] if node["id"] == 2)
    if v1 and not installed:
        old_project = next((node for node in v1.get("nodes", []) if node.get("type") == "AdsArtProjectConfig"), None)
        old_identity_request = next((node for node in v1.get("nodes", []) if node.get("type") == "AdsArtPrepareIdentity"), None)
        old_approved_identity = next((node for node in v1.get("nodes", []) if node.get("id") == 9 and node.get("type") == "LoadImage"), None)
        if old_identity_request:
            notes = widget_map(old_identity_request).get("identity_notes", "")
            set_widget(brief, "identity_notes", notes)
        if old_approved_identity:
            image = widget_map(old_approved_identity).get("image")
            if image:
                set_widget(identity, "image", image)
        if old_project:
            controls = widget_map(old_project)
            if controls.get("project_id"):
                set_widget(brief, "project_id", controls["project_id"])
            historical = []
            for name in ("positive_prompt", "restrictive_prompt", "negative_prompt", "creative_prompt"):
                value = str(controls.get(name, "") or "").strip()
                if value:
                    historical.append(f"HISTORICAL V1 {name} (preserved; latest v2 product paradigm controls): {value}")
            if historical:
                current = str(widget_map(brief).get("user_constraints", "") or "").strip()
                set_widget(brief, "user_constraints", current + "\n\n" + "\n".join(historical))

    for node in result["nodes"]:
        if node.get("type") == "AdsArtGeminiCreativeIntelligence":
            set_widget(node, "model", "gemini-3.6-flash")
            set_widget(node, "reuse_matching_analysis", True)
            set_widget(node, "allow_retry_after_unknown", False)
            set_widget(node, "upload_retries", 1)
            set_widget(node, "identity_approved", True)
            node["mode"] = 0
        elif node.get("type") == "AdsArtSubmitJob":
            set_widget(node, "confirm_paid_submission", False)
            node["mode"] = 2
        elif node.get("type") == "AdsArtPrepareOriginalSeedanceShot":
            set_widget(node, "keyframe_approved", False)
            node["mode"] = 2
        elif node.get("type") in {"AdsArtAssembleClips"} or int(node["id"]) == 16:
            node["mode"] = 2
    result["revision"] = max(int(template.get("revision", 0)), int((installed or {}).get("revision", 0))) + 1
    return result


def main() -> int:
    template = read(TEMPLATE)
    installed = read(INSTALLED) if INSTALLED.is_file() else None
    v1 = read(V1_INSTALLED) if V1_INSTALLED.is_file() else None
    merged = merge(template, installed, v1)
    INSTALLED.parent.mkdir(parents=True, exist_ok=True)
    temporary = INSTALLED.with_suffix(INSTALLED.suffix + ".tmp")
    temporary.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(INSTALLED)
    print(f"Installed {INSTALLED}")
    print(f"revision={merged['revision']} nodes={len(merged['nodes'])} links={len(merged['links'])}")
    print("gemini=automatic cache-first; paid_submissions=false; seedance=false")
    print(f"v1_preserved={V1_INSTALLED.is_file()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
