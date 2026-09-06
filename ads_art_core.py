"""Core services for the Ads Art ComfyUI extension.

This module deliberately keeps generation preparation, submission, and polling
separate.  It only talks to Higgsfield through the locally installed official
CLI and never reads or prints authentication tokens.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


IMAGE_MODEL_ID = "nano_banana_pro"
IMAGE_ASPECT_RATIO = "4:5"
IMAGE_RESOLUTION = "2k"

VIDEO_MODEL_ID = "seedance_2_5"
VIDEO_MODE = "omni_reference"
VIDEO_ALLOWED_ROLES = frozenset({"image", "start_image", "end_image"})
VIDEO_PROHIBITED_ROLES = frozenset({"video", "audio"})
VIDEO_PROHIBITED_MODES = frozenset({"video_edit", "video_extension"})
VIDEO_ASPECT_RATIOS = ("auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
VIDEO_RESOLUTIONS = ("480p", "720p", "1080p")

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"})
AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg", ".opus"})
TERMINAL_JOB_STATES = frozenset({"completed", "failed", "canceled", "nsfw", "ip_detected"})

PACKAGE_ROOT = Path(__file__).resolve().parent
KNOWLEDGE_PATH = PACKAGE_ROOT / "knowledge" / "ads_art_camera_knowledge_v1.json"
CATALOG_SNAPSHOT_PATH = PACKAGE_ROOT / "knowledge" / "higgsfield_catalog_snapshot_v1.json"


class AdsArtError(RuntimeError):
    """User-facing validation or integration failure."""


class SubmissionUncertainError(AdsArtError):
    """The provider may have received a submission, so automatic retry is unsafe."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)


