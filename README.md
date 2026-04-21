# DeadManCheck

Open source cron job monitoring. Know when your scheduled jobs go silent, run too long, or produce wrong output.

- **Dead man's switch** — alert if no ping within schedule + grace period
- **Duration monitoring** — alert if job takes too long (automatic baseline via rolling average)
- **Output assertions** — validate job payload on ping (e.g. `rows_exported > 0`) — no competitor has this
- **Website uptime monitoring** — active HTTP polling with alerts
- **Public status pages** — share a live status URL, free on all plans
- **Multi-channel alerts** — Email, Slack, Discord, Telegram, PagerDuty, Webhook
- **Prometheus metrics** — `/metrics` endpoint for scraping

## Self-hosting

**Requirements:** Python 3.12+, PostgreSQL 14+, Redis 6+

```bash
git clone https://github.com/Kriss-V/deadmancheck
cd deadmancheck

cp .env.example .env
# Edit .env with your database URL, secret key, Resend API key

pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or with Docker:

```bash
docker compose up
```

Then open `http://localhost:8000`.

## How it works

Each monitor gets a unique ping URL. Your cron job calls it after every successful run.

```bash
# Heartbeat only
curl https://your-instance.com/ping/YOUR-MONITOR-ID

# With duration tracking
curl https://your-instance.com/ping/YOUR-MONITOR-ID/start
./your_job.sh
curl https://your-instance.com/ping/YOUR-MONITOR-ID

# With output assertions (Developer+ on hosted)
curl -X POST https://your-instance.com/ping/YOUR-MONITOR-ID \
  -H "Content-Type: application/json" \
  -d '{"rows_exported": 1523, "status": "ok"}'

# Report explicit failure
curl https://your-instance.com/ping/YOUR-MONITOR-ID/fail?exit_code=1
```

If no ping is received within `schedule + grace_period`, an alert fires. If the job runs but takes longer than expected, a duration anomaly alert fires separately.

## Stack

- **FastAPI** — API and server-rendered UI
- **PostgreSQL** — primary store (users, monitors, pings)
- **Redis** — start-ping cache for duration tracking (optional, falls back to in-memory)
- **APScheduler** — background checker
- **Resend** — transactional email
- **Stripe** — billing (hosted cloud version only)
- **Alembic** — database migrations

## Hosted version

Don't want to run your own instance? Use [DeadManCheck.io](https://deadmancheck.io) — same codebase, managed for you.

| Plan | Price | Monitors |
|---|---|---|
| Hobby | Free | 5 |
| Developer | $12/month | 100 |
| Team | $39/month | 200 |
| Business | $99/month | Unlimited |

## License

MIT
