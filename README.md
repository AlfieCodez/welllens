# WellLens

WellLens is a self-hostable wellbeing-insights web app. You connect or upload your
own activity data (runs, rides, workouts) and WellLens turns it into clear,
plain-English insights — trends, training load, recovery signals — that go beyond
what any single fitness platform shows you.

The angle: most apps only see *their own* data. WellLens reads your own exported or
synced data from **any** source and does the analysis itself, surfacing things like
overtraining risk (ACWR) and week-on-week trends that a single-platform view misses.

It works entirely on **your own uploaded/synced data** — no Strava API, no lock-in.

---

## Features (Phase 1)

- **Accounts** — email/password (hashed with werkzeug) or Google sign-in.
- **Admin** — Google sign-in restricted to a server-side email allowlist.
- **Upload** — `.fit`, `.gpx`, `.tcx` files, parsed and normalised, with dedupe.
- **Insights engine** — all metrics computed in Python:
  - per-activity: distance, duration, avg/max HR, pace, elevation gain
  - rolling weekly distance & duration, week-on-week change
  - **ACWR** (acute:chronic workload ratio) with a low / balanced / watch / high flag
  - HR-adjusted pace trend (improving / steady / declining)
- **AI narration** — computed numbers are sent to Groq for a friendly summary, with a
  **plain-text fallback** so the app works with no AI key.
- **Dashboards** — user dashboard (metrics, ACWR flag, Chart.js charts, insight text)
  and an admin dashboard (users + counts).

**Phase 2 (Garmin auto-sync)** and **Phase 3 (PWA — installable + offline)** are built too.
See the Garmin and PWA sections below.

---

## Tech stack

Flask · SQLAlchemy + SQLite · Flask-WTF (CSRF) · Authlib (Google OAuth) ·
fitparse / gpxpy / python-tcxparser · Groq API · Jinja + vanilla JS · Chart.js (CDN).

All free / open source.

---

## Setup

> On Windows, `python` may be the Microsoft Store stub. Use the `py` launcher
> (as below) or your venv's interpreter directly.

```powershell
# 1. From the project root, create a virtual environment
py -m venv .venv

# 2. Activate it
.\.venv\Scripts\Activate.ps1        # PowerShell
# .venv\Scripts\activate.bat        # cmd
# source .venv/bin/activate         # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env from the template and fill it in
copy .env.example .env              # Windows
# cp .env.example .env              # macOS/Linux
```

### Environment variables (`.env`)

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | **yes** | Flask session signing. Generate: `py -c "import secrets; print(secrets.token_hex(32))"` |
| `FLASK_DEBUG` | no | `1` for dev auto-reload, `0` in production |
| `DATABASE_URL` | no | Defaults to `instance/welllens.db` (SQLite) |
| `MAX_UPLOAD_MB` | no | Per-file upload limit (default 25) |
| `GROQ_API_KEY` | no | Groq free-tier key. **If unset, WellLens uses the plain-text fallback.** |
| `GROQ_MODEL` | no | Default `llama-3.3-70b-versatile` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | no | Enables Google sign-in (user + admin). If unset, email/password still works. |
| `ADMIN_EMAILS` | for admin | Comma-separated allowlist of emails permitted admin access |
| `GARMIN_CONSUMER_KEY` / `GARMIN_CONSUMER_SECRET` | Phase 2 | Leave blank for now |

Secrets live only in `.env`, which is git-ignored. Never commit real keys.

---

## Running

```powershell
py run.py
```

Then open <http://127.0.0.1:5000>. The SQLite database and tables are created
automatically on first run (under `instance/`).

- `/` → redirects to the dashboard (if signed in) or the sign-in page.
- `/login` → the WellLens auth portal (sign in · register · admin).
- `/upload` → upload `.fit` / `.gpx` / `.tcx` files.
- `/dashboard` → your insights.
- `/admin` → admin dashboard (requires an allowlisted Google account).

### Setting up Google OAuth (optional)

1. Go to <https://console.cloud.google.com/apis/credentials>.
2. Create an **OAuth client ID** (type: Web application).
3. Add these **authorised redirect URIs**:
   - `http://127.0.0.1:5000/auth/google/callback`
   - `http://127.0.0.1:5000/admin/auth/google/callback`
4. Put the client ID/secret in `.env`, and your own email in `ADMIN_EMAILS`.

The admin restriction is enforced **server-side**: after Google returns a verified
email, WellLens checks it against `ADMIN_EMAILS` before granting an admin session.
The client is never trusted for this.

---

## Testing

```powershell
py -m pytest -q
```

Covers file parsing (`.gpx`, `.tcx`), the insights compute logic (ACWR thresholds,
weekly buckets, week-on-week change, pace trend), dedupe, and the auth flow.

---

