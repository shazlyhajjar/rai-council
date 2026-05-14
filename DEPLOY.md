# Deployment

Deploys the rai-council app behind a password-protected HTTPS subdomain on the existing Hetzner / Coolify box.

## Architecture

One Docker container. Multi-stage build:

1. Stage 1 (Node) builds the Vite frontend into `frontend/dist/`.
2. Stage 2 (Python) runs FastAPI on port 8001 AND serves the bundled frontend on the same origin. No CORS, no separate frontend container, no nginx-in-container.

Coolify's built-in proxy (Traefik) handles:

- HTTPS termination (Let's Encrypt cert for the subdomain).
- HTTP Basic Authentication middleware.
- Routing `council.calientedakar.com → container:8001`.

Persistent state lives in `/app/data/` — mount a host volume there so conversations + verdict log survive rebuilds.

## One-time setup

### 1. DNS

Add an A record at your DNS provider:

```
council.calientedakar.com    A    46.225.21.21
```

Wait for propagation (1-2 min on most providers).

### 2. Create the application in Coolify

In the Coolify dashboard:

1. **+ New** → **Application** → **Public Repository**
2. Repository: `https://github.com/shazlyhajjar/rai-council`
3. Branch: `master`
4. Build pack: **Dockerfile** (Coolify auto-detects the `Dockerfile` at repo root)
5. **Save**.

### 3. Configure the application

On the application's settings page:

- **General** → Name: `rai-council`
- **Domains** → add `council.calientedakar.com` (Coolify provisions HTTPS automatically; takes ~30s on first deploy)
- **Environment variables** (add all three; mark each as "Build variable: off, Runtime: on"):

  | Key | Value |
  |---|---|
  | `OPENROUTER_API_KEY` | `sk-or-v1-...` (copy from your local `~/.bash_profile`) |
  | `OPENAI_ADMIN_API_KEY` | `sk-admin-...` (use a **freshly rotated** key, not the one in chat history) |
  | `OPENAI_MONTHLY_CAP` | `50` |

- **Storages** → **+ New Volume Mount**:
  - Name: `rai-council-data`
  - Source path: leave blank (Coolify auto-creates a managed volume)
  - Destination path: `/app/data`

### 4. Add HTTP Basic Auth (Traefik middleware)

Coolify v4 doesn't have a one-click "Add Basic Auth" toggle, but you can add the Traefik middleware via container labels.

On the application → **Advanced** → **Container Labels**, paste:

```
traefik.http.middlewares.council-auth.basicauth.users=Shazly:<HASHED_PASSWORD>
traefik.http.middlewares.council-auth.basicauth.removeheader=true
traefik.http.routers.council-https-0.middlewares=council-auth
```

> **You need to generate `<HASHED_PASSWORD>` once.** From any Mac or Linux box:
>
> ```sh
> htpasswd -nbB Shazly 'Noemie11' | cut -d: -f2 | sed 's/\$/\$\$/g'
> ```
>
> Replace `<HASHED_PASSWORD>` in the label with the full output (the `\$\$` escaping is required so Docker doesn't interpret `$` as variable substitution).
>
> If you don't have `htpasswd`: `brew install httpd` on macOS, or use any online bcrypt generator and add `\$\$` escaping yourself.

The router name `council-https-0` follows Coolify's auto-generated convention — verify it in the dashboard's "Container labels" preview if Traefik refuses to apply the middleware.

### 5. Deploy

On the application page → **Deploy**.

Watch the build log. First build takes 2-3 min (Node + Python layers). Subsequent deploys cache and finish in ~30s.

### 6. Verify

Visit `https://council.calientedakar.com`. You should see:

1. Browser basic-auth prompt → enter `Shazly` / `Noemie11`.
2. The council UI loads, same as locally.
3. The header balance pills show live data (one quick health check: hit `https://council.calientedakar.com/api/health` after authenticating — should return `{"status":"ok","service":"LLM Council API"}`).

## Updates

Every push to `master` on GitHub can trigger a redeploy: in Coolify → application → **Source** → enable "Automatic deploy" and add the GitHub webhook URL Coolify shows you, or just hit **Deploy** manually when you push.

## Backups

`/app/data/` (mounted volume) holds:

- `conversations/*.json` — every chat.
- `verdicts.db` — the SQLite verdict log.

Set up a `pg_dump`-style snapshot of the volume in Coolify, or `rsync` the host path on a cron if you want offsite backups.

## If something goes wrong

Likely failure modes:

- **Build fails on `npm ci`** → check `frontend/package-lock.json` is committed (it is).
- **App boots but the frontend doesn't load** → the static mount only activates if `frontend/dist/` exists in the image. Check the build log for the Vite "✓ built in …" line.
- **API calls 404** → make sure the Traefik middleware label uses the right router name; if `council-https-0` is wrong, the basic-auth doesn't apply, but also nothing else should break.
- **Basic auth prompt loops** → the hash escaping is the usual culprit. `\$\$` (literal backslash-dollar-backslash-dollar) per `$` in the bcrypt output.
- **Balance pill says "unavailable"** → env var missing in Coolify, or the OpenAI admin key was rotated and the new one isn't pasted in.

Backend logs live in Coolify → application → **Logs**. The hardened error handling (commit `83af556`-ish) prints full tracebacks for SSE crashes and OpenRouter API failures.