def parse_json(value: str | dict[str, Any], label: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except Exception as exc:
        raise AdsArtError(f"{label} no contiene JSON válido: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AdsArtError(f"{label} debe ser un objeto JSON.")
    return parsed


def load_knowledge() -> dict[str, Any]:
    try:
        data = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AdsArtError(
            f"Falta la base de conocimiento requerida: {KNOWLEDGE_PATH}"
        ) from exc
    if len(data.get("concepts", [])) != 31:
        raise AdsArtError("La base de conocimiento no contiene los 31 conceptos esperados.")
    return data


def load_catalog_snapshot() -> dict[str, Any]:
    try:
        return json.loads(CATALOG_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AdsArtError(f"Falta el snapshot de catálogo: {CATALOG_SNAPSHOT_PATH}") from exc


def _safe_project_id(value: str) -> str:
    value = (value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", value):
        raise AdsArtError(
            "project_id debe comenzar con letra o número y usar sólo letras, "
            "números, punto, guion o guion bajo (máximo 80 caracteres)."
        )
    return value


def _default_user_directory() -> Path:
    try:
        import folder_paths

        return Path(folder_paths.get_user_directory()).resolve()
    except Exception:
        # Tests can import the core without importing all of ComfyUI.
        return (PACKAGE_ROOT.parents[1] / "user").resolve()


def _default_output_directory() -> Path:
    try:
        import folder_paths

        return Path(folder_paths.get_output_directory()).resolve()
    except Exception:
        return (PACKAGE_ROOT.parents[1] / "output").resolve()


def resolve_input_path(value: str) -> Path:
    candidate = Path(os.path.expandvars((value or "").strip())).expanduser()
    if candidate.is_absolute() and candidate.is_file():
        return candidate.resolve()
    try:
        import folder_paths

        input_candidate = Path(folder_paths.get_input_directory()) / candidate
        if input_candidate.is_file():
            return input_candidate.resolve()
    except Exception:
        pass
    if candidate.is_file():
        return candidate.resolve()
    raise AdsArtError(f"No existe el archivo de entrada: {value}")


class ProjectStore:
    def __init__(self, project_id: str, user_directory: Path | None = None):
        self.project_id = _safe_project_id(project_id)
        base = (user_directory or _default_user_directory()).resolve()
        self.root = (base / "ads_art" / "projects" / self.project_id).resolve()
        allowed = (base / "ads_art" / "projects").resolve()
        if not self.root.is_relative_to(allowed):
            raise AdsArtError("La ruta del proyecto quedó fuera del directorio permitido.")
        self.root.mkdir(parents=True, exist_ok=True)

    def directory(self, *parts: str) -> Path:
        target = self.root.joinpath(*parts).resolve()
        if not target.is_relative_to(self.root):
            raise AdsArtError("Ruta de proyecto no permitida.")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def path(self, *parts: str) -> Path:
        target = self.root.joinpath(*parts).resolve()
        if not target.is_relative_to(self.root):
            raise AdsArtError("Ruta de proyecto no permitida.")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def write_json(self, relative_path: str, data: dict[str, Any]) -> Path:
        target = self.path(relative_path)
        payload = json_dumps(data) + "\n"
        fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return target

    def read_json(self, relative_path: str) -> dict[str, Any] | None:
        target = self.path(relative_path)
        if not target.is_file():
            return None
        return json.loads(target.read_text(encoding="utf-8"))


def save_image_tensor(image: Any, path: Path, index: int = 0) -> Path:
    import numpy as np
    from PIL import Image

    try:
        import torch

        is_tensor = isinstance(image, torch.Tensor)
    except Exception:
        is_tensor = False
    if is_tensor:
        if image.ndim == 4:
            array = image[min(max(index, 0), image.shape[0] - 1)].detach().cpu().numpy()
        else:
            array = image.detach().cpu().numpy()
    else:
        array = np.asarray(image)
        if array.ndim == 4:
            array = array[min(max(index, 0), array.shape[0] - 1)]
    if array.dtype != np.uint8:
        array = np.clip(array * 255.0, 0, 255).astype(np.uint8)
    if array.shape[-1] == 4:
        mode = "RGBA"
    else:
        mode = "RGB"
        array = array[..., :3]
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array, mode=mode).save(path, format="PNG")
    return path


def load_image_tensor(path: str | Path) -> Any:
    import numpy as np
    import torch
    from PIL import Image, ImageOps

    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        array = np.asarray(image).astype(np.float32) / 255.0
    return torch.from_numpy(array)[None, ...]


def image_ratio(image: Any) -> float:
    shape = tuple(image.shape)
    if len(shape) == 4:
        height, width = shape[1], shape[2]
    elif len(shape) == 3:
        height, width = shape[0], shape[1]
    else:
        raise AdsArtError("El tensor de imagen no tiene una forma compatible.")
    return float(width) / float(height)


def ratio_to_float(value: str) -> float | None:
    if value == "auto":
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)", value or "")
    if not match or float(match.group(2)) == 0:
        raise AdsArtError(f"Relación de aspecto no válida: {value}")
    return float(match.group(1)) / float(match.group(2))


_STOPWORDS = {
    "the", "and", "with", "from", "that", "this", "una", "uno", "unos", "unas",
    "los", "las", "del", "por", "para", "con", "que", "como", "sin", "debe", "deben",
    "keep", "preserve", "retain", "remove", "replace", "avoid", "conservar", "mantener",
    "preservar", "eliminar", "quitar", "sustituir", "reemplazar", "evitar", "generar",
}


def _normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value.lower()).strip()


def _targets(value: str) -> list[set[str]]:
    clauses = re.split(r"[\n;.!?]+", _normalize_text(value))
    result: list[set[str]] = []
    for clause in clauses:
        tokens = {
            token
            for token in re.findall(r"[a-z0-9_-]{3,}", clause)
            if token not in _STOPWORDS
        }
        if tokens:
            result.append(tokens)
    return result


def _overlap(a: set[str], b: set[str]) -> tuple[float, list[str]]:
    common = sorted(a & b)
    if not common:
        return 0.0, []
    return len(common) / max(1, min(len(a), len(b))), common


def detect_prompt_conflicts(
    positive_prompt: str,
    restrictive_prompt: str,
    negative_prompt: str,
    creative_prompt: str,
) -> list[dict[str, Any]]:
    fields = {
        "positive_prompt": _targets(positive_prompt),
        "restrictive_prompt": _targets(restrictive_prompt),
        "negative_prompt": _targets(negative_prompt),
        "creative_prompt": _targets(creative_prompt),
    }
    conflicts: list[dict[str, Any]] = []
    comparisons = [
        ("positive_prompt", "restrictive_prompt", "error", None),
        ("positive_prompt", "negative_prompt", "error", None),
        ("creative_prompt", "restrictive_prompt", "warning", "restrictive_prompt"),
        ("creative_prompt", "negative_prompt", "warning", "negative_prompt"),
    ]
    for left, right, severity, winner in comparisons:
        for a in fields[left]:
            for b in fields[right]:
                score, common = _overlap(a, b)
                if score < 0.6:
                    continue
                conflicts.append(
                    {
                        "id": f"{left}_vs_{right}_{len(conflicts) + 1}",
                        "severity": severity,
                        "fields": [left, right],
                        "overlap_terms": common,
                        "message_es": (
                            f"Posible contradicción entre {left} y {right}: "
                            f"{', '.join(common)}."
                        ),
                        "resolved_by_policy": winner,
                    }
                )
    return conflicts


def blocking_conflicts(conflicts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in conflicts if item.get("severity") == "error"]


def compile_controls(project: dict[str, Any], stage: str) -> str:
    controls = project.get("controls", {})
    sections: list[str] = []
    if stage in {"frame", "video"} and controls.get("positive_prompt", "").strip():
        sections.append(
            "REQUISITOS EXPLÍCITOS DE CONSERVACIÓN DEL USUARIO (máxima prioridad):\n"
            + controls["positive_prompt"].strip()
        )
    if stage in {"frame", "video"} and controls.get("restrictive_prompt", "").strip():
        sections.append(
            "ELIMINAR O SUSTITUIR OBLIGATORIAMENTE:\n"
            + controls["restrictive_prompt"].strip()
        )
    if controls.get("negative_prompt", "").strip():
        sections.append(
            "NO GENERAR (instrucción integrada en el prompt; no es un parámetro nativo):\n"
            + controls["negative_prompt"].strip()
        )
    if controls.get("creative_prompt", "").strip():
        sections.append(
            "DIRECCIÓN CREATIVA OPCIONAL, subordinada a las decisiones explícitas anteriores:\n"
            + controls["creative_prompt"].strip()
        )
    return "\n\n".join(sections)


def make_project(
    project_id: str,
    positive_prompt: str,
    restrictive_prompt: str,
    negative_prompt: str,
    creative_prompt: str,
    video_aspect_ratio: str = "auto",
    video_resolution: str = "1080p",
    seedance_generate_audio: bool = False,
) -> dict[str, Any]:
    project_id = _safe_project_id(project_id)
    if video_aspect_ratio not in VIDEO_ASPECT_RATIOS:
        raise AdsArtError(f"Formato de video no admitido por el snapshot: {video_aspect_ratio}")
    if video_resolution not in VIDEO_RESOLUTIONS:
        raise AdsArtError(f"Resolución de video no admitida: {video_resolution}")
    conflicts = detect_prompt_conflicts(
        positive_prompt, restrictive_prompt, negative_prompt, creative_prompt
    )
    project = {
        "schema_version": "1.0.0",
        "project_id": project_id,
        "created_or_updated_at": utc_now(),
        "controls": {
            "positive_prompt": positive_prompt.strip(),
            "restrictive_prompt": restrictive_prompt.strip(),
            "negative_prompt": negative_prompt.strip(),
            "creative_prompt": creative_prompt.strip(),
            "native_negative_prompt_assumed": False,
        },
        "models": {
            "image": {
                "id": IMAGE_MODEL_ID,
                "aspect_ratio": IMAGE_ASPECT_RATIO,
                "resolution": IMAGE_RESOLUTION,
            },
            "video": {
                "id": VIDEO_MODEL_ID,
                "mode": VIDEO_MODE,
                "aspect_ratio": video_aspect_ratio,
                "resolution": video_resolution,
                "generate_audio": bool(seedance_generate_audio),
                "aspect_is_independent_from_image": True,
            },
        },
        "audio_policy": {
            "montage_default": "original_commercial_audio",
            "forward_original_audio_to_seedance": False,
        },
        "conflicts": conflicts,
        "ready": not blocking_conflicts(conflicts),
        "knowledge_base": {
            "path": str(KNOWLEDGE_PATH),
            "concept_count": 31,
            "policy": "editorial_suggestions_only",
        },
    }
    store = ProjectStore(project_id)
    store.write_json("project.json", project)
    return project


def make_request(
    project: dict[str, Any],
    stage: str,
    shot_id: str,
    prompt: str,
    params: dict[str, Any],
    media: list[dict[str, Any]],
    approvals: dict[str, bool],
    extra_conflicts: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conflicts = list(project.get("conflicts", [])) + list(extra_conflicts or [])
    missing_approvals = sorted(name for name, approved in approvals.items() if not approved)
    for name in missing_approvals:
        conflicts.append(
            {
                "id": f"approval_{name}",
                "severity": "error",
                "message_es": f"Falta aprobación explícita: {name}.",
            }
        )
    request = {
        "schema_version": "1.0.0",
        "request_id": str(uuid.uuid4()),
        "project_id": project["project_id"],
        "stage": stage,
        "shot_id": shot_id,
        "created_at": utc_now(),
        "provider": "higgsfield",
        "transport": "official_higgsfield_cli",
        "model": params.get("model"),
        "prompt": re.sub(r"\s+", " ", prompt).strip(),
        "params": params,
        "media": media,
        "approvals": approvals,
        "conflicts": conflicts,
        "status": "blocked" if blocking_conflicts(conflicts) else "prepared",
        "metadata": metadata or {},
    }
    validate_generation_request(request, live_catalog=None, allow_blocked=True)
    store = ProjectStore(project["project_id"])
    relative = f"requests/{shot_id}/{request['request_id']}.json"
    request["record_path"] = str(store.path(relative))
    store.write_json(relative, request)
    return request


def _media_extension(item: dict[str, Any]) -> str:
    return Path(str(item.get("path", ""))).suffix.lower()


def validate_generation_request(
    request: dict[str, Any],
    live_catalog: dict[str, Any] | None = None,
    allow_blocked: bool = False,
) -> None:
    if request.get("status") == "blocked" and not allow_blocked:
        messages = [c.get("message_es", c.get("id", "conflicto")) for c in blocking_conflicts(request.get("conflicts", []))]
        raise AdsArtError("Solicitud bloqueada antes de generar:\n- " + "\n- ".join(messages))
    params = request.get("params", {})
    media = request.get("media", [])
    model = request.get("model") or params.get("model")
    if "negative_prompt" in params:
        raise AdsArtError("negative_prompt no se envía como parámetro nativo; debe compilarse en prompt.")
    if not request.get("prompt", "").strip():
        raise AdsArtError("La solicitud no tiene prompt.")

    if request.get("stage") in {"identity", "frame"}:
        if model != IMAGE_MODEL_ID or params.get("model") != IMAGE_MODEL_ID:
            raise AdsArtError(f"Ads Art requiere exactamente {IMAGE_MODEL_ID} para imágenes.")
        if params.get("aspect_ratio") != IMAGE_ASPECT_RATIO:
            raise AdsArtError(f"Ads Art requiere imágenes {IMAGE_ASPECT_RATIO}.")
        if str(params.get("resolution", "")).lower() != IMAGE_RESOLUTION:
            raise AdsArtError(f"Ads Art requiere imágenes a {IMAGE_RESOLUTION}.")
        if len(media) > 14:
            raise AdsArtError("Nano Banana Pro admite como máximo 14 referencias en el catálogo vigente.")
        for item in media:
            if item.get("role") != "image" or _media_extension(item) not in IMAGE_EXTENSIONS:
                raise AdsArtError("Nano Banana Pro sólo recibe referencias de imagen en Ads Art.")

    elif request.get("stage") == "video":
        if model != VIDEO_MODEL_ID or params.get("model") != VIDEO_MODEL_ID:
            raise AdsArtError(f"Ads Art requiere exactamente {VIDEO_MODEL_ID} para video.")
        mode = params.get("mode")
        if mode in VIDEO_PROHIBITED_MODES or mode != VIDEO_MODE:
            raise AdsArtError(
                "Seedance está limitado a omni_reference en Ads Art; "
                "video_edit y video_extension están prohibidos."
            )
        if params.get("aspect_ratio") == IMAGE_ASPECT_RATIO:
            raise AdsArtError("4:5 no figura como formato de Seedance 2.5; el formato de video es independiente.")
        if params.get("aspect_ratio") not in VIDEO_ASPECT_RATIOS:
            raise AdsArtError("Formato de Seedance no admitido por el catálogo verificado.")
        duration = int(params.get("duration", 0))
        if duration < 4 or duration > 30:
            raise AdsArtError("Seedance 2.5 requiere una duración generada entre 4 y 30 segundos.")
        if params.get("resolution") not in VIDEO_RESOLUTIONS:
            raise AdsArtError("Resolución de Seedance no admitida.")
        if not media:
            raise AdsArtError("omni_reference requiere al menos una imagen.")
        if len(media) > 30:
            raise AdsArtError("Seedance 2.5 admite como máximo 30 imágenes en este modo.")
        seen_start = 0
        seen_end = 0
        for item in media:
            role = item.get("role")
            ext = _media_extension(item)
            if role in VIDEO_PROHIBITED_ROLES or role not in VIDEO_ALLOWED_ROLES:
                raise AdsArtError(f"Rol de medio prohibido para Seedance: {role}")
            if ext in VIDEO_EXTENSIONS or ext in AUDIO_EXTENSIONS or ext not in IMAGE_EXTENSIONS:
                raise AdsArtError("Seedance sólo puede recibir archivos de imagen en Ads Art.")
            seen_start += int(role == "start_image")
            seen_end += int(role == "end_image")
        if seen_start > 1 or seen_end > 1:
            raise AdsArtError("Seedance sólo admite una start_image y una end_image.")
        if request.get("metadata", {}).get("original_video_forwarded"):
            raise AdsArtError("El video original nunca se reenvía a Seedance.")
        if request.get("metadata", {}).get("original_audio_forwarded"):
            raise AdsArtError("El audio original nunca se reenvía a Seedance.")
    else:
        raise AdsArtError(f"Etapa de solicitud desconocida: {request.get('stage')}")

    if live_catalog is not None:
        if live_catalog.get("job_type") != model:
            raise AdsArtError("El catálogo vigente devolvió un modelo distinto al solicitado.")
        declared = {item.get("name"): item for item in live_catalog.get("params", [])}
        for key, value in params.items():
            if key == "model":
                continue
            if key not in declared:
                raise AdsArtError(f"El catálogo vigente no declara el parámetro {key}.")
            options = declared[key].get("enum")
            if options and value not in options:
                raise AdsArtError(f"Valor no admitido para {key}: {value}")
        if request.get("stage") in {"identity", "frame"} and "image_references" not in declared:
            raise AdsArtError("El catálogo vigente ya no declara referencias de imagen.")
        if request.get("stage") == "video":
            role_param = {"image": "image_references", "start_image": "start_image", "end_image": "end_image"}
            for item in media:
                if role_param[item["role"]] not in declared:
                    raise AdsArtError(f"El catálogo vigente ya no admite el rol {item['role']}.")


@dataclass(frozen=True)
class CliCommand:
    prefix: tuple[str, ...]
    display_name: str


def find_higgsfield_cli() -> CliCommand:
    explicit = os.environ.get("HIGGSFIELD_CLI", "").strip()
    if explicit:
        resolved = shutil.which(explicit) or explicit
        if Path(resolved).exists():
            return CliCommand((str(Path(resolved).resolve()),), str(Path(resolved).resolve()))
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "node"
    node = local / "node.exe"
    script = local / "node_modules" / "@higgsfield" / "cli" / "bin" / "higgsfield.js"
    if node.is_file() and script.is_file():
        return CliCommand((str(node), str(script)), str(local / "higgsfield.cmd"))
    for name in ("higgsfield.exe", "higgsfield", "higgsfield.cmd"):
        resolved = shutil.which(name)
        if resolved:
            return CliCommand((resolved,), resolved)
    raise AdsArtError(
        "No se encontró el CLI oficial de Higgsfield. Instálalo/autentícalo o define HIGGSFIELD_CLI."
    )


def _parse_cli_json(stdout: str, stderr: str) -> Any:
    raw = (stdout or "").strip() or (stderr or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"(\{.*\}|\[.*\])", raw, re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
    return {"raw": raw[:4000]}


def run_cli(args: list[str], timeout: int = 120) -> tuple[Any, str]:
    cli = find_higgsfield_cli()
    command = [*cli.prefix, *[str(item) for item in args], "--json", "--no-color"]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5, int(timeout)),
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SubmissionUncertainError(
            "El CLI agotó el tiempo. Si era un envío, no lo repitas automáticamente: "
            "consulta los jobs recientes y recupera el job ID."
        ) from exc
    data = _parse_cli_json(proc.stdout, proc.stderr)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "error desconocido").strip()
        # Tokens are never requested, but redact bearer-like strings defensively.
        detail = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~-]+", r"\1[REDACTED]", detail)
        raise AdsArtError(f"Higgsfield CLI devolvió un error: {detail[:2000]}")
    return data, (proc.stdout or "").strip()


