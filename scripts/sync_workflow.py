"""Safely refresh the installed Ads Art workflow from the versioned template.

Personal widget values on existing nodes (including identity notes and persisted
job identifiers) are retained by input name.  Newly versioned node definitions
and links are applied, while installed-only nodes are kept.  Every paid submit
and every remote Gemini confirmation is forced back to false.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = REPO_ROOT.parents[1]
DEFAULT_TEMPLATE = REPO_ROOT / "workflows" / "ads_art_prepare_v1.json"
DEFAULT_INSTALLED = (
    COMFY_ROOT / "user" / "default" / "workflows" / "Ads Art" / "ads_art_prepare_v1.json"
)
ACTIVE_PREFLIGHT_NODE_IDS = {1, 4, 5, 9, 23, 24, 25, 26}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _widget_values(node: dict[str, Any]) -> dict[str, Any]:
    names = [
        item.get("widget", {}).get("name", item.get("name"))
        for item in node.get("inputs", [])
        if item.get("widget")
    ]
    values = list(node.get("widgets_values", []))
    return {name: values[index] for index, name in enumerate(names) if index < len(values)}


def _merged_widgets(template_node: dict[str, Any], installed_node: dict[str, Any]) -> list[Any]:
    prior = _widget_values(installed_node)
    defaults = _widget_values(template_node)
    names = [
        item.get("widget", {}).get("name", item.get("name"))
        for item in template_node.get("inputs", [])
        if item.get("widget")
    ]
    return [prior.get(name, defaults.get(name)) for name in names]


def _set_widget(node: dict[str, Any], name: str, value: Any) -> None:
    names = [
        item.get("widget", {}).get("name", item.get("name"))
        for item in node.get("inputs", [])
        if item.get("widget")
    ]
    if name not in names:
        raise ValueError(f"Node {node.get('id')} has no widget {name!r}")
    node["widgets_values"][names.index(name)] = value


def _reset_extra_links(node: dict[str, Any]) -> None:
    for item in node.get("inputs", []):
        item["link"] = None
    for item in node.get("outputs", []):
        item["links"] = []


def _node(nodes: list[dict[str, Any]], node_id: int) -> dict[str, Any]:
    return next(item for item in nodes if int(item["id"]) == int(node_id))


def merge_workflow(
    template: dict[str, Any],
    installed: dict[str, Any],
    *,
    identity_image: str | None = None,
    positive_prompt: str | None = None,
    restrictive_prompt: str | None = None,
) -> dict[str, Any]:
    result = copy.deepcopy(template)
    previous = {int(item["id"]): item for item in installed.get("nodes", [])}
    template_ids = {int(item["id"]) for item in result["nodes"]}

    for node in result["nodes"]:
        old = previous.get(int(node["id"]))
        if old and old.get("type") == node.get("type"):
            node["widgets_values"] = _merged_widgets(node, old)
            for key in ("pos", "size", "title", "color", "bgcolor"):
                if key in old:
                    node[key] = copy.deepcopy(old[key])

    extras = []
    for old in installed.get("nodes", []):
        if int(old["id"]) not in template_ids:
            extra = copy.deepcopy(old)
            _reset_extra_links(extra)
            extra["mode"] = 2
            extras.append(extra)
    result["nodes"].extend(extras)

    for node in result["nodes"]:
        node["mode"] = 0 if int(node["id"]) in ACTIVE_PREFLIGHT_NODE_IDS else 2
        if node.get("type") == "AdsArtSubmitJob":
            _set_widget(node, "confirm_paid_submission", False)
        if node.get("type") == "AdsArtGeminiAnalyzeCommercial":
            _set_widget(node, "model", "gemini-3.6-flash")
            _set_widget(node, "confirm_gemini_analysis", False)
            _set_widget(node, "allow_retry_after_unknown", False)
            _set_widget(node, "max_shots", 3)
            _set_widget(node, "upload_retries", 1)
            if identity_image:
                _set_widget(node, "identity_approved", True)
        if int(node["id"]) == 9 and identity_image:
            _set_widget(node, "image", identity_image)
        if int(node["id"]) == 1 and positive_prompt is not None:
            _set_widget(node, "positive_prompt", positive_prompt)
        if int(node["id"]) == 1 and restrictive_prompt is not None:
            _set_widget(node, "restrictive_prompt", restrictive_prompt)

    next_link = int(result.get("last_link_id", 0))
    extra_ids = {int(item["id"]) for item in extras}
    for old_link in installed.get("links", []):
        _, source_id, source_slot, target_id, target_slot, link_type = old_link
        if int(source_id) not in extra_ids and int(target_id) not in extra_ids:
            continue
        if int(source_id) not in {int(item["id"]) for item in result["nodes"]}:
            continue
        if int(target_id) not in {int(item["id"]) for item in result["nodes"]}:
            continue
        next_link += 1
        link = [next_link, source_id, source_slot, target_id, target_slot, link_type]
        result["links"].append(link)
        source = _node(result["nodes"], source_id)
        target = _node(result["nodes"], target_id)
        source["outputs"][int(source_slot)].setdefault("links", []).append(next_link)
        target["inputs"][int(target_slot)]["link"] = next_link

    node_ids = {int(item["id"]) for item in result["nodes"]}
    for link in result["links"]:
        if int(link[1]) not in node_ids or int(link[3]) not in node_ids:
            raise ValueError(f"Dangling workflow link: {link}")
    result["last_node_id"] = max(node_ids)
    result["last_link_id"] = next_link
    result["revision"] = max(
        int(template.get("revision", 0)), int(installed.get("revision", 0))
    ) + 1
    result["groups"] = copy.deepcopy(installed.get("groups", result.get("groups", [])))
    result["extra"] = copy.deepcopy(installed.get("extra", result.get("extra", {})))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--installed", type=Path, default=DEFAULT_INSTALLED)
    parser.add_argument("--identity-image", default=None)
    parser.add_argument("--positive-prompt", default=None)
    parser.add_argument("--restrictive-prompt", default=None)
    args = parser.parse_args()

    template = _read(args.template.resolve())
    installed_path = args.installed.resolve()
    installed = _read(installed_path) if installed_path.is_file() else copy.deepcopy(template)
    merged = merge_workflow(
        template,
        installed,
        identity_image=args.identity_image,
        positive_prompt=args.positive_prompt,
        restrictive_prompt=args.restrictive_prompt,
    )
    installed_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = installed_path.with_suffix(installed_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(installed_path)
    print(f"Updated {installed_path}")
    print(f"revision={merged['revision']} nodes={len(merged['nodes'])} links={len(merged['links'])}")
    print("remote_gemini_confirmation=false paid_submissions=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
