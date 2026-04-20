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
├─ config_files/     # teacher‑editable JSON (HMAC keys…)
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

# create the directory that will contain your per-project API credentials
mkdir -p config_files

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

---

## Environment variables

| Variable | Description |
| --- | --- |
| `MONGO_URI` | MongoDB connection string |
| `GITHUB_SECRET` | HMAC key for GitHub signatures |
| `TAIGA_SECRET` | HMAC key for Taiga signatures |
| `EVAL_HOST` | Hostname of LD Eval (default `ld_eval`) |
| `EVAL_PORT` | LD Eval port (default `5001`) |
| `LOG_LEVEL` | `INFO` (default) or `DEBUG` |

Store them in `.env` (already referenced in `docker-compose.yml`).

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

Basically, when LD Connect receives an event from GitHub or Taiga, it often needs to fetch additional details about the event (e.g., commit info, issue details) by calling the respective APIs. To authenticate these API calls, LD Connect uses tokens that are specific to each project or team. The `credentials_config.json` file serves as a mapping between project identifiers (like "TeamA") and their corresponding API tokens. This way, when an event comes in with a `prj` parameter, LD Connect can look up the correct token to use for any API requests related to that event.

Minimal example:

```json
{
  "course_a": {
    "github_token": "ghp_replace_me",
    "taiga_user": "replace-me",
    "taiga_password": "replace-me",
    "teams": ["TeamAlpha", "TeamBeta"]
  }
}
```

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
