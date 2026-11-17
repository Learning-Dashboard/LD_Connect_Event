# LD Connect – Event Ingestion Service

**LD Connect** is the entry point of the Learning Dashboard pipeline.
Whenever a student pushes to **GitHub**, edits a task on **Taiga**, or logs effort in **Google Sheets**, the event first reaches this service. LD Connect

1. **Authenticates** the webhook (HMAC signatures)
2. **Normalises** the payload to a common schema
3. **Persists** it in MongoDB (idempotent upserts)
4. **Notifies** LD Eval so metrics are recalculated in near real‑time

---

## Key features

| Feature | What it does | Where to look |
| --- | --- | --- |
| HMAC‑secured webhooks | Validates signatures from GitHub & Taiga | `routes/*_routes.py` |
| Source‑aware parsing | Converts raw payloads into domain‑specific documents | `datasources/*_handler.py` |
| Idempotent upserts | Natural IDs avoid duplicates on re‑delivery | `database/` |
| Per‑subject credentials | Each subject has its own GitHub token and Taiga server | `config/credentials_loader.py` |
| Asynchronous metric trigger | Posts a lightweight envelope to LD Eval | `routes/API_publisher/API_event_publisher.py` |
| Docker‑first deployment | Ready‑to‑run `Dockerfile` + Compose snippet | `docker-compose.yml` |

---

## Architecture at a glance

```text
┌──────────────┐   Webhook   ┌──────────────┐
│  GitHub      │───POST────▶ │              │
└──────────────┘             │              │
┌──────────────┐             │              │
│  Taiga       │───POST────▶ │  LD Connect  │──┐  POST /api/event
└──────────────┘             │              │  │
┌──────────────┐             │              │  │
│  GoogleSheet │───POST────▶│              │  │  (notify)
└──────────────┘             └──────────────┘  │
                                               ▼
                                       ┌─────────────┐
                                       │   LD Eval   │
                                       └─────────────┘
```

---

## Folder layout

```text
ldconnect/
├─ config/           # secrets, logging, settings
├─ config_files/     # teacher‑editable JSON (per‑subject credentials)
├─ database/         # pooled Mongo client
├─ datasources/      # GitHub / Taiga / Excel handlers
├─ routes/           # Blueprint per source + HMAC helpers
├─ utils/            # CLIs, recovery & admin scripts
├─ recovery/         # Back‑fill utilities (GitHub, Taiga)
└─ app.py            # Flask factory (run by Gunicorn)
```

---

## Quick start (local)

> Requires **Python ≥ 3.10** and a running **MongoDB** instance.

```bash
git clone https://github.com/PabloGomezNa/LD_Connect_Event.git
cd LD_Connect_Event
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# copy sample env and edit credentials / secrets
cp template.env .env

# create your per-subject credentials (GitHub token, Taiga server, teams)
cp config_files/credentials_config.example.json config_files/credentials_config.json

# run development server (single worker)
python app.py
```

Health‑check:

```bash
curl -X POST "http://127.0.0.1:5000/webhook/github?ping=1"
# → 403 Invalid Signature (expected, means server is alive)
```

---

## Production with Docker Compose

```bash
docker compose up -d --build ld_connect
```

* Exposes the service on port **5000** inside the container
* Mounts `./config_files` into `/app/config_files` as read-only
* Behind Nginx / Traefik, route
  `https://<your-domain>/webhook/{github|taiga|excel}` → `ld_connect:5000`

