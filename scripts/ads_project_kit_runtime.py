"""Runtime preflight, loading, creation, and validation via ads-project-kit.

This module bridges Analog Design Bench tasks and the ADS Python Runtime
without duplicating keysight.ads.de project-creation logic or hardcoding host
paths. Non-ADS tasks do not import or require this module.
"""

from __future__ import annotations

from dataclasses import asdict
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Iterable
import warnings

ADS_PROJECT_KIT_REPO = "https://github.com/why250/ads-project-kit"
ADS_PROJECT_KIT_PINNED_COMMIT = "00ae027d578336c7b70f8d76ab553ecc257b3b67"
ADS_PROJECT_KIT_MIN_VERSION = "0.1.0"
ADS_PROJECT_KIT_ENV_VAR = "ADS_PROJECT_KIT_PATH"


class AdsProjectKitError(RuntimeError):
    """Raised when ads-project-kit cannot be loaded or runtime preflight fails."""


def _remediation_hint() -> str:
    return (
        f"Install ads-project-kit>={ADS_PROJECT_KIT_MIN_VERSION} (pinned commit "
        f"{ADS_PROJECT_KIT_PINNED_COMMIT} from {ADS_PROJECT_KIT_REPO}) into the target "
        f"ADS Python environment, or deploy its source on the ADS host and pass "
        f"src_path / set {ADS_PROJECT_KIT_ENV_VAR}."
    )


def _is_link(path: Path) -> bool:
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        return True
    try:
        attrs = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    except FileNotFoundError:
        return False


def _same_path(first: str | os.PathLike[str], second: str | os.PathLike[str]) -> bool:
    first_path = Path(first)
    second_path = Path(second)
    try:
        if os.path.lexists(first_path) and os.path.lexists(second_path):
            return os.path.samefile(first_path, second_path)
    except OSError:
        pass
    return os.path.normcase(os.path.abspath(os.path.realpath(first_path))) == os.path.normcase(
        os.path.abspath(os.path.realpath(second_path))
    )


def _resolve_src_dir(candidate: str | os.PathLike[str]) -> Path:
    raw = Path(candidate).expanduser()
    if not raw.exists():
        raise AdsProjectKitError(
            f"Configured ads-project-kit path does not exist on this host: {raw}. {_remediation_hint()}"
        )
    if (raw / "ads_project_kit" / "__init__.py").is_file():
        return raw.resolve()
    if (raw / "src" / "ads_project_kit" / "__init__.py").is_file():
        return (raw / "src").resolve()
    raise AdsProjectKitError(
        f"Path does not contain an ads_project_kit package: {raw}. {_remediation_hint()}"
    )


def _package_version(module: Any) -> str:
    version = getattr(module, "__version__", None)
    if isinstance(version, str) and version.strip():
        return version.strip()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            found = importlib.metadata.version("ads-project-kit")
            if found:
                return found
        except importlib.metadata.PackageNotFoundError:
            pass
    return "unknown"


def _parse_version(raw: str) -> tuple[int, ...] | None:
    parts: list[int] = []
    for token in raw.strip().split("."):
        digits = ""
        for ch in token:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            return None
        parts.append(int(digits))
    return tuple(parts) if parts else None


def _deployed_commit(package_file: Path | None) -> str | None:
    if package_file is None:
        return None
    for parent in package_file.resolve().parents[:4]:
        marker = parent / "ads-project-kit-commit.txt"
        if marker.is_file():
            text = marker.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                return text
        head = parent / ".git" / "HEAD"
        if not head.is_file():
            continue
        head_text = head.read_text(encoding="utf-8", errors="replace").strip()
        if head_text.startswith("ref: "):
            ref_path = parent / ".git" / head_text[5:].strip()
            if ref_path.is_file():
                return ref_path.read_text(encoding="utf-8", errors="replace").strip()
        elif head_text:
            return head_text
    return None


