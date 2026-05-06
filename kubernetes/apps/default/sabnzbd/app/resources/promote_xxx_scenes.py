#!/usr/bin/env python3
"""Move completed xxx jobs into Stash scenes and trigger a targeted Stash scan."""

import errno
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path


CATEGORY = "xxx"
SAB_COMPLETE_ROOT = Path("/data/usenet/complete")
DESTINATION_ROOT = Path("/data/xxx/scenes")
STASH_SCENES_ROOT = "/library/scenes"
STASH_GRAPHQL_URL = os.environ.get(
    "STASH_GRAPHQL_URL",
    "http://stash.default.svc.cluster.local:9999/graphql",
)
STASH_API_KEY = os.environ.get("STASH_API_KEY")


def log(message: str) -> None:
    print(f"[promote_xxx_scenes] {message}", flush=True)


def parse_sab_context() -> tuple[Path, str, str]:
    if len(sys.argv) >= 8:
        source = Path(sys.argv[1])
        category = sys.argv[5]
        postproc_status = sys.argv[7]
        return source, category, postproc_status

    source_env = os.environ.get("SAB_COMPLETE_DIR")
    category = os.environ.get("SAB_CAT", "")
    postproc_status = os.environ.get("SAB_PP_STATUS", "")

    if not source_env:
        raise ValueError("Missing SAB post-processing path")

    return Path(source_env), category, postproc_status


def ensure_source_is_safe(source: Path) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"Source does not exist: {source}")

    resolved_source = source.resolve(strict=True)
    resolved_root = SAB_COMPLETE_ROOT.resolve(strict=False)

    if not resolved_source.is_relative_to(resolved_root):
        raise ValueError(f"Refusing to move path outside {resolved_root}: {resolved_source}")

    if resolved_source == resolved_root:
        raise ValueError(f"Refusing to move SAB complete root: {resolved_source}")

    return resolved_source


def destination_for(source: Path) -> Path:
    destination = DESTINATION_ROOT / source.name
    if destination.exists():
        raise FileExistsError(f"Destination already exists: {destination}")
    return destination


def move_path(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        source.rename(destination)
        return
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise

    temp_destination = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    if temp_destination.exists():
        raise FileExistsError(f"Temporary destination already exists: {temp_destination}")

    try:
        if source.is_dir():
            shutil.copytree(source, temp_destination, symlinks=True)
            temp_destination.rename(destination)
            shutil.rmtree(source)
        else:
            shutil.copy2(source, temp_destination)
            temp_destination.rename(destination)
            source.unlink()
    except Exception:
        if temp_destination.exists():
            if temp_destination.is_dir():
                shutil.rmtree(temp_destination)
            else:
                temp_destination.unlink()
        raise


def stash_path_for(destination: Path) -> str:
    return f"{STASH_SCENES_ROOT}/{destination.name}"


def trigger_stash_scan(stash_path: str) -> None:
    payload = {
        "query": """
            mutation MetadataScan($input: ScanMetadataInput!) {
              metadataScan(input: $input)
            }
        """,
        "variables": {
            "input": {
                "paths": [stash_path],
                "rescan": True,
                "scanGenerateCovers": True,
                "scanGeneratePreviews": True,
                "scanGenerateSprites": True,
                "scanGeneratePhashes": True,
            },
        },
    }

    headers = {"Content-Type": "application/json"}
    if STASH_API_KEY:
        headers["ApiKey"] = STASH_API_KEY

    request = urllib.request.Request(
        STASH_GRAPHQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Stash scan request failed with HTTP {error.code}: {body}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Stash scan request failed: {error}") from error

    parsed = json.loads(body)
    if parsed.get("errors"):
        raise RuntimeError(f"Stash scan returned errors: {parsed['errors']}")


def main() -> int:
    source, category, postproc_status = parse_sab_context()

    if category != CATEGORY:
        log(f"Skipping category {category!r}")
        return 0

    if postproc_status != "0":
        log(f"Skipping because SAB post-processing status is {postproc_status!r}")
        return 0

    source = ensure_source_is_safe(source)
    destination = destination_for(source)
    stash_path = stash_path_for(destination)

    log(f"Moving {source} to {destination}")
    move_path(source, destination)

    log(f"Triggering Stash scan for {stash_path}")
    trigger_stash_scan(stash_path)

    log("Done")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        log(f"ERROR: {error}")
        sys.exit(1)
