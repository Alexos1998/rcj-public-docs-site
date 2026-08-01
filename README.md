# RCJ Public Team Documents Site

Static GitHub Pages-ready outline for browsing team documents without storing large videos/PDFs in the repository.

## What is in this repo

- `index.html` — static frontend.
- `data/teams.json` — token-free team metadata and publication consent status.
- `data/assets.json` — token-free asset manifest, keyed by `team_code`. Display always uses `team_name`; `team_code` never appears in the rendered site, only as the internal join key. URLs are empty until files are uploaded to Drive/CDN.
- `data/publication_consent.csv` — consent audit data.
- `data/score_budget_sensor_summary.json` and related CSVs — analysis summaries.
- `tools/source_upload_manifest.csv` — local source paths for upload automation. Do not publish this if you do not want local path names in the repo.
- `tools/merge_drive_file_ids.py` — fills `data/assets.json` from a Drive/CDN mapping CSV (works for Google Drive, YouTube, or any CDN/backend).
- `tools/upload_to_youtube.py` — uploads every consented `video`/`launching_video` asset to YouTube (matched to local files via `team_code`, which is also the upload-stage folder name) and appends a merge-ready CSV; see the script's `--help` / docstring for OAuth setup, quota, and usage.

## Why large files are not included

Videos, PDFs, ZIPs, and journals are too large for normal GitHub Pages/repo hosting. This site expects those files to live on Google Drive, Cloudflare R2, S3, YouTube, or another external host.

## Google Drive workflow

1. Upload publishable files to Drive.
2. Share each file as `Anyone with the link can view`.
3. Create a CSV like:

```csv
team_code,artifact,drive_file_id
L01,video,1AbCdEfGhIjKlMnOpQrStUvWxYz
L01,poster,2BcDeFgHiJkLmNoPqRsTuVwXyZa
L01,bom,3CdEfGhIjKlMnOpQrStUvWxYzAb
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

Only assets with `consent == "Agree"` are ever uploaded.

## Consent behavior

The frontend renders an asset only when:

- `status == "ok"`
- `consent == "Agree"`
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
