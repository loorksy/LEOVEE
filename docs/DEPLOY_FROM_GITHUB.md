# Deploy staging from GitHub (phone-friendly)

Do these five steps in order. No laptop terminal required after the SSH key is created once.

## Secrets to add (Settings → Secrets and variables → Actions)

### Required

| Secret | Paste |
|--------|--------|
| `VPS_HOST` | `72.60.83.140` |
| `VPS_USER` | `root` |
| `VPS_SSH_KEY` | Full private key (`-----BEGIN … PRIVATE KEY-----` through `-----END …-----`) |
| `OANDA_API_TOKEN` | Practice token only |
| `OANDA_ACCOUNT_ID` | Practice account id |
| `ANTHROPIC_API_KEY` | Anthropic key |
| `OPENAI_API_KEY` | OpenAI key |
| `SECRET_KEY` | Long random string (app JWT signing) |

### Optional (enable features when ready)

| Secret | Effect |
|--------|--------|
| `FINNHUB_API_KEY` | Research / news ingestion |
| `RESEND_API_KEY` | Transactional email |
| `METRICS_BEARER_TOKEN` | Protect `/metrics` |
| `SENTRY_DSN` | Error reporting |
| `ENCRYPTION_KEY` | Field encryption |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | Billing (keep manual until ready) |

**Do not add** a live OANDA token. Do not set `OANDA_EXECUTION` to true. Deploy hardcodes `OANDA_ENVIRONMENT=practice` and `OANDA_EXECUTION=false`, and refuses non-practice values.

---

## One-time: SSH deploy key

You need any device that can run a shell once (Codespace from phone browser, laptop, or iSH).

```bash
ssh-keygen -t ed25519 -f leovee-deploy -N "" -C "leovee-github-deploy"
```

1. Open `leovee-deploy` (private). Copy **all** of it → GitHub secret `VPS_SSH_KEY`.
2. Open `leovee-deploy.pub` (public). Copy the single line.
3. On the VPS (console / hosting panel), append that public line to:

```text
/root/.ssh/authorized_keys
```

4. Delete the local `leovee-deploy*` files after pasting.

---

## The five steps

### 1. Merge the code
- Merge **PR #18**, then **PR #19**, on GitHub (web UI).

### 2. Add secrets
- Repo → **Settings → Secrets and variables → Actions → New repository secret**
- Add every **Required** row above (and optional ones you have).

### 3. Trigger deploy
- Repo → **Actions → Deploy staging → Run workflow**
- Branch/tag: `main` (or the branch you merged)
- Leave **Run live Playwright after deploy** checked
- Tap **Run workflow**

### 4. Watch deploy
- Open the run. Deploy fails immediately with a named list if any required secret is missing.
- On success the job summary prints `DEPLOYED_COMMIT_SHA=…`.

### 5. Read E2E result
- Same run → job **Live Playwright (staging)**
- If red: open **Artifacts** → `playwright-staging-<sha>` (trace, screenshots, video)
- Assertions are not softened. Fix → re-run **Deploy staging**.

---

## Rotate a credential

1. Update the secret in GitHub.
2. Actions → **Deploy staging → Run workflow** again.
3. The workflow rewrites `/opt/leovee/.env` on the VPS (secrets never printed in logs).
