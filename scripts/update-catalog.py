#!/usr/bin/env python3
"""Vendor or diff Cardigann YAML definitions from Prowlarr-indexers.

Usage:
    scripts/update-catalog.py sync    # download + overwrite vendored files
    scripts/update-catalog.py diff    # print per-file status, no writes

The canonical upstream is Prowlarr/Prowlarr-indexers @ master. Slug->path
mapping lives in backend/src/trove/indexers/catalog/registry.yaml.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import httpx
import yaml

REPO_ROOT = Path(__file__).parent.parent
CATALOG_DIR = REPO_ROOT / "backend" / "src" / "trove" / "indexers" / "catalog"
REGISTRY_PATH = CATALOG_DIR / "registry.yaml"
UPSTREAM_RAW = "https://raw.githubusercontent.com/Prowlarr/Indexers/master/"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_registry() -> list[dict[str, str]]:
    raw = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    entries = raw.get("entries") or []
    out: list[dict[str, str]] = []
    for row in entries:
        upstream = row.get("upstream_path")
        if not upstream:
            continue
        out.append(
            {
                "slug": row["slug"],
                "yaml_file": row["yaml_file"],
                "upstream_path": upstream,
            }
        )
    return out


def _fetch(client: httpx.Client, upstream_path: str) -> bytes | None:
    url = UPSTREAM_RAW + upstream_path
    resp = client.get(url, timeout=30.0)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.content


def run(mode: str) -> int:
    entries = _load_registry()
    with httpx.Client(follow_redirects=True) as client:
        changes = 0
        missing = 0
        for entry in entries:
            slug = entry["slug"]
            local_path = CATALOG_DIR / entry["yaml_file"]
            upstream_bytes = _fetch(client, entry["upstream_path"])
            if upstream_bytes is None:
                print(f"  [MISSING] {slug}: upstream {entry['upstream_path']} not found")
                missing += 1
                continue

            local_hash = _sha256(local_path.read_bytes()) if local_path.exists() else None
            upstream_hash = _sha256(upstream_bytes)

            if local_hash == upstream_hash:
                print(f"  [unchanged] {slug}")
                continue

            changes += 1
            if mode == "sync":
                local_path.write_bytes(upstream_bytes)
                state = "created" if local_hash is None else "updated"
                print(f"  [{state}] {slug}")
            else:
                state = "missing locally" if local_hash is None else "upstream changed"
                print(f"  [{state}] {slug}")

        print(f"\n{changes} change(s), {missing} missing upstream")
        return 1 if missing else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["sync", "diff"])
    args = parser.parse_args()
    return run(args.mode)


if __name__ == "__main__":
    sys.exit(main())