def load_ads_project_kit(
    *,
    src_path: str | os.PathLike[str] | None = None,
    require_apis: tuple[str, ...] = ("create_project", "validate_project"),
) -> tuple[Any, dict[str, Any]]:
    """Load ads_project_kit from an explicit source path, env var, or Python environment.

    Never falls back to an alternative ADS project-creation implementation.
    """
    load_mode = "installed_environment"
    resolved_src: Path | None = None
    env_override = os.environ.get(ADS_PROJECT_KIT_ENV_VAR, "").strip()
    if src_path is not None:
        resolved_src = _resolve_src_dir(src_path)
        load_mode = "explicit_src_path"
    elif env_override:
        resolved_src = _resolve_src_dir(env_override)
        load_mode = f"env:{ADS_PROJECT_KIT_ENV_VAR}"

    if resolved_src is not None:
        src_str = str(resolved_src)
        if src_str not in sys.path:
            sys.path.insert(0, src_str)

    try:
        module = importlib.import_module("ads_project_kit")
    except Exception as exc:
        raise AdsProjectKitError(
            f"Unable to import ads_project_kit ({type(exc).__name__}: {exc}). {_remediation_hint()}"
        ) from exc

    pkg_file_raw = getattr(module, "__file__", None)
    pkg_file = Path(pkg_file_raw).resolve() if pkg_file_raw else None
    if resolved_src is not None and pkg_file is not None:
        expected_pkg_dir = (resolved_src / "ads_project_kit").resolve()
        if not _same_path(pkg_file.parent, expected_pkg_dir):
            raise AdsProjectKitError(
                f"ads_project_kit was already loaded from {pkg_file.parent}, not requested {expected_pkg_dir}."
            )

    missing = [api for api in require_apis if not callable(getattr(module, api, None))]
    if missing:
        raise AdsProjectKitError(
            f"Loaded ads_project_kit is missing required APIs {missing}. {_remediation_hint()}"
        )

    pkg_info_fn = getattr(module, "package_info", None)
    pkg_info: dict[str, Any] = {}
    if callable(pkg_info_fn):
        try:
            candidate = pkg_info_fn()
            if isinstance(candidate, dict):
                pkg_info = candidate
        except Exception:
            pkg_info = {}

    version = str(pkg_info.get("version") or "").strip() or _package_version(module)
    parsed = _parse_version(version)
    min_parsed = _parse_version(ADS_PROJECT_KIT_MIN_VERSION)
    if parsed is not None and min_parsed is not None and parsed < min_parsed:
        raise AdsProjectKitError(
            f"Loaded ads_project_kit version {version} is older than required "
            f"{ADS_PROJECT_KIT_MIN_VERSION}. {_remediation_hint()}"
        )

    deployed_commit = pkg_info.get("commit") or _deployed_commit(pkg_file)
    info = {
        "repo": ADS_PROJECT_KIT_REPO,
        "pinned_commit": ADS_PROJECT_KIT_PINNED_COMMIT,
        "min_version": ADS_PROJECT_KIT_MIN_VERSION,
        "load_mode": load_mode,
        "package_path": str(pkg_file) if pkg_file is not None else pkg_info.get("package_path"),
        "package_version": version,
        "deployed_commit": deployed_commit,
        "source_kind": pkg_info.get("source_kind"),
    }
    return module, info


def _check_parent_writable(parent: Path) -> tuple[bool, str]:
    probe = parent / f".apk_preflight_{os.getpid()}.tmp"
    try:
        with probe.open("x", encoding="utf-8") as handle:
            handle.write("probe\n")
        probe.unlink()
        return True, f"Parent directory is writable: {parent}"
    except OSError as exc:
        try:
            if probe.exists():
                probe.unlink()
        except OSError:
            pass
        return False, f"Parent directory is not writable ({parent}): {type(exc).__name__}: {exc}"


