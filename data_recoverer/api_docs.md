# DR API Endpoints (summary)

## GitHub
- **Commits**: `GET /repos/{owner}/{repo}/commits?per_page=100&since={iso}&until={iso}`  
  Filters by commit author date. Used to rebuild `commits` collection documents.
- **Issues**: `GET /repos/{owner}/{repo}/issues?state=all&per_page=100&since={iso}`  
  Returns issues and PRs; PRs are ignored in recovery, issues get turned into webhook-shaped docs.
- **Pull requests**: `GET /repos/{owner}/{repo}/pulls?state=all&sort=updated&direction=desc&per_page=100`  
  Walks pages until `updated_at` falls before the downtime window. Only closed PRs are normalized because the webhook handler only persists closed PRs.
- **Auth**: personal access token via `Authorization: Bearer <token>`. Pulled from `config_files/credentials_config.json` by `project_id`; falls back to `GITHUB_TOKEN` env var.
- **Rate limits**: retried with exponential backoff on 403/429/5xx.

## Taiga
- **Tasks**: `GET /api/v1/tasks?project={id}&modified_date__gte={iso}&modified_date__lte={iso}`  
  Normalized to `taiga_{project}.tasks` schema (`task_id` upsert key).
- **Issues**: `GET /api/v1/issues?project={id}&modified_date__gte={iso}&modified_date__lte={iso}`  
  Normalized to `taiga_{project}.issues` schema (`issue_id` upsert key).
- **User stories**: `GET /api/v1/userstories?project={id}&modified_date__gte={iso}&modified_date__lte={iso}`  
  Normalized with milestone and custom attributes preserved (`userstory_id` key).
- **Epics**: `GET /api/v1/epics?project={id}&modified_date__gte={iso}&modified_date__lte={iso}`  
  Upserted by `epic_id`.
- **Auth**: bearer token from Taiga (`taiga_user`/`taiga_password` resolved per project; falls back to `TAIGA_USERNAME`/`TAIGA_PASSWORD` env vars). Public projects can omit auth.
- **Rate limits**: exponential backoff on 429/5xx; project id resolved via `/projects/by_slug` when a slug is configured.

## Collections and upsert keys
- GitHub: `github_{project}.commits` (`sha`), `github_{project}.issues` (`issue_id`), `github_{project}.pull_requests` (`pr_number`).
- Taiga: `taiga_{project}.tasks` (`task_id`), `taiga_{project}.issues` (`issue_id`), `taiga_{project}.userstories` (`userstory_id`), `taiga_{project}.epics` (`epic_id`).

## Configuration hints
- Runtime config lives in `data_recoverer/config.yaml`.  
- Project IDs must match the `prj` query parameter used by the ingestion endpoints.  
- Window boundaries (`start_time` / `end_time`) come from `inactivity_intervals` collection produced by the Inactivity Detector.
