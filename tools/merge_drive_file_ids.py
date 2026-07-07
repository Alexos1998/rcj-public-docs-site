#!/usr/bin/env python3
"""Merge Google Drive file IDs or CDN URLs into data/assets.json.

Input CSV columns:
  team_code,artifact,drive_file_id
or:
  team_code,artifact,preview_url,view_url,download_url,backend

For Google Drive, this script derives:
  https://drive.google.com/file/d/<FILE_ID>/preview
  https://drive.google.com/file/d/<FILE_ID>/view
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "data" / "assets.json"


def drive_urls(file_id: str) -> dict[str, str]:
    return {
        "backend": "google_drive",
        "drive_file_id": file_id,
        "preview_url": f"https://drive.google.com/file/d/{file_id}/preview",
        "view_url": f"https://drive.google.com/file/d/{file_id}/view",
        "download_url": f"https://drive.google.com/file/d/{file_id}/view",
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: tools/merge_drive_file_ids.py drive_file_map.csv", file=sys.stderr)
        return 2
    data = json.loads(ASSETS.read_text(encoding="utf-8"))
    assets = data["assets"]
    index = {(a["team_code"], a["artifact"]): a for a in assets}
    updated = 0
    with Path(sys.argv[1]).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["team_code"], row["artifact"])
            asset = index.get(key)
            if not asset:
                print(f"warning: no asset row for {key}", file=sys.stderr)
                continue
            if row.get("drive_file_id"):
                asset.update(drive_urls(row["drive_file_id"].strip()))
            else:
                asset["backend"] = row.get("backend") or "cdn"
                for field in ["preview_url", "view_url", "download_url"]:
                    if row.get(field):
                        asset[field] = row[field].strip()
            updated += 1
    ASSETS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"updated": updated, "assets": len(assets)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
