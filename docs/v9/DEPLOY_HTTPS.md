# B.E.A.M. v9 PRO — HTTPS deployment guide

Production uses a **single origin**: FastAPI serves the built React app and the WebSocket endpoint. If your platform gives you:

```text
https://beam.example.com
```

the browser automatically connects to:

```text
wss://beam.example.com/ws
```

This avoids mixed-content errors, a second public port, and most CORS mistakes.

## Before deployment

Run locally first:

```bat
INSTALL_BEAM.bat
START_BEAM.bat
```

Verify:

```text
http://127.0.0.1:8000/health
```

reports `version: 9.0.0`, and confirm the dashboard shows no VERSION MISMATCH banner.

## Render

1. Put the **whole v9 project folder** in a GitHub repository.
2. Create a new Render Blueprint/Web Service from that repository.
3. Render detects `render.yaml` and builds the included `Dockerfile`.
4. Wait for the health check `/health` to pass.
5. Open the HTTPS URL Render gives you.
6. Test from another device/network and verify the top badge says **Live model backend**.

The Render service must support WebSocket upgrades; Render Web Services do.

## Generic Docker platform

```bash
docker build -t beam-v9 .
docker run --rm -p 8000:8000 beam-v9
```

Then place the container behind the host's HTTPS reverse proxy. The proxy must pass WebSocket Upgrade/Connection headers.

## Production build structure

The Docker image does this automatically:

```text
Node build stage
  beam-frontend -> npm install -> npm run build
                       |
                       v
                 frontend/dist
                       |
Python runtime stage   v
  beam-backend/static/
                       |
                       +-- FastAPI serves /
                       +-- FastAPI serves /ws
```

## Security boundary

The current project is suitable for a controlled demo, not public clinical use.

Before exposing it broadly, add at minimum:

- authentication and authorization,
- TLS-only access,
- rate limits,
- persistent database/state store,
- audit retention,
- secrets management,
- input validation appropriate to your deployment,
- privacy controls.

Do **not** enter real patient names, medical record numbers or other PHI into an Internet-facing demo.

## State persistence

Plant/HIS state is in memory. A server restart resets the live session, trend buffers, session utilization and generated HIS state. This is intentional for the prototype. PostgreSQL/Redis or another state layer should be added before production reliance.

## Custom WebSocket URL

Normally leave `VITE_BEAM_WS_URL` unset in production. Same-origin discovery is safer.

Only set it if frontend/backend are intentionally separated:

```text
VITE_BEAM_WS_URL=wss://api.example.com/ws
```

If you split the origins, also configure `BEAM_ALLOWED_ORIGINS` on the backend.

## Troubleshooting remote access

### Page opens but says Offline / retrying

Check the browser console and make sure your proxy supports WebSockets. Visit:

```text
https://your-domain/health
```

If `/health` works but `/ws` does not, it is usually a proxy/WebSocket configuration problem.

### VERSION MISMATCH

The host is serving frontend and backend artifacts from different releases. Rebuild/redeploy the **whole v9 repository**, not only the frontend files.

### Floorplan missing online

Check that Docker copied:

```text
beam-backend/data/floorplan.json
beam-backend/data/Hospital.osm
beam-backend/data/or_capabilities.json
```

The supplied Dockerfile copies the entire backend directory, so these should be present unless your repository excluded them.
