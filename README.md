# Djinn Antonic

Telegram Mini App for a house party bar. Guests open a paper-style cocktail menu, set the name on their ticket, and order. You (the bartender) add drink cards, toggle sold-out, and walk tickets from queued → mixing → ready → served. New orders also ping you in Telegram.

Stack: **FastAPI** + **aiogram 3** + **SQLite** + **Vite / TypeScript / Tailwind** (no React).

## What you need

| Variable | Purpose |
| --- | --- |
| `BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather). Used for HMAC initData checks and order notifications. |
| `BARTENDER_TELEGRAM_ID` | Your numeric Telegram user id. That account sees bartender screens; everyone else is a guest. |
| `WEBAPP_URL` | Public **HTTPS** URL of the Mini App (Telegram will not load `http://localhost`). |
| `DEV_TELEGRAM_USER_ID` | Optional. When set, a normal browser can call the API without Telegram initData. Use your bartender id to preview the bar book, or any other id for the guest menu. The local UI also has a Guest / Bartender toggle. |

Copy `.env.example` to `.env` and fill it in.

## Local run

Backend (from the repo root, with a venv):

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend (second terminal):

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` and `/media` to FastAPI.

For a production-style single process, `npm run build` in `frontend/`, then start uvicorn. FastAPI serves `frontend/dist` when that folder exists.

## BotFather and HTTPS

Telegram Mini Apps only load over HTTPS.

1. Talk to [@BotFather](https://t.me/BotFather): `/newbot`, copy the token into `BOT_TOKEN`.
2. Put a public HTTPS URL in `WEBAPP_URL`. For a home machine, Cloudflare Tunnel or ngrok in front of Vite (`5173`) or uvicorn (`8000` after a frontend build) works.
3. BotFather: `/mybots` → your bot → **Bot Settings** → **Menu Button** → set URL to the same `WEBAPP_URL`.
4. On startup the backend also calls `setChatMenuButton` and `/start` shows an **Open menu** Web App keyboard button.

Restart the backend after changing `WEBAPP_URL` so the menu button updates.

## How auth works

Every API call sends Telegram `initData`. The server checks the HMAC (secret derived from `BOT_TOKEN`) and reads `user.id`. If it equals `BARTENDER_TELEGRAM_ID`, the user is the bartender.

Locally, omit initData and set `DEV_TELEGRAM_USER_ID`, then open `http://127.0.0.1:5173` or `http://127.0.0.1:8000`. The public tunnel hostname still requires Telegram `initData`.

## Guest vs bartender

- Guests see available drinks only, can edit the display name (pre-filled from Telegram first name), order, and watch their ticket status (Queued / Mixing / Ready / Served).
- Repeat **Order** for another drink; there is no quantity picker.
- Bartender tabs: **Orders** (advance status), **Menu** (availability, edit, delete), **New drink** (photo + name + description).

Photos live in `backend/data/uploads/` and are served at `/media/...`.
