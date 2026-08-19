# Deploy to the cloud (run 24/7, watch from your phone)

One always-on cloud machine runs both the **trading loop** and the **dashboard**, sharing a SQLite
volume. You get an HTTPS link that works on mobile. Your desktop can be off.

> **Start on PAPER.** Everything below defaults to paper (no real orders). Only flip to live after
> paper convinces you, and only with a **trade-only** Kraken key (withdrawals disabled).

## Before you start
- A Kraken API key **only if going live** (paper needs none). Trade-only: enable *Query Funds* +
  *Create & Modify Orders*, leave *Withdraw* OFF.
- Pick a dashboard password (any strong string) → `DASH_PASSWORD`.

---

## Option A — Fly.io (recommended: one managed machine, HTTPS included)

1. Install flyctl and log in: `curl -L https://fly.io/install.sh | sh` then `fly auth login`.
2. Edit `fly.toml`: set a unique `app = "..."` and a `primary_region` near you.
3. Create the app without deploying: `fly launch --no-deploy --copy-config --name <your-app>`.
4. Create the persistent volume (holds the SQLite state):
   `fly volumes create botdata --size 1 --region <your-region>`.
5. Set secrets (never in git):
   ```
   fly secrets set DASH_PASSWORD='your-strong-password'
   # live only:
   fly secrets set KRAKEN_API_KEY='...' KRAKEN_API_SECRET='...'
   ```
6. Deploy: `fly deploy`.
7. On your phone open `https://<your-app>.fly.dev`, enter the password. Done.

To go live later: `fly secrets set` the Kraken keys, set `BOT_MODE=live` (edit `[env]` in fly.toml or
`fly secrets set BOT_MODE=live`), then `fly deploy`. Kill from anywhere: the dashboard's **kill-switch
button**, or `fly ssh console -C "python -m src.cli kill --pipeline meanrev"`.

---

## Option B — Cheap VPS + Docker Compose (more control, ~$5/mo)

1. Get a small VPS (DigitalOcean/Hetzner/Vultr) and install Docker + Docker Compose.
2. Point a domain's A record at the VPS IP; put it in `docker/Caddyfile` (replaces `bot.example.com`).
3. Create `.env` on the box (chmod 600):
   ```
   DASH_PASSWORD=your-strong-password
   BOT_MODE=paper
   # live only:
   KRAKEN_API_KEY=...
   KRAKEN_API_SECRET=...
   ```
4. `docker compose up -d --build`.
5. Phone → `https://your-domain`, enter the password.

Caddy auto-provisions HTTPS. The `bot` and `dashboard` services restart on crash independently.

### No domain? Use a private link instead (most secure)
Install [Tailscale](https://tailscale.com) on the VPS and your phone; drop the `caddy` service and
reach the dashboard at `http://<vps-tailscale-ip>:8501`. It's then reachable **only from your own
devices** — no public exposure at all. Keep `DASH_PASSWORD` set anyway.

---

## Security checklist (do all of these)
- [ ] Kraken key is **trade-only, withdrawals disabled**.
- [ ] `DASH_PASSWORD` set (the dashboard refuses to load without the password when it's set).
- [ ] HTTPS in front (Fly gives it; VPS uses Caddy) — or Tailscale-only access.
- [ ] `.env` / secrets never committed (they're gitignored; use the host's secret store on Fly).
- [ ] Running **paper** until you've watched it behave.
- [ ] Caps are small (defaults: 1% risk/trade, 10% portfolio heat, max 10 positions).

## Watching & controlling from mobile
- **Fleet overview** is the landing page: every pipeline compared, combined equity chart.
- **Kill switch**: open a pipeline in the sidebar → red **Engage kill switch** button. The loop
  flattens and stops on its next tick. Green button resumes.

## Cost
Fly.io free/near-free for one shared-cpu-1x/512MB machine + 1GB volume; a VPS is ~$4–6/mo. The bot's
own trading is separate (and on paper, $0).

## Adding more strategy pipelines later
Run another loop against the same box/volume with its own `--pipeline` name (e.g. a second Compose
service, or a second Fly `[processes]` entry). It gets its own DB and shows up on the fleet dashboard
automatically.
