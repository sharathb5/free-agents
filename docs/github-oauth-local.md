# GitHub OAuth (local backend flow)

The upload UI opens `GET /github/oauth/start`, then a popup navigates to GitHub’s **OAuth authorize** URL. After the user approves, GitHub redirects the browser to **`GITHUB_OAUTH_REDIRECT_URI`** (your gateway), e.g. `http://localhost:4280/github/oauth/callback`. The gateway exchanges the code and returns HTML that `postMessage`s back to the frontend.

If you **never** see `GET /github/oauth/callback` in gateway logs, GitHub rejected or could not complete the authorize step. That is almost always **GitHub app configuration**, not Python code.

## 0. Local: get this working first (ordered)

Do these **in order** before worrying about Render.

1. **Run the API from the repo root** (so `app/config.py` can load `./.env` if you use one):

   ```bash
   source .venv/bin/activate   # or your venv
   uvicorn app.main:app --host 0.0.0.0 --port 4280
   ```

   Avoid `AGENT_TOOLBOX_DISABLE_DOTENV=1` unless you intend to skip `.env`.

2. **Set GitHub env vars** for that process (in `.env` or the shell):

   - `GITHUB_CLIENT_ID`
   - `GITHUB_CLIENT_SECRET`
   - `GITHUB_OAUTH_REDIRECT_URI=http://localhost:4280/github/oauth/callback`  
     (Use `127.0.0.1` instead of `localhost` only if you will use that **everywhere** the same way, including GitHub’s callback field.)

   **Pitfall:** If `make github-oauth-check` shows `github_oauth_redirect_uri` starting with `https://` and your **onrender.com** host, your local process is still using **production** redirect settings (often copied `.env`). GitHub then validates that HTTPS URL, not `http://localhost:...`, and your popup will never finish “locally” the way you expect. Use a **separate** local value (and register it on the same GitHub app).

3. **Confirm what the server actually loaded** (must show your Client ID and the same redirect URI):

   ```bash
   make github-oauth-check
   ```

   Or manually: `curl -sS "http://localhost:4280/github/oauth/debug" | python3 -m json.tool`

   If `oauth_configured` is false, the gateway does not see all three variables—fix env/cwd and restart uvicorn.

4. **Register that exact redirect URI** on the **same** GitHub app as that Client ID (OAuth App → **Authorization callback URL**, or GitHub App → **User authorization callback URL**). **One URL per line** in GitHub’s form. Do **not** put two URLs on one line separated by spaces or commas—GitHub treats that as a single invalid URL (a common cause of *redirect_uri is not associated* when mixing Clerk and gateway callbacks).

5. **Run the Next app** with the gateway URL explicit (defaults to localhost:4280 if unset):

   ```bash
   cd frontend
   NEXT_PUBLIC_GATEWAY_URL=http://localhost:4280 npm run dev
   ```

   Open the UI at the **same host** you will use in the browser (`http://localhost:3000` vs `http://127.0.0.1:3000`); `return_to` is `window.location.origin`, and it must stay consistent.

6. **Try “Connect GitHub” again.** If GitHub still shows *redirect_uri is not associated*, compare `redirect_uri` from step 3’s `oauth/start` output to GitHub’s field **byte-for-byte** (scheme, host, port, path).

## 1. Use credentials from one GitHub application

`GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` must come from the **same** GitHub developer application you configure below.

### Option A — Classic **OAuth App** (simplest for this flow)

1. GitHub → **Settings** → **Developer settings** → **OAuth Apps** → **New OAuth App** (or edit an existing one you own).
2. **Authorization callback URL**: set exactly to the value you put in `GITHUB_OAUTH_REDIRECT_URI`, for example:
   - `http://localhost:4280/github/oauth/callback`
3. Copy **Client ID** → `GITHUB_CLIENT_ID`, generate **Client secrets** → `GITHUB_CLIENT_SECRET`.

You can register **multiple** callback URLs (one per line) on a single OAuth App, e.g. Clerk’s URL **and** your local gateway URL.

### Option B — **GitHub App** (if your Client ID is from a GitHub App)

This repo still uses `https://github.com/login/oauth/authorize` (user OAuth). For a **GitHub App**, the setting you need is **User authorization callback URL** on the GitHub App’s settings page—not only the Clerk webhook/install URLs.

Add the same URL as in `GITHUB_OAUTH_REDIRECT_URI` there. If only Clerk’s callback is listed, GitHub will not send users to `http://localhost:4280/...`.

## 2. Match `redirect_uri` exactly

GitHub compares the `redirect_uri` query parameter to a registered callback **exactly** (scheme, host, port, path). Common mistakes:

- Trailing slash on one side only (`.../callback` vs `.../callback/`) — the gateway normalizes env values by stripping a trailing slash; keep GitHub’s field consistent with that.
- `127.0.0.1` in `.env` but `localhost` in GitHub (or the reverse).
- Callback registered on a **different** OAuth App than the `GITHUB_CLIENT_ID` you use locally.

