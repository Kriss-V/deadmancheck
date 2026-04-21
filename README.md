# DeadManCheck

Open source cron job monitoring with **duration anomaly detection**.

Know when your scheduled jobs:
- Go silent (classic dead man's switch)
- Run but take **too long** (duration monitoring — unique to DeadManCheck)
- Explicitly fail

## Self-hosting

**Requirements:** Python 3.12+, PostgreSQL 14+, Redis 6+

```bash
git clone https://github.com/yourusername/deadmancheck
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

# Report explicit failure
curl https://your-instance.com/ping/YOUR-MONITOR-ID/fail?exit_code=1
```

If we don't receive a ping within `schedule + grace_period`, an alert fires.

If duration monitoring is enabled and the job takes longer than expected (hard max or >X% of rolling average), a separate duration anomaly alert fires.

## Stack

- **FastAPI** — API and server-rendered UI
- **PostgreSQL** — primary store (users, monitors, pings)
- **Redis** — start-ping cache for duration tracking (optional, falls back to in-memory)
- **APScheduler** — background checker, runs every 30s
- **Resend** — transactional email
- **Stripe** — billing (hosted cloud version only)
- **Alembic** — database migrations

## Hosted version

Don't want to run your own instance? Use [DeadManCheck.io](https://deadmancheck.io) — same codebase, managed for you.

Free for 5 monitors. Paid plans from $12/month.

## License

MIT
