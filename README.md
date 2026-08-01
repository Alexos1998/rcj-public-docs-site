# RCJ Public Team Documents Site

Static GitHub Pages-ready outline for browsing team documents without storing large videos/PDFs/ZIPs in the repository. Team/robot photos are the exception — small enough to commit directly (see below).

## What is in this repo

- `index.html` — static frontend.
- `images/<team_code>/team_photo.*`, `images/<team_code>/robot_photo.*` — committed directly to the repo (resized to a max 900px edge). These are the only media type hosted in-repo; `data/assets.json` `backend: "local"` entries point here with a relative path.
- `data/teams.json` — token-free team metadata and publication consent status.
  - `keywords` — from each team's TDP "Keywords" question (source: `docevaluation Kopie/teams/<team_code>_*/answer_raw.json`). Blank or clearly-not-a-keyword-list (prose) answers are left empty rather than guessed at.
  - `introduction` — the TDP's "Abstract" question (TDP section 1, Introduction), extracted whole/verbatim, paragraph breaks preserved.
  - Both are unconditional: TDP submission itself cannot be marked "Disagree" (it's mandatory to enter), so every team that submitted a TDP has these fields populated when present.
  - A team with every consent field (`tdp`/`video`/`poster`/`bom`/`source_code`) set to `Disagree` is dropped from this file entirely, unless they are a top-3 league winner (see below).
- **Consent policy** (also enforced live in `index.html`'s `isPublished()`, not just baked into the data): `tdp` is mandatory/always shared. `poster` and `video`/`launching_video` are optional, but a top-3 league winner's poster and video are published regardless of what they answered (`WINNER_OVERRIDE_ARTIFACTS` in `index.html`). `bom` and `source_code` are fully optional with no override, ever — a winning team that declined those still has them hidden.
- `data/assets.json` — token-free asset manifest, keyed by `team_code`. Display always uses `team_name`; `team_code` never appears in the rendered site, only as the internal join key. `team_photo`/`robot_photo` use `backend: "local"` (path into `images/`); every other artifact is empty until uploaded to Drive/CDN/YouTube.
- `data/publication_consent.csv` — consent audit data.
- `data/score_budget_sensor_summary.json` and related CSVs — analysis summaries.
- `tools/source_upload_manifest.csv` — local source paths for upload automation. Do not publish this if you do not want local path names in the repo.
- `tools/merge_drive_file_ids.py` — fills `data/assets.json` from a Drive/CDN mapping CSV (works for Google Drive, YouTube, or any CDN/backend).
- `tools/upload_to_youtube.py` — uploads every consented `video`/`launching_video` asset to YouTube (matched to local files via `team_code`, which is also the upload-stage folder name) and appends a merge-ready CSV; see the script's `--help` / docstring for OAuth setup, quota, and usage.

## Why large files are not included

Videos, PDFs, ZIPs, and journals are too large for normal GitHub Pages/repo hosting and stay external (Google Drive, Cloudflare R2, S3, YouTube). Team/robot photos are committed to `images/` instead: hotlinking them from Google Drive's unauthenticated thumbnail proxy (`drive.google.com/thumbnail`) hits aggressive rate limits (`429`) once a league page renders 25-30 team cards at once, and same-repo images are faster and don't depend on Drive sharing settings.

## Google Drive workflow

1. Upload publishable files to Drive. Video is handled by the YouTube workflow below instead — Drive is for poster/BOM/TDP/journal.
2. Share each file as `Anyone with the link can view`.
3. Create a CSV like:

```csv
team_code,artifact,drive_file_id
L01,poster,1AbCdEfGhIjKlMnOpQrStUvWxYz
L01,bom,2BcDeFgHiJkLmNoPqRsTuVwXyZa
```

4. Merge it:

```bash
python3 tools/merge_drive_file_ids.py drive_file_map.csv
```

The tool writes Google Drive preview/view URLs into `data/assets.json`.

## CDN workflow

Create a CSV like:

```csv
team_code,artifact,backend,preview_url,view_url,download_url
L01,video,cdn,https://assets.example.org/teams/L01/video.mp4,https://assets.example.org/teams/L01/video.mp4,https://assets.example.org/teams/L01/video.mp4
```

Then run the same merge tool.

## YouTube workflow

1. Get an OAuth client (`client_secret.json`) — see `tools/upload_to_youtube.py`'s docstring.
2. Preview the plan without uploading or touching any API:

```bash
python3 tools/upload_to_youtube.py --dry-run
```

3. Upload (batched to stay under the daily API quota; safe to re-run — already-uploaded
   rows are skipped):

```bash
python3 tools/upload_to_youtube.py --client-secrets client_secret.json --limit 6
```

4. Merge the results into `data/assets.json`:

```bash
python3 tools/merge_drive_file_ids.py tools/youtube_upload_results.csv
```

Assets are uploaded when `consent == "Agree"`, or — for `video`/`launching_video` only — the team is a top-3 league winner (see the consent policy note above). BOM and source code have no such override, ever.

## Consent behavior

The frontend renders an asset only when:

- `status == "ok"`
- `consent == "Agree"` (or, for `video`/`launching_video`/`poster` only, the team is a top-3 league winner)
- a URL exists

Rows with `Disagree`, `Missing`, missing files, or no configured external URL are displayed as not embedded.

## GitHub Pages

Use this repository root as the Pages source, or move files into `/docs` if preferred.

If pushing manually:

```bash
git init
git add .
git commit -m "Initial public documents site"
git branch -M main
git remote add origin git@github.com:<owner>/<repo>.git
git push -u origin main
```
