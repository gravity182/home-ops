#!/usr/bin/env python3
"""Promote completed xxx jobs to Stash scenes."""

import json
import shutil
import sys
import urllib.request
from pathlib import Path


SOURCE_ROOT = Path("/data/usenet/complete/xxx")
DESTINATION_ROOT = Path("/data/xxx/scenes")
STASH_SCENES_ROOT = "/library/scenes"
STASH_GRAPHQL_URL = "http://stash.default.svc.cluster.local:9999/graphql"


def promote_scene(source: Path) -> Path:
    destination = DESTINATION_ROOT / source.name
    staging = DESTINATION_ROOT / f".{source.name}.partial"

    if destination.exists():
        raise FileExistsError(f"Destination already exists: {destination}")

    try:
        staging.mkdir()
    except FileExistsError as error:
        raise FileExistsError(f"Staging directory already exists: {staging}") from error

    try:
        shutil.copytree(source, staging, dirs_exist_ok=True, symlinks=True)
        staging.rename(destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    shutil.rmtree(source)
    return destination


def trigger_stash_scan(scene_name: str) -> None:
    stash_path = f"{STASH_SCENES_ROOT}/{scene_name}"
    payload = {
        "query": """
            mutation MetadataScan($input: ScanMetadataInput!) {
              metadataScan(input: $input)
            }
        """,
        "variables": {
            "input": {
                "paths": [stash_path],
                "scanGenerateCovers": True,
                "scanGeneratePreviews": True,
                "scanGenerateSprites": True,
                "scanGeneratePhashes": True,
            },
        },
    }

    request = urllib.request.Request(
        STASH_GRAPHQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)

    if errors := result.get("errors"):
        raise RuntimeError(f"Stash scan returned errors: {errors}")


def main() -> int:
    if len(sys.argv) != 9:
        raise ValueError(f"Expected 8 SAB arguments, received {len(sys.argv) - 1}")

    postproc_status = sys.argv[7]
    if postproc_status != "0":
        return 0

    source = Path(sys.argv[1]).resolve(strict=True)
    source_root = SOURCE_ROOT.resolve(strict=True)

    if not source.is_dir():
        raise ValueError(f"Source is not a directory: {source}")
    if source.parent != source_root:
        raise ValueError(f"Source must be a direct child of {source_root}: {source}")

    destination = promote_scene(source)

    try:
        trigger_stash_scan(destination.name)
    except Exception as error:
        print(f"Promoted; Stash scan failed: {error}", flush=True)
        return 0

    print("Promoted and scan queued", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
