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
* Behind Nginx / Traefik, route  
  `https://<your-domain>/webhook/{github|taiga|excel}` → `ld_connect:5000`

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
locust -f tests/    # stress tests (replay real‑world payloads)
```

---

## License

Released under the **Apache License 2.0** – see [`LICENSE`](./LICENSE).

Part of the Master’s Thesis **“Redefinition of the Intake and Processing of Learning Dashboard Data”** (UPC · 2025).

---