## Garmin auto-sync (Phase 2)

WellLens can sync activities automatically from Garmin Connect, alongside manual upload
(which stays as the fallback). It uses **OAuth 2.0 PKCE** — Garmin's current scheme, since
OAuth 1.0a is being retired on 31 Dec 2026.

**Heads up:** the **Garmin Connect Developer Program is currently on hold** for new
sign-ups, so you may not be able to obtain credentials right now. The integration is fully
built and env-gated — it switches on the moment you have a client id/secret, and the app
works normally (upload-only) until then.

### How it works
1. **Link:** a user clicks *Connect Garmin* → OAuth 2.0 PKCE flow (`/connect/garmin`) →
   WellLens stores their access/refresh tokens and Garmin user id.
2. **Webhook:** Garmin sends a *ping* to `/webhooks/garmin` when a new activity is ready.
3. **Pull:** WellLens makes a signed request to download the activity **file** (`.FIT`/
   `.GPX`/`.TCX`), runs it through the **same parser + dedupe pipeline** as upload, and
   returns a quick `200`.

### Setup
1. Register an app in the [Garmin Connect Developer Program](https://developer.garmin.com/gc-developer-program/)
   and get your **client id/secret**.
2. Set in `.env`:
   ```
   GARMIN_CLIENT_ID=...
   GARMIN_CLIENT_SECRET=...
   GARMIN_REDIRECT_URI=https://YOURDOMAIN/connect/garmin/callback
   GARMIN_WEBHOOK_TOKEN=<py -c "import secrets; print(secrets.token_urlsafe(24))">
   ```
3. In the Garmin developer portal, register:
   - **Redirect URL:** `https://YOURDOMAIN/connect/garmin/callback`
   - **Ping/webhook URL:** `https://YOURDOMAIN/webhooks/garmin?token=YOUR_GARMIN_WEBHOOK_TOKEN`
4. Webhooks need a **public HTTPS URL**. For local testing use a tunnel
   (`tools/cloudflared.exe tunnel --url http://localhost:5000`); for production use your
   deployed domain (see `DEPLOYMENT.md`).

### Security
- The webhook is authenticated by the **secret token** embedded in its URL (Garmin doesn't
  HMAC-sign pings), and WellLens only ever acts on activity data it then **pulls from
  `apis.garmin.com`** itself. The webhook is CSRF-exempt (it's a server-to-server call).
- All OAuth signing/secret handling is server-side. Tokens are stored per user and
  refreshed automatically.

## Progressive Web App (Phase 3)

WellLens is an installable PWA with an offline app shell:
- Web manifest + brand icons (`/static/manifest.webmanifest`, `/static/icons/`).
- A service worker (`/sw.js`, root scope) — network-first navigations with an offline
  fallback page, cache-first static assets.
- Installable on desktop (Chrome/Edge address-bar **Install**) and mobile (**Add to Home
  Screen**). Requires HTTPS (or `localhost`); over a LAN IP the browser won't register the
  service worker.

Regenerate icons after a brand change: `py scripts/generate_icons.py`.

## Security notes

- Passwords are hashed with werkzeug; never stored or logged in plain text.
- Admin access is enforced via a server-side email allowlist, never the client.
- All secrets are environment variables; `.env` is git-ignored; `.env.example`
  documents every key.
- CSRF protection (Flask-WTF) is enabled on all POST forms.
- Uploads are validated by extension and size; bad files produce a friendly in-app
  error, not a stack trace.

---

## Project layout

```
welllens/
├── config.py              # env-driven config
├── run.py                 # dev entrypoint
├── welllens/
│   ├── __init__.py        # app factory
│   ├── models.py          # User, Activity
│   ├── auth/              # login, register, Google OAuth, admin allowlist
│   ├── activities/        # upload + parsing (.fit/.gpx/.tcx) + dedupe
│   ├── insights/          # compute (ACWR, trends) + Groq narration w/ fallback
│   ├── garmin/            # OAuth2 PKCE + webhook → pull → parse → dedupe
│   ├── dashboard/         # user + admin dashboards
│   ├── templates/         # Jinja (auth portal, dashboard, upload, admin)
│   └── static/            # CSS, JS, PWA (manifest, service worker, icons)
├── scripts/               # seed_dev.py, generate_icons.py
└── tests/                 # parsing, insights, dedupe, auth, garmin
```

---

## Roadmap

- ✅ **Phase 1 — core app** (auth, upload/parsing, insights, dashboards).
- ✅ **Phase 2 — Garmin auto-sync** (OAuth 2.0 PKCE + webhook → pull → same dedupe pipeline).
- ✅ **Phase 3 — PWA** (installable, offline app shell).
- **Next:** deploy to a stable HTTPS host (`DEPLOYMENT.md`), then app-store wrapping.
