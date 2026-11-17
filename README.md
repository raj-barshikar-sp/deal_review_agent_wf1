# Deal Review Agent (workflow 1)

A small FastAPI service that supports SailPoint deal review. It does two jobs:

1. **Purchase acknowledgement** (`POST /purchase-acknowledge`). It reads a "Purchase Acknowledgement" email, creates a task in the Asana *Deal Review Tracker*, and downloads the quote's PDFs from Salesforce (purchase order, fully executed quote, transaction approval form, master agreement).
2. **Quote lines** (`POST /quote-lines-drs`). It fetches a quote's lines from Salesforce and takes a time-stamped screenshot of the Salesforce *Quote Lines* report.

A single-page front end is served at `/`.

## Project layout

```
.
├── app/                         Application package
│   ├── main.py                  App factory, CORS, uvicorn entry point
│   ├── config.py                Paths (.env, downloads, screenshots, certs) and server settings
│   ├── schemas.py               Pydantic request/response models
│   ├── routes/                  HTTP layer only: parse, call a service, map errors to HTTP
│   │   ├── pages.py             GET /  and  GET /files
│   │   ├── asana.py             GET /asana/authorize, /asana/callback
│   │   ├── purchase.py          POST /purchase-acknowledge(ment)
│   │   └── quote_lines.py       POST /quote-lines-drs
│   ├── services/                Business logic that is not tied to one external system
│   │   ├── purchase.py          Parse the email subject/body into a task
│   │   └── files.py             Which local files /files may serve
│   ├── integrations/
│   │   ├── asana/               errors, settings, http, auth (OAuth + token cache), client, tasks
│   │   └── salesforce/
│   │       ├── constants.py     Document kinds, API version, token skew
│   │       ├── soql.py          SOQL builders and quote-ID validation
│   │       ├── http.py          Raw HTTP and form posts (no auth)
│   │       ├── auth.py          Client-credentials token cache
│   │       ├── client.py        Authenticated SOQL queries and file downloads
│   │       ├── documents.py     Classify, choose and save PDFs
│   │       ├── retrieval.py     retrieve_documents(): the full PDF workflow
│   │       ├── quote_lines.py   fetch_quote_lines()
│   │       └── screenshot/      JWT web login, headless Chrome, report capture, time stamp
│   ├── core/                    Shared helpers: .env reading/writing, TLS context
│   └── static/index.html        Front end
├── scripts/                     Manual tools (need real credentials in .env)
│   ├── fetch_quote_lines.py
│   └── screenshot_smoke.py
├── tests/                       Offline unit tests (pytest)
├── docs/                        Access guide, Salesforce setup, ITAI-1270 plan (docs/plan/)
├── salesforce_metadata/         SFDX project: custom objects, report, permission sets, ECA configs
├── certs/                       Public JWT certificate (the private key is git-ignored)
├── Dockerfile
├── requirements.txt             Runtime dependencies
└── requirements-dev.txt         Runtime plus pytest
```

Dependencies point one way: `routes` -> `services` / `integrations` -> `core` / `config`. Integrations never import from `routes`.

## Quick start

Requires Python 3.12+. For screenshots you also need Chrome and chromedriver.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt certifi
cp .env.example .env   # or create .env by hand, see Configuration
python -m app.main     # http://127.0.0.1:8000
```

`uvicorn app.main:app --reload` also works for development.

### Tests

```bash
pytest
```

The tests are offline and need no credentials.

### Manual scripts

Run these from the repo root. They call real Salesforce.

```bash
python -m scripts.fetch_quote_lines Q-127182
SCREENSHOT_TEST_QUOTE=Q-127182 python -m scripts.screenshot_smoke
```

### Docker

```bash
docker build -t deal-review-agent .
docker run -p 8080:8080 --env-file .env deal-review-agent
```

The image installs Chromium and chromedriver and starts `python -m app.main` on `$PORT` (8080).

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Front end |
| GET | `/files?path=...` | Download a saved PDF or screenshot (only inside `downloaded_docs/` and `screenshots/`) |
| GET | `/asana/authorize` | Start the Asana OAuth flow (only needed without a personal access token) |
| GET | `/asana/callback` | Asana OAuth redirect target |
| POST | `/purchase-acknowledge` (alias `/purchase-acknowledgement`) | Body `{"subject", "body"}`. The subject must end with ` - Purchase Acknowledgement for SailPoint Offerings`. The body must contain exactly one quote number like `Q-127182`. |
| POST | `/quote-lines-drs` | Body `{"quote_number": "Q-127182"}`. Returns the lines plus a screenshot path. |

Interactive docs are at `/docs`. For the deployed Cloud Run service and curl examples, see [docs/access.md](docs/access.md).

## Configuration

Settings come from the process environment, or from a git-ignored `.env` in the repo root. Real environment variables win.

**Server**

| Variable | Default | Notes |
| --- | --- | --- |
| `PORT` | `8000` | |
| `CORS_ORIGINS` | `http://127.0.0.1:8000,http://localhost:8000` | Comma separated |
| `CHROME_BIN`, `CHROMEDRIVER` | auto | Set in the Docker image |

**Salesforce, REST (documents and quote lines)**

| Variable | Notes |
| --- | --- |
| `SALESFORCE_INSTANCE_URL` | https My Domain URL |
| `SALESFORCE_CLIENT_ID`, `SALESFORCE_CLIENT_SECRET` | Client-credentials app. The cached token and its expiry are written back to `.env`. |
| `SALESFORCE_API_VERSION` | Default `v66.0` |

**Salesforce, screenshot login (JWT bearer)**

| Variable | Notes |
| --- | --- |
| `SALESFORCE_MY_DOMAIN_URL` | Falls back to `SALESFORCE_INSTANCE_URL` |
| `SALESFORCE_JWT_CLIENT_ID` | Falls back to `SALESFORCE_CLIENT_ID` |
| `SALESFORCE_USERNAME` | The integration user's exact username |
| `SALESFORCE_JWT_PRIVATE_KEY` / `SALESFORCE_JWT_KEY_FILE` | Or place the key at `certs/sf-jwt.key` |
| `SALESFORCE_JWT_AUDIENCE` | Optional override |
| `SALESFORCE_QUOTE_LINES_REPORT_ID` / `_REPORT_NAME` / `SALESFORCE_SCREENSHOT_URL` | Optional ways to point at the report. The default is the `Quote_Lines` report by developer name. |

Setup details are in [docs/salesforce-screenshot-setup.md](docs/salesforce-screenshot-setup.md).

**Asana**

| Variable | Notes |
| --- | --- |
| `ASANA_ACCESS_TOKEN` | Personal access token. Simplest option, used as-is. |
| `ASANA_CLIENT_ID`, `ASANA_CLIENT_SECRET`, `ASANA_REDIRECT_URI`, `ASANA_SCOPES` | OAuth alternative. Visit `/asana/authorize` once. The refresh token is saved to `.env`. |

Tasks are created in the project named in `app/integrations/asana/settings.py` (`PROJECT_NAME`). It must have the custom fields *Delivery Date*, *Period* and *Quote Number*.

## Runtime folders (git-ignored)

- `downloaded_docs/`: PDFs saved by `retrieve_documents`
- `screenshots/`: stamped PNGs plus `screenshot.log`

## Further reading

- [docs/access.md](docs/access.md): reaching the deployed service
- [docs/salesforce-screenshot-setup.md](docs/salesforce-screenshot-setup.md): integration user, certificate, report sharing
- [docs/plan/](docs/plan/): the ITAI-1270 deal review agent plan and diagrams