## 3. Verify what the gateway sends

Call:

```bash
curl -sS "http://localhost:4280/github/oauth/start?return_to=http://localhost:3000" | jq .
```

Check:

- `authorization_url` — decode the `redirect_uri` query parameter; it must match GitHub.
- `redirect_uri` — same string the server uses for authorize and token exchange (compare to GitHub UI).

## 4. “The redirect_uri is not associated with this application”

GitHub shows this when the `redirect_uri` in the authorize URL is **not** listed on the **same** OAuth App / GitHub App as your `GITHUB_CLIENT_ID`.

### Fast check (running server)

`GET /github/oauth/debug` on the **same base URL** as your API (e.g. `http://localhost:4280/github/oauth/debug` or `https://free-agents.onrender.com/github/oauth/debug`) returns the exact `github_client_id` and `github_oauth_redirect_uri` this process uses. Those must match **one** GitHub application’s settings.

Then:

1. Call your running gateway (use the same base URL your frontend uses as `NEXT_PUBLIC_GATEWAY_URL`):

   `GET /github/oauth/start?return_to=http://localhost:3000`

2. Read the JSON field **`redirect_uri`** (or decode `redirect_uri` inside **`authorization_url`**). It must match **`github_oauth_redirect_uri`** from `/github/oauth/debug` and GitHub.

3. In GitHub → **Settings** → **Developer settings** → your **OAuth App** (or **GitHub App** → **User authorization callback URL**), add that value **exactly** (scheme, host, port, path—no extra slash). Save.

4. **`GITHUB_OAUTH_REDIRECT_URI`** in the environment for **this** server must equal that same string. Local and Render need different values if the API host differs; register **both** URLs on GitHub if you use both.

Common mismatch: only the production callback is registered, but you are hitting **localhost** (or the opposite).

Other gotchas:

- **Wrong settings page**: Callback on an OAuth App does **not** apply to a GitHub App (and vice versa). The Client ID in the URL must be the app you edited.
- **Multiple URLs on one line**: GitHub expects **one callback per line**, not `https://a...,https://b...`.
- **Org-owned app**: If the app lives under a GitHub **Organization**, open **Organization settings** → **Developer settings** → **OAuth Apps** (or **GitHub Apps**) and edit **that** app.
- **Render env not applied**: After changing env vars on Render, **redeploy** or restart so `/github/oauth/debug` shows the new `github_oauth_redirect_uri`.

## 5. If GitHub shows a 404 on authorize

Usually means **`client_id` is wrong** (typo, secret from another app, or app deleted) or you’re not editing the app that owns that Client ID. Open the authorize URL, confirm the `client_id=` value matches **Developer settings** for that application.

## 6. Local + production (two callback URLs)

Register **both** URLs on the same GitHub OAuth App (one per line), for example:

- `http://localhost:4280/github/oauth/callback`
- `https://free-agents.onrender.com/github/oauth/callback`

Then set **`GITHUB_OAUTH_REDIRECT_URI`** per environment so it matches where the **API** runs:

| Where the gateway runs | `GITHUB_OAUTH_REDIRECT_URI` |
|------------------------|-----------------------------|
| Local                  | `http://localhost:4280/github/oauth/callback` |
| Render / prod          | `https://<your-service>.onrender.com/github/oauth/callback` |

## 7. Frontend origin (`return_to`) and `postMessage`

`/github/oauth/start?return_to=<frontend origin>` must be an origin the gateway trusts:

- **`http://localhost:<port>`** and **`http://127.0.0.1:<port>`** are always allowed (e.g. Next.js on `:3000`).
- For a **deployed** frontend (HTTPS), either:
  - set **`CORS_ORIGINS`** to that exact origin (comma-separated, not `*`), e.g. `https://your-app.vercel.app`, **or**
  - set **`GITHUB_OAUTH_ALLOWED_RETURN_ORIGINS`** to the same origin(s).

The browser still calls the **API** using **`NEXT_PUBLIC_GATEWAY_URL`** in the frontend (local: `http://localhost:4280`, prod: `https://free-agents.onrender.com`). GitHub redirects to **`GITHUB_OAUTH_REDIRECT_URI`**, which must be the API host where `/github/oauth/callback` is served.

## 8. Production checklist

1. GitHub app: production callback URL registered (exact match).
2. Render (API): `GITHUB_OAUTH_REDIRECT_URI`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`.
3. Vercel / frontend host: `NEXT_PUBLIC_GATEWAY_URL=https://…` pointing at the API.
4. API: `CORS_ORIGINS` includes your frontend origin, or use `GITHUB_OAUTH_ALLOWED_RETURN_ORIGINS`.