def preflight_ads_runtime(
    workspace_path: str | os.PathLike[str] | None = None,
    *,
    allow_existing: bool = False,
    require_ads: bool = True,
    src_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Verify ADS Python Runtime, ads_project_kit availability, and workspace state."""
    errors: list[str] = []
    warnings: list[str] = []

    kit_info: dict[str, Any] = {"status": "FAIL"}
    kit_module = None
    try:
        kit_module, loaded = load_ads_project_kit(src_path=src_path)
        kit_info = {"status": "PASS", **loaded}
    except AdsProjectKitError as exc:
        kit_info = {"status": "FAIL", "error": str(exc)}
        errors.append(str(exc))

    ads_info: dict[str, Any] = {
        "status": "NOT RUN",
        "python_executable": sys.executable,
        "python_version": sys.version,
    }
    de = None
    try:
        from keysight.ads import de as ads_de  # type: ignore[import-not-found]

        de = ads_de
    except ImportError as exc:
        msg = (
            f"keysight.ads.de is unavailable ({exc}); run inside the target ADS Python "
            "Runtime (ADS MCP session or HPEESOF_DIR/tools/python)."
        )
        ads_info["detail"] = msg
        if require_ads:
            ads_info["status"] = "FAIL"
            errors.append(msg)
        else:
            ads_info["status"] = "NOT RUN"
            warnings.append(msg)
    else:
        workspace_open = bool(de.workspace_is_open())
        active_path = None
        if workspace_open:
            try:
                active = de.active_workspace()
                raw_active = getattr(active, "path", None)
                active_path = str(raw_active) if raw_active is not None else None
            except Exception as exc:
                warnings.append(f"Unable to inspect active ADS workspace: {type(exc).__name__}: {exc}")
        ads_info.update(
            {
                "status": "PASS",
                "ads_version": de.version() if hasattr(de, "version") else None,
                "ads_product_version": de.product_version().strip() if hasattr(de, "product_version") else None,
                "hpeesof_path": str(de.hpeesof_path()) if hasattr(de, "hpeesof_path") else None,
                "is_pde_app": bool(de.is_pde_app()) if hasattr(de, "is_pde_app") else None,
                "running_automation": bool(de.running_automation()) if hasattr(de, "running_automation") else None,
                "workspace_is_open": workspace_open,
                "active_workspace_path": active_path,
            }
        )

    ws_info: dict[str, Any] = {"status": "NOT RUN"}
    if workspace_path is not None:
        root = Path(workspace_path).absolute()
        ws_info = {
            "status": "PASS",
            "path": str(root),
            "allow_existing": allow_existing,
            "exists": os.path.lexists(root),
        }
        if kit_module is not None:
            from ads_project_kit.naming import is_valid_workspace_name

            if not is_valid_workspace_name(root.name):
                msg = f"Target workspace directory must follow <identifier>_wrk convention: {root.name!r}"
                ws_info["status"] = "FAIL"
                errors.append(msg)
        elif not root.name.endswith("_wrk"):
            msg = f"Target workspace directory must end with '_wrk': {root.name!r}"
            ws_info["status"] = "FAIL"
            errors.append(msg)

        if _is_link(root):
            msg = f"Target workspace path cannot be a symlink or junction: {root}"
            ws_info["status"] = "FAIL"
            errors.append(msg)

        if not allow_existing:
            if os.path.lexists(root):
                msg = f"Target ADS workspace already exists (refusing to overwrite): {root}"
                ws_info["status"] = "FAIL"
                errors.append(msg)
            elif not root.parent.is_dir():
                msg = f"Parent directory does not exist on the ADS host: {root.parent}"
                ws_info["status"] = "FAIL"
                errors.append(msg)
            else:
                writable, detail = _check_parent_writable(root.parent)
                ws_info["parent_writable"] = writable
                ws_info["parent_detail"] = detail
                if not writable:
                    ws_info["status"] = "FAIL"
                    errors.append(detail)
            if de is not None and ads_info.get("workspace_is_open"):
                active_desc = ads_info.get("active_workspace_path") or "unknown"
                msg = (
                    f"An ADS workspace is already open ({active_desc}); refusing to close or "
                    "replace it before creating a new project."
                )
                ws_info["status"] = "FAIL"
                errors.append(msg)
        else:
            if not root.is_dir():
                msg = f"Target ADS workspace directory does not exist: {root}"
                ws_info["status"] = "FAIL"
                errors.append(msg)
            elif de is not None and ads_info.get("workspace_is_open"):
                active_path = ads_info.get("active_workspace_path")
                if active_path and _same_path(active_path, root):
                    ws_info["active_match"] = "same_workspace"
                else:
                    ws_info["active_match"] = "different_workspace"
                    warnings.append(
                        f"A different ADS workspace is open ({active_path or 'unknown'}); "
                        "native checks will report NOT RUN without closing it."
                    )

    if errors:
        overall = "FAIL"
    elif ads_info["status"] == "NOT RUN":
        overall = "NOT RUN"
    else:
        overall = "PASS"

    return {
        "schema_version": 1,
        "status": overall,
        "ads_project_kit": kit_info,
        "ads_runtime": ads_info,
        "target_workspace": ws_info,
        "errors": errors,
        "warnings": warnings,
    }


def _serialize_check(check: Any) -> dict[str, str]:
    if isinstance(check, dict):
        return {
            "name": str(check["name"]),
            "status": str(check["status"]),
            "detail": str(check["detail"]),
        }
    return {str(k): str(v) for k, v in asdict(check).items()}


def format_validation_report(report: Any, *, native_requested: bool = True) -> dict[str, Any]:
    """Normalize an ads_project_kit.ValidationReport with strict PASS/FAIL/NOT RUN semantics."""
    static = [_serialize_check(item) for item in report.static]
    native = [_serialize_check(item) for item in report.native]

    static_has_fail = (not static) or any(item["status"] == "FAIL" for item in static)
    static_has_not_run = any(item["status"] == "NOT RUN" for item in static)
    static_passed = bool(static) and all(item["status"] == "PASS" for item in static)

    native_has_fail = any(item["status"] == "FAIL" for item in native)
    native_has_not_run = (not native) or any(item["status"] == "NOT RUN" for item in native)
    native_validated = bool(
        native_requested and native and static_passed and not native_has_fail and not native_has_not_run
    )

    if static_has_fail or native_has_fail:
        overall = "FAIL"
    elif static_has_not_run or native_has_not_run:
        overall = "NOT RUN"
    else:
        overall = "PASS"

    return {
        "path": str(report.path),
        "overall_status": overall,
        "static_passed": static_passed,
        "native_validated": native_validated,
        "static": static,
        "native": native,
    }


def validate_ads_project(
    workspace_path: str | os.PathLike[str],
    *,
    native: bool = True,
    src_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run ads_project_kit.validate_project() and preserve PASS/FAIL/NOT RUN status."""
    kit, info = load_ads_project_kit(src_path=src_path)
    report = kit.validate_project(Path(workspace_path), native=native)
    formatted = format_validation_report(report, native_requested=native)
    formatted["ads_project_kit"] = info
    return formatted


def create_ads_project(
    workspace_path: str | os.PathLike[str],
    name: str,
    libraries: Iterable[str] = (),
    *,
    setup_schematic_tech: bool = True,
    src_path: str | os.PathLike[str] | None = None,
    validate_native: bool = True,
) -> dict[str, Any]:
    """Preflight, create a native ADS project via ads_project_kit, and validate it."""
    preflight = preflight_ads_runtime(
        workspace_path,
        allow_existing=False,
        require_ads=True,
        src_path=src_path,
    )
    if preflight["status"] != "PASS":
        raise AdsProjectKitError(
            "ADS Project Kit preflight failed: " + "; ".join(preflight["errors"])
        )

    kit, info = load_ads_project_kit(src_path=src_path)
    project = kit.create_project(
        path=Path(workspace_path),
        name=name,
        libraries=tuple(libraries),
        setup_schematic_tech=setup_schematic_tech,
    )
    validation = validate_ads_project(
        project.path,
        native=validate_native,
        src_path=src_path,
    )
    if validation["overall_status"] == "FAIL":
        raise AdsProjectKitError(
            "ADS Project Kit validation failed after create_project(): "
            + json.dumps(validation, ensure_ascii=False)
        )
    if validate_native and not validation["native_validated"]:
        raise AdsProjectKitError(
            "Native ADS validation did not complete after create_project(): "
            + json.dumps(validation, ensure_ascii=False)
        )

    return {
        "status": validation["overall_status"],
        "project": {
            "path": str(project.path),
            "name": project.name,
            "libraries": list(project.libraries),
        },
        "ads_project_kit": info,
        "preflight": preflight,
        "validation": validation,
    }