Before building or starting the service, make sure
`config_files/credentials_config.json` exists. It is used during local image builds
and can also be provided at runtime through the `./config_files` mount.
See [Per-subject credentials](#per-subject-credentials) for its content.

---

## Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `MONGO_HOST`, `MONGO_PORT`, `MONGO_DB` | no | MongoDB location (defaults `mongodb`, `27017`, `mongo`) |
| `MONGO_USER`, `MONGO_PASS`, `MONGO_AUTHSRC` | no | MongoDB credentials, when authentication is enabled |
| `CREDENTIALS_FILE` | no | Path of the per-subject credentials file (default `config_files/credentials_config.json`) |
| `GITHUB_SIGNATURE_KEY` | yes | HMAC key for GitHub signatures |
| `GITHUB_API_URL` | no | GitHub API URL (default `https://api.github.com`) |
| `TAIGA_SIGNATURE_KEY` | yes | HMAC key for Taiga signatures |
| `TAIGA_FALLBACK_API_URL` | see below | API URL of the fallback Taiga, e.g. `https://api.taiga.io/api/v1` |
| `TAIGA_FALLBACK_AUTH_URL` | see below | Login endpoint of the fallback Taiga, e.g. `https://api.taiga.io/api/v1/auth` |
| `TAIGA_FALLBACK_USERNAME` | see below | User of the fallback Taiga |
| `TAIGA_FALLBACK_PASSWORD` | see below | Password of the fallback Taiga |
| `WEBHOOK_URL_GITHUB`, `WEBHOOK_URL_TAIGA` | no | Public webhook URLs, used by the webhook deletion script |
| `EVAL_HOST` | no | Hostname of LD Eval (default `ld_eval`) |
| `EVAL_PORT` | no | LD Eval port (default `5001`) |
| `LOG_LEVEL` | no | `INFO` (default) or `DEBUG` |

Store them in `.env` (already referenced in `docker-compose.yml`); `template.env` is the starting point.

The `TAIGA_FALLBACK_*` variables are needed as soon as one subject does not have a
Taiga server of its own; see [Per-subject credentials](#per-subject-credentials).

There is no global GitHub token and no global Taiga server any more. `GITHUB_TOKEN`,
`TAIGA_API_URL`, `TAIGA_AUTH_URL`, `TAIGA_USERNAME`, `TAIGA_PASSWORD` and `TAIGA_TOKEN`
are ignored if they are still present in `.env`.

---

## Per-subject credentials

Each subject (course) can use a different Taiga server and a different GitHub token.
They are configured in `config_files/credentials_config.json`, one entry per subject.
The file is git-ignored; copy `config_files/credentials_config.example.json` to start.

```json
{
  "subject_with_university_taiga": {
    "github_token": "ghp_replace_me",
    "taiga_api_url": "https://taiga.university.example/api/v1",
    "taiga_auth_url": "https://taiga.university.example/api/v1/auth",
    "taiga_token": "replace_me_with_the_application_token",
    "teams": ["TeamAlpha", "TeamBeta"]
  },
  "subject_on_fallback_taiga": {
    "github_token": "ghp_replace_me",
    "taiga_api_url": "",
    "taiga_auth_url": "",
    "taiga_token": "",
    "teams": ["TeamGamma"]
  }
}
```

| Field | Required | Description |
| --- | --- | --- |
| `github_token` | yes | GitHub token used for every team of the subject |
| `taiga_api_url` | no | API URL of the subject's Taiga server (`.../api/v1`). Empty: fallback Taiga |
| `taiga_auth_url` | no | Login endpoint of the subject's Taiga server (`.../api/v1/auth`). Empty: fallback Taiga |
| `taiga_token` | no | Static Taiga token (application token or bearer token) |
| `taiga_user`, `taiga_password` | no | Taiga user and password, used to log in when there is no `taiga_token` |
| `teams` | yes | Identifiers of the teams of the subject: the `prj` value of their webhooks |

### How the credentials of a team are resolved

Every webhook event, recovery run and webhook deletion starts from the team (`prj`):

1. **Subject**: the entry whose `teams` list contains the team. A team that is in no
   list has no credentials. A team must be listed under one subject only.
2. **GitHub token**: the `github_token` of that subject. There is no fallback.
3. **Taiga server**:
   - `taiga_api_url` and `taiga_auth_url` both set: the subject's own server.
   - both empty: the fallback server, `TAIGA_FALLBACK_API_URL` and `TAIGA_FALLBACK_AUTH_URL`.
   - only one of them set: configuration error.
4. **Taiga credentials**, first match:
   1. `taiga_token`: sent as `Application <token>` when it contains `:` (Taiga
      application tokens), otherwise as `Bearer <token>`.
   2. `taiga_user` and `taiga_password`: login at the auth URL resolved in step 3.
   3. Only on the fallback server: `TAIGA_FALLBACK_USERNAME` and `TAIGA_FALLBACK_PASSWORD`.
   4. Otherwise: configuration error. A subject with its own server never uses the
      fallback user.

What happens when the resolution fails:

| Situation | Webhooks | Recovery endpoints |
| --- | --- | --- |
| Team in no `teams` list | GitHub push: `400 Unknown project credentials`. Taiga: the event is stored without the data fetched from the Taiga API | `400`, no job is created |
| Subject entry incomplete | GitHub push: `500 Credentials configuration error`. Taiga: as above | `500`, no job is created |

GitHub issue and pull request events do not call the GitHub API, so they are stored
in both situations. The webhook deletion script skips the teams it cannot resolve
and logs them.

Notes:

* The file is re-read when it changes on disk; adding a team or rotating a token does
  not need a restart.
* On start-up, every problem found in the file is written to the log as
  `Credentials config problem: ...`.
* The Admin Tool backend reads the same file to validate projects on import, so both
  services must see the same content.

---

## API reference

### `POST /webhook/github`

Receives any GitHub event subscribed in the repo webhook.
Requires headers `X-Hub-Signature` **and** `X-Hub-Signature-256`.

### `POST /webhook/taiga`

Receives Taiga events.
Requires header `X-Taiga-Webhook-Signature`.

### `POST /webhook/excel`

Receives Google Sheets JSON payloads created by the Apps Script add‑on.

Optional query parameters for all endpoints:

| Param | Example | Purpose |
| --- | --- | --- |
| `prj` (required) | `TeamA` | Team / project identifier |
| `quality_model` | `AMEP` | Override default quality model for the event |

All endpoints return **`200 OK`** immediately; heavy work continues asynchronously.

---

## Development & testing

```bash
pytest              # unit tests
```

If you just cloned the repository, set up `pre-commit` once before you start coding.
It will automatically run checks every time you commit, so common issues are caught early.

### First-time setup (after cloning)

```bash
# 1) create and activate a virtual environment (if you did not do it yet)
python -m venv .venv
source .venv/bin/activate

# 2) install project dependencies
pip install -r requirements.txt

# 3) install pre-commit in your environment
pip install pre-commit

# 4) install git hooks for this repository (one-time)
pre-commit install

# 5) optional: run checks on all files now
pre-commit run --all-files
```

### Why this helps

- `ruff` catches Python style/quality issues and can auto-fix many of them.
- `gitleaks` helps prevent committing secrets (tokens, passwords, keys).
- Because hooks run before each commit, problems are found locally instead of failing later in CI.

Configured hooks:

| Hook | Purpose |
| --- | --- |
| `ruff` | Python linting (with autofix) |
| `gitleaks` | Detect hardcoded secrets |

---

## FAQs

### What's the origin and purpouse of credentials_config.json?

Basically, when LD Connect receives an event from GitHub or Taiga, it often needs to fetch additional details about the event (e.g., commit info, milestone statistics) by calling the respective APIs. Each subject can use a different GitHub token and a different Taiga server, so these API calls cannot be authenticated with one global credential. The `credentials_config.json` file maps each subject to its GitHub token, its Taiga server and credentials, and its teams. When an event comes in with a `prj` parameter, LD Connect looks up the subject of that team and uses its credentials for any API request related to that event. The recovery tool and the webhook deletion script use the same lookup.

The schema and the resolution rule are described in [Per-subject credentials](#per-subject-credentials).

## Can i use LD Connect alone, without LD-infrastructure?

No, LD Connect is designed to work as part of the larger Learning Dashboard ecosystem. It relies on LD Eval for processing and calculating metrics based on the events it ingests. While you could technically run LD Connect in isolation, it would not be able to fulfill its intended purpose without the rest of the infrastructure, particularly LD Eval. Apart from that, LD Connect expects a mongodb instance to store the ingested events, so you would need to set that up as well (already included at ld-infrastructure).

## What is the expected GitFlow for this repository?

The expected GitFlow for this repository is as follows:
- The `main` branch is the stable production branch. Only thoroughly tested and reviewed code should be merged here.
- The `dev` branch is the main development branch where new features and bug fixes are integrated before they are ready for production. Developers should create feature branches off of `dev` for their work, and then merge back into `dev` once their work is complete and tested.
- Pull requests to `main` should only be made from `dev`, ensuring that all changes go through the development and testing process before reaching production. This is enforced by the CI workflow defined in `.github/workflows/main-pr.yml`, which checks that PRs to `main` come from `dev` only.

## License

Released under the **Apache License 2.0** – see [`LICENSE`](./LICENSE).

Part of the Master’s Thesis **“Redefinition of the Intake and Processing of Learning Dashboard Data”** (UPC · 2025).

---
