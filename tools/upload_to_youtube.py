#!/usr/bin/env python3
"""Upload consented team videos to YouTube and log the resulting video IDs.

Prerequisites (not installed by default):
  pip install google-api-python-client google-auth-oauthlib google-auth

Getting an OAuth client (one-time, done by whoever owns the target YouTube channel/account):
  1. https://console.cloud.google.com/ -> create/select a project.
  2. APIs & Services -> Enable APIs -> enable "YouTube Data API v3".
  3. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID -> Application
     type "Desktop app". Download the JSON as client_secret.json.
  4. APIs & Services -> OAuth consent screen -> add the uploading Google account as a Test User
     (unless the app is published/verified).
  5. Quota: a fresh Cloud project defaults to 10,000 units/day; videos.insert costs 1,600
     units, so ~6 uploads/day until a quota increase is granted (Google Cloud console ->
     IAM & Admin -> Quotas -> filter "YouTube Data API v3" -> request increase). This script
     is safe to re-run across multiple days: already-uploaded (team_code, artifact) rows
     are skipped via --results.

First run opens a browser for consent and caches a refresh token in --token-file; subsequent
runs are non-interactive until the token is revoked.

Only artifacts with status == "ok" and consent == "Agree" in data/assets.json are eligible.
This script never uploads anything a team declined to publish.

`team_code` is used only to locate the local video file (it is also the upload-stage folder
name, e.g. rcj-public-docs-upload-stage/L01/video.mp4) and to key the merge-ready results CSV
so it matches data/assets.json. Video titles/descriptions always use team_name, never the code.

Usage:
  python3 tools/upload_to_youtube.py --client-secrets client_secret.json --dry-run
  python3 tools/upload_to_youtube.py --client-secrets client_secret.json --limit 6

After a batch finishes, fold the results into data/assets.json:
  python3 tools/merge_drive_file_ids.py tools/youtube_upload_results.csv
"""
from __future__ import annotations

import argparse
import csv
import http.client
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "data" / "assets.json"
TEAMS = ROOT / "data" / "teams.json"
WINNERS = ROOT / "data" / "winners.json"
STAGE_ROOT = ROOT.parent / "rcj-public-docs-upload-stage"

VIDEO_ARTIFACTS = ("video", "launching_video")
FILE_CANDIDATES = {
    "video": ["video.mp4", "video.MP4", "video.mov"],
    "launching_video": ["launching_video.mp4", "launching_video.MP4"],
}
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}
RETRIABLE_EXCEPTIONS = (http.client.NotConnected, http.client.IncompleteRead,
                         http.client.ImproperConnectionState, http.client.CannotSendRequest,
                         http.client.CannotSendHeader, http.client.ResponseNotReady,
                         http.client.BadStatusLine, ConnectionError)


def load_teams() -> dict[str, dict]:
    data = json.loads(TEAMS.read_text(encoding="utf-8"))
    return {t["team_code"]: t for t in data["teams"]}


def load_winner_codes() -> set[str]:
    data = json.loads(WINNERS.read_text(encoding="utf-8"))
    return {e["team_code"] for entries in data.get("leagues", {}).values() for e in entries}


def load_eligible_assets(winner_codes: set[str]) -> list[dict]:
    """Video/launching_video, gated by consent OR the winner override: top-3 league
    winners get their video published regardless of their consent answer (BOM and
    source code have no such override — this applies to video/poster only)."""
    data = json.loads(ASSETS.read_text(encoding="utf-8"))
    return [
        a for a in data["assets"]
        if a["artifact"] in VIDEO_ARTIFACTS
        and a["status"] == "ok"
        and (a["consent"] == "Agree" or a["team_code"] in winner_codes)
        and (a["publishable"] or a["team_code"] in winner_codes)
    ]


def load_done(results_path: Path) -> set[tuple[str, str]]:
    if not results_path.exists():
        return set()
    done = set()
    with results_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            done.add((row["team_code"], row["artifact"]))
    return done


def resolve_local_file(team_code: str, artifact: str) -> Path | None:
    team_dir = STAGE_ROOT / team_code
    for name in FILE_CANDIDATES[artifact]:
        candidate = team_dir / name
        if candidate.exists():
            return candidate
    return None