def cli_version() -> str:
    cli = find_higgsfield_cli()
    proc = subprocess.run(
        [*cli.prefix, "version", "--no-color"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        shell=False,
    )
    return (proc.stdout or proc.stderr).strip()


def get_live_model(model_id: str) -> dict[str, Any]:
    data, _ = run_cli(["model", "get", model_id], timeout=60)
    if not isinstance(data, dict) or data.get("job_type") != model_id:
        raise AdsArtError(f"No se pudo verificar {model_id} en el catálogo vigente.")
    return data


def get_account_status() -> dict[str, Any]:
    data, _ = run_cli(["account", "status"], timeout=60)
    if not isinstance(data, dict):
        raise AdsArtError("Respuesta de cuenta Higgsfield no reconocida.")
    # Do not expose/store account email from the status response.
    return {
        "connected": "credits" in data,
        "credits": data.get("credits"),
        "subscription_plan_type": data.get("subscription_plan_type"),
    }


def _extract_uuid(data: Any, stdout: str = "") -> str | None:
    candidates: list[str] = []
    if isinstance(data, str):
        candidates.append(data)
    elif isinstance(data, list):
        candidates.extend(item for item in data if isinstance(item, str))
    elif isinstance(data, dict):
        for key in ("id", "job_id", "media_id", "upload_id"):
            if isinstance(data.get(key), str):
                candidates.append(data[key])
        if isinstance(data.get("result"), dict):
            nested = _extract_uuid(data["result"], "")
            if nested:
                return nested
    candidates.extend(re.findall(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", stdout or ""))
    for candidate in candidates:
        value = candidate.strip()
        if re.fullmatch(r"[0-9a-fA-F-]{36}", value):
            return value
    return None


def _collect_result_urls(value: Any) -> list[str]:
    """Collect generated outputs without accidentally returning reference URLs."""
    urls: list[str] = []
    direct_keys = (
        "result_url",
        "output_url",
        "media_url",
        "rawUrl",
        "minUrl",
        "raw_url",
        "min_url",
    )

    def add(candidate: Any) -> None:
        if (
            isinstance(candidate, str)
            and candidate.startswith(("https://", "http://"))
            and candidate not in urls
        ):
            urls.append(candidate)

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key in direct_keys:
                add(item.get(key))
            # Do not traverse params/medias: those contain uploaded references.
            for key in ("results", "result", "output", "outputs", "artifacts"):
                if key in item:
                    visit(item[key])
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return urls


def _retry(operation, attempts: int, label: str):
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return operation()
        except SubmissionUncertainError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt >= max(1, attempts):
                break
            time.sleep(min(2 ** (attempt - 1), 4))
    raise AdsArtError(f"{label} falló tras {max(1, attempts)} intentos: {last_error}")


def upload_image(path: str, attempts: int = 2, timeout: int = 180) -> dict[str, Any]:
    source = Path(path).resolve()
    if not source.is_file() or source.suffix.lower() not in IMAGE_EXTENSIONS:
        raise AdsArtError(f"Referencia de imagen inválida: {source}")

    def operation():
        data, stdout = run_cli(["upload", "create", str(source)], timeout=timeout)
        media_id = _extract_uuid(data, stdout)
        if not media_id:
            raise AdsArtError("Higgsfield no devolvió un media/upload ID.")
        return {"media_id": media_id, "source_path": str(source)}

    return _retry(operation, attempts, f"Upload de {source.name}")


def _media_args(uploaded: list[dict[str, Any]]) -> list[str]:
    flag = {
        "image": "--image-references",
        "start_image": "--start-image",
        "end_image": "--end-image",
    }
    args: list[str] = []
    for item in uploaded:
        role = item["role"]
        if role not in flag:
            raise AdsArtError(f"Rol de referencia no transportable: {role}")
        args.extend([flag[role], item["media_id"]])
    return args


def _parameter_args(request: dict[str, Any]) -> list[str]:
    params = request["params"]
    ordered = [
        "mode", "aspect_ratio", "resolution", "duration", "generate_audio", "bitrate_mode"
    ]
    args: list[str] = []
    for key in ordered:
        if key not in params:
            continue
        value = params[key]
        if isinstance(value, bool):
            value = "true" if value else "false"
        args.extend([f"--{key}", str(value)])
    args.extend(["--prompt", request["prompt"]])
    return args


def _extract_cost(data: Any) -> float | None:
    if isinstance(data, dict):
        for key in ("credits_exact", "credits", "cost", "estimated_cost", "total_credits"):
            value = data.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        for value in data.values():
            found = _extract_cost(value)
            if found is not None:
                return found
    if isinstance(data, list):
        for value in data:
            found = _extract_cost(value)
            if found is not None:
                return found
    return None


def submit_request(
    request_value: str | dict[str, Any],
    confirm_submission: bool,
    minimum_credits_after: float = 0,
    upload_retries: int = 2,
    timeout: int = 180,
) -> dict[str, Any]:
    request = parse_json(request_value, "request")
    validate_generation_request(request, live_catalog=None, allow_blocked=False)
    store = ProjectStore(request["project_id"])
    job_path = f"jobs/{request['request_id']}.json"
    existing = store.read_json(job_path)
    if existing and existing.get("job_id"):
        existing["deduplicated"] = True
        return existing
    if existing and existing.get("status") in {"submission_started", "submission_unknown"}:
        raise SubmissionUncertainError(
            "Esta request ya tiene un envío iniciado o incierto. No se volverá a enviar. "
            "Recupere el job ID con `higgsfield generate list` y consúltelo con Ads Art — Poll Job."
        )
    if not confirm_submission:
        job = {
            "schema_version": "1.0.0",
            "project_id": request["project_id"],
            "request_id": request["request_id"],
            "shot_id": request["shot_id"],
            "stage": request["stage"],
            "status": "prepared_not_submitted",
            "job_id": None,
            "paid_generation_submitted": False,
            "request_record_path": request.get("record_path"),
            "updated_at": utc_now(),
        }
        store.write_json(job_path, job)
        return job

    live_catalog = get_live_model(request["model"])
    validate_generation_request(request, live_catalog=live_catalog, allow_blocked=False)
    account = get_account_status()
    uploaded: list[dict[str, Any]] = []
    for item in request["media"]:
        record = upload_image(item["path"], attempts=upload_retries, timeout=timeout)
        record.update({"role": item["role"], "kind": item.get("kind")})
        uploaded.append(record)

    media_args = _media_args(uploaded)
    common_args = [request["model"], *media_args, *_parameter_args(request)]
    cost_data, _ = run_cli(["generate", "cost", *common_args], timeout=timeout)
    estimated_cost = _extract_cost(cost_data)
    credits = account.get("credits")
    if estimated_cost is None:
        raise AdsArtError("No se pudo estimar el coste; el envío queda bloqueado.")
    if isinstance(credits, (int, float)) and float(credits) - estimated_cost < float(minimum_credits_after):
        raise AdsArtError(
            f"Envío bloqueado por reserva de créditos: saldo={credits}, "
            f"coste estimado={estimated_cost}, reserva={minimum_credits_after}."
        )

    marker = {
        "schema_version": "1.0.0",
        "project_id": request["project_id"],
        "request_id": request["request_id"],
        "shot_id": request["shot_id"],
        "stage": request["stage"],
        "status": "submission_started",
        "job_id": None,
        "uploaded_media": uploaded,
        "estimated_cost": estimated_cost,
        "paid_generation_submitted": "unknown",
        "updated_at": utc_now(),
    }
    store.write_json(job_path, marker)
    try:
        # Exactly one create attempt. An uncertain response must be recovered, not retried.
        data, stdout = run_cli(["generate", "create", *common_args], timeout=timeout)
    except Exception as exc:
        marker["status"] = "submission_unknown"
        marker["error"] = str(exc)
        marker["updated_at"] = utc_now()
        store.write_json(job_path, marker)
        raise SubmissionUncertainError(
            "No se puede confirmar si Higgsfield recibió el job. No se reintentó. "
            "Consulta `higgsfield generate list`, recupera el ID y úsalo en Ads Art — Poll Job."
        ) from exc
    job_id = _extract_uuid(data, stdout)
    if not job_id:
        marker["status"] = "submission_unknown"
        marker["provider_response_summary"] = {
            "status": data.get("status") if isinstance(data, dict) else None,
        }
        marker["updated_at"] = utc_now()
        store.write_json(job_path, marker)
        raise SubmissionUncertainError(
            "Higgsfield respondió sin un job ID reconocible. No se reintentó para evitar duplicados."
        )
    job = {
        **marker,
        "status": "submitted",
        "job_id": job_id,
        "paid_generation_submitted": True,
        "provider_status": data.get("status") if isinstance(data, dict) else None,
        "updated_at": utc_now(),
    }
    store.write_json(job_path, job)
    return job


def _download(url: str, target: Path, attempts: int = 2) -> Path:
    def operation():
        request = urllib.request.Request(url, headers={"User-Agent": "AdsArt-ComfyUI/1.0"})
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = response.read()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return target

    return _retry(operation, attempts, f"Descarga de {target.name}")


def poll_job(
    job_value: str | dict[str, Any],
    job_id_override: str = "",
    download_completed: bool = True,
    query_retries: int = 2,
) -> dict[str, Any]:
    job = parse_json(job_value, "job")
    job_id = (job_id_override or job.get("job_id") or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", job_id):
        raise AdsArtError("Falta un job ID UUID válido para consultar.")

    def operation():
        return run_cli(["generate", "get", job_id], timeout=60)[0]

    data = _retry(operation, query_retries, "Consulta de job")
    if not isinstance(data, dict):
        raise AdsArtError("Respuesta de job no reconocida.")
    status = str(data.get("status") or data.get("state") or "unknown").lower()
    urls = _collect_result_urls(data)
    job.update(
        {
            "job_id": job_id,
            "status": status,
            "provider_status": status,
            "result_urls": urls,
            "updated_at": utc_now(),
        }
    )
    if status == "completed" and download_completed and urls:
        store = ProjectStore(job["project_id"])
        extension = ".mp4" if job.get("stage") == "video" else ".png"
        result_paths: list[str] = []
        for index, url in enumerate(urls, 1):
            target = store.path("results", job.get("shot_id", "result"), f"{job_id}_{index}{extension}")
            _download(url, target, attempts=2)
            result_paths.append(str(target))
        job["result_paths"] = result_paths
    store = ProjectStore(job["project_id"])
    store.write_json(f"jobs/{job.get('request_id', job_id)}.json", job)
    return job


def recover_job_record(
    project_value: str | dict[str, Any],
    request_id: str = "",
    job_id: str = "",
    shot_id: str = "identity",
    stage: str = "identity",
) -> dict[str, Any]:
    """Load a persisted job or create a local recovery record for a known job ID.

    This function is local-only. It never submits or queries a provider job.
    """
    project = parse_json(project_value, "project")
    store = ProjectStore(project["project_id"])
    request_id = (request_id or "").strip()
    job_id = (job_id or "").strip()
    if request_id:
        try:
            uuid.UUID(request_id)
        except ValueError as exc:
            raise AdsArtError("request_id debe ser un UUID válido.") from exc
        existing = store.read_json(f"jobs/{request_id}.json")
        if not existing:
            raise AdsArtError(
                f"No existe un registro local para request_id={request_id}. "
                "Use el job_id conocido para crear un registro de recuperación."
            )
        existing_job_id = str(existing.get("job_id") or "").strip()
        if job_id and existing_job_id and job_id != existing_job_id:
            raise AdsArtError("El job_id indicado no coincide con el registro local.")
        if job_id and not existing_job_id:
            existing["job_id"] = job_id
            existing["status"] = "recovered_with_manual_job_id"
            existing["updated_at"] = utc_now()
            store.write_json(f"jobs/{request_id}.json", existing)
        if not existing.get("job_id"):
            raise AdsArtError(
                "El registro existe pero no contiene job_id. Recupérelo con "
                "`higgsfield generate list` y escríbalo en este nodo."
            )
        return existing

    if not job_id:
        raise AdsArtError("Indique request_id o job_id para recuperar un trabajo.")
    try:
        uuid.UUID(job_id)
    except ValueError as exc:
        raise AdsArtError("job_id debe ser un UUID válido.") from exc
    if stage not in {"identity", "frame", "video"}:
        raise AdsArtError("stage debe ser identity, frame o video.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", shot_id or ""):
        raise AdsArtError("shot_id no es válido.")
    recovery_key = f"recovered_{job_id}"
    recovered = {
        "schema_version": "1.0.0",
        "project_id": project["project_id"],
        "request_id": recovery_key,
        "shot_id": shot_id,
        "stage": stage,
        "status": "recovered_from_manual_job_id",
        "job_id": job_id,
        "paid_generation_submitted": "unknown_external_history",
        "recovered_at": utc_now(),
        "updated_at": utc_now(),
    }
    store.write_json(f"jobs/{recovery_key}.json", recovered)
    return recovered
