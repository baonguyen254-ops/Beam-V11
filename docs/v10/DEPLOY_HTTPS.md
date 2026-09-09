# BEAM v10 internal deployment

Start with the loopback launcher in `README.md`. Do not expose patient data through a public demo deployment. For an internal pilot, run one backend worker with a persistent `BEAM_DATA_DIR`, place it behind the hospital's approved HTTPS reverse proxy and enable WebSocket forwarding for `/ws`.

Forward the original Host and HTTPS scheme. Configure uvicorn proxy trust only for the actual proxy, for example `--proxy-headers --forwarded-allow-ips=127.0.0.1` when the reverse proxy runs locally. Correct HTTPS scheme is required for Secure cookies. Set `BEAM_ALLOWED_ORIGINS` to the exact HTTPS dashboard origin; no wildcard. Proxy timeouts must permit persistent WebSocket connections.

Use separate random BMS/HIS integration tokens stored in server environment or an approved secret manager. Keep `BEAM_DATA_DIR` on durable storage with restricted OS permissions. Back up using `tools/backup_data.py` and test restore using a separate data directory. For containers, mount a volume at `/data`; the image runs as UID 10001, so bind-mounted directories must allow that user to write.

```bash
docker build -t beam:v10 .
docker run --rm -p 127.0.0.1:8000:8000 -v beam-data:/data beam:v10
```

Docker build and Windows launchers are supplied but were not executed on their target platforms in this session. `render.yaml` includes a persistent disk and requires a configured origin; it has not been deployed. A Render `web` service can be publicly reachable, so use synthetic demo data unless the hospital's access restrictions are independently configured. Confirm the template against the provider's [Blueprint reference](https://render.com/docs/blueprint-spec) before use.

Before real patient use, add read permissions by clinical scope, account lifecycle/SSO policies, protected backups, approved retention and disk encryption. Before physical actuation, commission per-room sensors, PLC interlocks, actuator feedback and emergency policies. Do not use the bundled single facility-pressure signal as an independently validated OR pressure-control network.