def build_body(team_name: str, league: str, country: str, artifact: str, category_id: str,
                privacy: str, year: str) -> dict:
    kind = "Launching video" if artifact == "launching_video" else "Presentation video"
    title = f"{team_name} — {league} — RoboCupJunior {year}"
    if artifact == "launching_video":
        title += " (Launching video)"
    description = (
        f"{kind} for team {team_name} ({league} league, {country}) — "
        f"RoboCupJunior {year}."
    )
    return {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": ["RoboCupJunior", league, year],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }


def get_credentials(client_secrets: Path, token_file: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), scopes)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload_one(youtube, path: Path, body: dict) -> str:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    retry = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  uploaded {int(status.progress() * 100)}%", file=sys.stderr)
        except HttpError as exc:
            if exc.resp.status in RETRIABLE_STATUS_CODES and retry < 8:
                retry += 1
                time.sleep(min(64, 2 ** retry) + random.random())
                continue
            raise
        except RETRIABLE_EXCEPTIONS:
            if retry < 8:
                retry += 1
                time.sleep(min(64, 2 ** retry) + random.random())
                continue
            raise
    return response["id"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--client-secrets", type=Path, help="OAuth client_secret.json from Google Cloud Console")
    parser.add_argument("--token-file", type=Path, default=ROOT / "tools" / ".youtube_token.json")
    parser.add_argument("--results", type=Path, default=ROOT / "tools" / "youtube_upload_results.csv")
    parser.add_argument("--privacy", choices=["public", "unlisted", "private"], default="unlisted")
    parser.add_argument("--category-id", default="28", help="YouTube category id (28 = Science & Technology)")
    parser.add_argument("--year", default="2026")
    parser.add_argument("--limit", type=int, default=None, help="max uploads this run (quota safety)")
    parser.add_argument("--league", default=None, help="restrict to one league (Line/Maze/Simulation)")
    parser.add_argument("--dry-run", action="store_true", help="print the upload plan, upload nothing")
    args = parser.parse_args()

    teams_by_code = load_teams()
    winner_codes = load_winner_codes()
    eligible = load_eligible_assets(winner_codes)
    if args.league:
        eligible = [a for a in eligible if teams_by_code.get(a["team_code"], {}).get("league") == args.league]
    done = load_done(args.results)

    plan = []
    skipped_no_file = []
    for asset in eligible:
        key = (asset["team_code"], asset["artifact"])
        if key in done:
            continue
        local_file = resolve_local_file(asset["team_code"], asset["artifact"])
        if not local_file:
            skipped_no_file.append((*key, "no local video file found"))
            continue
        plan.append((asset, local_file))

    print(f"{len(plan)} eligible upload(s) pending, {len(done)} already done, "
          f"{len(skipped_no_file)} skipped (missing file).", file=sys.stderr)
    for team_code, artifact, reason in skipped_no_file:
        print(f"  SKIP {team_code}/{artifact}: {reason}", file=sys.stderr)

    if args.limit is not None:
        plan = plan[: args.limit]

    if args.dry_run:
        for asset, local_file in plan:
            team = teams_by_code.get(asset["team_code"], {})
            print(f"WOULD UPLOAD {team.get('league', '?')}/{team.get('team_name', asset['team_code'])}"
                  f"/{asset['artifact']} <- {local_file} ({local_file.stat().st_size / 1e6:.1f} MB)")
        return 0

    if not plan:
        print("Nothing to upload.", file=sys.stderr)
        return 0

    if not args.client_secrets:
        print("error: --client-secrets is required for a real (non --dry-run) upload", file=sys.stderr)
        return 2

    creds = get_credentials(args.client_secrets, args.token_file)
    from googleapiclient.discovery import build
    youtube = build("youtube", "v3", credentials=creds)

    args.results.parent.mkdir(parents=True, exist_ok=True)
    write_header = not args.results.exists()
    with args.results.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if write_header:
            writer.writerow(["team_code", "artifact", "backend", "preview_url", "view_url", "download_url"])
        for asset, local_file in plan:
            team = teams_by_code.get(asset["team_code"], {})
            team_name = team.get("team_name", asset["team_code"])
            league = team.get("league", "")
            country = team.get("country", "")
            body = build_body(team_name, league, country, asset["artifact"],
                               args.category_id, args.privacy, args.year)
            print(f"Uploading {league}/{team_name}/{asset['artifact']} "
                  f"({local_file.stat().st_size / 1e6:.1f} MB)...", file=sys.stderr)
            try:
                video_id = upload_one(youtube, local_file, body)
            except Exception as exc:  # noqa: BLE001 - surface and keep going
                print(f"  FAILED: {exc}", file=sys.stderr)
                continue
            preview_url = f"https://www.youtube.com/embed/{video_id}"
            view_url = f"https://www.youtube.com/watch?v={video_id}"
            writer.writerow([asset["team_code"], asset["artifact"], "youtube",
                              preview_url, view_url, view_url])
            handle.flush()
            print(f"  done: {view_url}", file=sys.stderr)

    print(f"Results appended to {args.results}. Merge with:\n"
          f"  python3 tools/merge_drive_file_ids.py {args.results}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
