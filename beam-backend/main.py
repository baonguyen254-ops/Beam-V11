"""Single-process hospital dashboard. Hardware control remains in a validated gateway."""

from __future__ import annotations
import asyncio
import csv
import hmac
import io
import json
import logging
import os
import secrets
import ipaddress
import sqlite3
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from auth import Auth, COOKIE, SESSION_SECONDS
from beam_state import BEAM_VERSION, BeamState, TICK_SECONDS
from hospital import aware, number, text
from storage import encode
from engineering import finance
from privacy import for_role

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(
    os.getenv("BEAM_DATA_DIR", str(BASE_DIR / "data" / "runtime"))
).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.chmod(0o700)
beam_state = BeamState(
    Path(os.getenv("BEAM_FLOORPLAN_PATH", str(BASE_DIR / "data" / "floorplan.json"))),
    db_path=DATA_DIR / "beam.sqlite3",
    demo=os.getenv("BEAM_DEMO") == "1",
)
auth = Auth(beam_state.store, DATA_DIR)
demo_presenter = None
if beam_state.demo_enabled:
    presenter_id = beam_state.store.get("demo_presenter_id")
    row = beam_state.store.db.execute(
        "SELECT id,username,role FROM users WHERE id=? AND active=1", (presenter_id,)
    ).fetchone()
    if row:
        demo_presenter = dict(row)
    else:
        demo_presenter = auth.create_user(
            "demo-presenter-" + secrets.token_hex(3), secrets.token_urlsafe(48), "ADMIN"
        )
        beam_state.store.put("demo_presenter_id", demo_presenter["id"])
        beam_state.store.put("bootstrap_hash", None)
        beam_state.store.db.commit()
        auth.key_path.unlink(missing_ok=True)
connected_clients = {}
allowed_origins = [
    x.strip().rstrip("/")
    for x in os.getenv(
        "BEAM_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if x.strip() and x.strip() != "*"
]


def origin_ok(origin, host, scheme="http"):
    return bool(
        origin
        and (
            origin.rstrip("/") in allowed_origins
            or origin.rstrip("/") == f"{scheme}://{host}"
        )
    )


def current_user(request, roles=None):
    user = auth.user(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, "Authentication required")
    if roles and user["role"] not in roles:
        raise HTTPException(403, "Insufficient permissions")
    return user


async def body(request):
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > 131072:
            raise HTTPException(413, "Request too large")
    try:
        result = json.loads(
            chunks,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("Non-finite JSON")
            ),
        )
        if not isinstance(result, dict):
            raise ValueError("Object required")
        return result
    except (ValueError, UnicodeError):
        raise HTTPException(422, "A valid JSON object is required")


def session_response(user, request):
    response = JSONResponse(
        {"user": user, "needs_setup": False, "demo_available": bool(demo_presenter)}
    )
    response.set_cookie(
        COOKIE,
        auth.session(user),
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
    )
    return response


async def broadcast_state():
    if not connected_clients:
        return
    snapshot = beam_state.to_dict(include_floorplan=False)
    messages = {}

    async def send(ws, token):
        try:
            user = auth.user(token)
            if not user:
                await asyncio.wait_for(ws.close(1008), 1.5)
                connected_clients.pop(ws, None)
            else:
                role = user["role"]
                if role not in messages:
                    messages[role] = encode(
                        {"type": "STATE_UPDATE", "payload": for_role(snapshot, role)}
                    )
                await asyncio.wait_for(ws.send_text(messages[role]), 1.5)
        except Exception:
            connected_clients.pop(ws, None)

    await asyncio.gather(
        *(send(ws, token) for ws, token in list(connected_clients.items()))
    )


async def telemetry_loop():
    previous = time.monotonic()
    while True:
        await asyncio.sleep(TICK_SECONDS)
        now = time.monotonic()
        elapsed = min(5.0, max(0.0, now - previous))
        previous = now
        try:
            await beam_state.tick(elapsed)
            await broadcast_state()
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Telemetry tick failed")


@asynccontextmanager
async def lifespan(_):
    task = asyncio.create_task(telemetry_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        beam_state.checkpoint()
        beam_state.store.db.commit()


app = FastAPI(
    title="BEAM Hospital Intelligence", version=BEAM_VERSION, lifespan=lifespan
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def boundaries(request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if (origin or request.cookies.get(COOKIE)) and not origin_ok(
            origin, request.headers.get("host"), request.url.scheme
        ):
            return JSONResponse({"detail": "Untrusted request origin"}, status_code=403)
    response = await call_next(request)
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin",
        }
    )
    if request.url.path.startswith("/api/") or request.url.path in {
        "/state",
        "/floorplan",
        "/energy-baseline",
    }:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(ValueError)
async def value_error(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error(_, exc):
    beam_state.store.db.rollback()
    return JSONResponse(
        {"detail": "Record conflicts with an existing identifier"}, status_code=409
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": BEAM_VERSION,
        "clients": len(connected_clients),
        "mode": beam_state.hospital.config["mode"],
    }


@app.get("/api/session")
async def session(request: Request):
    return {
        "user": auth.user(request.cookies.get(COOKIE)),
        "needs_setup": auth.needs_setup,
        "demo_available": bool(demo_presenter),
    }


@app.post("/api/setup")
async def setup(request: Request):
    auth.throttle(request.client.host)
    p = await body(request)
    return session_response(
        auth.setup(p.get("key"), p.get("username"), p.get("password")), request
    )


@app.post("/api/login")
async def login(request: Request):
    auth.throttle(request.client.host)
    p = await body(request)
    return session_response(auth.login(p.get("username"), p.get("password")), request)


@app.post("/api/demo/login")
async def demo_login(request: Request):
    if (
        not demo_presenter
        or not beam_state.demo_enabled
        or beam_state.hospital.config["mode"] != "SIMULATION"
    ):
        raise HTTPException(404, "Demo presenter is not enabled in this workspace")
    try:
        local = ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        local = False
    if not local or not origin_ok(
        request.headers.get("origin"), request.headers.get("host"), request.url.scheme
    ):
        raise HTTPException(
            403, "Open the demo from this computer with a trusted origin"
        )
    auth.throttle("demo:" + request.client.host)
    return session_response(demo_presenter, request)


@app.post("/api/logout")
async def logout(request: Request):
    auth.logout(request.cookies.get(COOKIE))
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE)
    return response


@app.get("/api/users")
async def users(request: Request):
    current_user(request, {"ADMIN"})
    return [
        dict(r)
        for r in beam_state.store.db.execute(
            "SELECT id,username,role,active FROM users ORDER BY username"
        )
    ]


@app.post("/api/users")
async def create_user(request: Request):
    actor = current_user(request, {"ADMIN"})
    p = await body(request)
    user = auth.create_user(p.get("username"), p.get("password"), p.get("role"))
    beam_state.store.audit(actor["id"], "CREATE_USER", True, user["id"])
    beam_state.store.db.commit()
    return user


async def execute(p, user):
    if not isinstance(p.get("command_id"), str) or not 1 <= len(p["command_id"]) <= 120:
        raise ValueError("A command_id of 1 to 120 characters is required")
    result = await beam_state.handle_command(
        {**p, "actor": user["id"], "_role": user["role"]}
    )
    await broadcast_state()
    return result


@app.post("/api/commands")
async def commands(request: Request):
    result = await execute(await body(request), current_user(request))
    return JSONResponse(
        json.loads(encode(result)), status_code=200 if result["ok"] else 422
    )


@app.websocket("/ws")
async def socket(ws: WebSocket):
    token = ws.cookies.get(COOKIE)
    if not auth.user(token) or not origin_ok(
        ws.headers.get("origin"),
        ws.headers.get("host"),
        "https" if ws.url.scheme == "wss" else "http",
    ):
        await ws.close(1008)
        return
    await ws.accept()
    connected_clients[ws] = token
    await ws.send_text(
        encode(
            {
                "type": "STATE_INIT",
                "payload": for_role(
                    beam_state.to_dict(include_floorplan=True), auth.user(token)["role"]
                ),
            }
        )
    )
    recent = deque()
    try:
        while True:
            raw = await ws.receive_text()
            user = auth.user(token)
            if not user:
                await ws.close(1008)
                break
            now = time.monotonic()
            while recent and now - recent[0] > 10:
                recent.popleft()
            if len(raw) > 65536 or len(recent) >= 40:
                await ws.close(1008)
                break
            recent.append(now)
            p = {}
            try:
                p = json.loads(
                    raw,
                    parse_constant=lambda _: (_ for _ in ()).throw(
                        ValueError("Non-finite JSON")
                    ),
                )
                if not isinstance(p, dict):
                    raise ValueError("Command object required")
                result = await execute(p, user)
            except ValueError as exc:
                result = {
                    "ok": False,
                    "message": str(exc),
                    "command_id": p.get("command_id") if isinstance(p, dict) else None,
                }
            await ws.send_text(
                encode(
                    {
                        "type": "COMMAND_ACK" if result["ok"] else "COMMAND_REJECTED",
                        **result,
                    }
                )
            )
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        connected_clients.pop(ws, None)


@app.get("/api/state")
@app.get("/state")
async def state(request: Request):
    user = current_user(request)
    return for_role(beam_state.to_dict(include_floorplan=False), user["role"])


@app.get("/floorplan")
async def floorplan(request: Request):
    current_user(request)
    return beam_state.floorplan.public_dict()


@app.get("/energy-baseline")
async def baseline(request: Request):
    current_user(request)
    return beam_state.energy_baseline.public_dict()


@app.get("/api/hospital")
async def hospital(request: Request):
    user = current_user(request)
    return for_role(beam_state.hospital.public(), user["role"])


@app.get("/api/intelligence")
async def intelligence(request: Request):
    user = current_user(request)
    return for_role(
        beam_state.hospital.insights(datetime.now(timezone.utc)), user["role"]
    )


@app.get("/api/cases/archive")
async def archive(request: Request, q: str = "", limit: int = 20, offset: int = 0):
    current_user(request, {"ADMIN", "CLINICIAN"})
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("Invalid pagination")
    records = [
        c
        for c in beam_state.store.records("case_archive").values()
        if q.lower() in encode(c).lower()
    ]
    records.sort(
        key=lambda c: c.get("actual_end") or c.get("created_at") or "", reverse=True
    )
    return {
        "items": [
            {
                **c,
                "ai_predictions": beam_state.v11.data.get("predictions", {}).get(
                    c["id"], []
                ),
            }
            for c in records[offset : offset + limit]
        ],
        "total": len(records),
        "offset": offset,
        "limit": limit,
    }


@app.get("/api/rooms/overview")
async def room_overview(request: Request):
    user = current_user(request)
    return for_role(beam_state.v11.overview(datetime.now(timezone.utc)), user["role"])


@app.get("/api/rooms/{room_id}")
async def room_detail(request: Request, room_id: str):
    user = current_user(request)
    return for_role(
        beam_state.v11.room(room_id, datetime.now(timezone.utc)), user["role"]
    )


@app.get("/api/clinical/models")
async def clinical_models(request: Request):
    current_user(request, {"ADMIN", "CLINICIAN"})
    from clinical_models import FEATURES

    return {
        "models": list(beam_state.v11.models.models.values()),
        "features": {
            k: {"min": v[0], "max": v[1], "unit": v[2]} for k, v in FEATURES.items()
        },
    }


@app.get("/api/audit")
async def audit(request: Request, limit: int = 50, offset: int = 0):
    current_user(request, {"ADMIN", "CLINICIAN"})
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError("Invalid pagination")
    return [
        dict(r)
        for r in beam_state.store.db.execute(
            "SELECT * FROM audit ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
    ]


@app.get("/api/energy")
async def energy(
    request: Request,
    scope: str = "facility",
    resolution: str = "hour",
    start: str | None = None,
    end: str | None = None,
    format: str = "json",
    source: str | None = None,
):
    current_user(request)
    if scope != "facility" and scope not in beam_state.rooms:
        raise ValueError("Unknown scope")
    report = beam_state.store.history(
        scope,
        resolution,
        aware(start).timestamp() if start else None,
        aware(end).timestamp() if end else None,
        beam_state.hospital.config["timezone"],
        source or beam_state.hospital.config["mode"],
    )
    report["finance"] = finance(
        beam_state,
        beam_state.v11.data,
        scope,
        source,
        report["query_start"] if start or end else None,
        report["query_end"] if start or end else None,
    )
    if format == "json":
        return report
    if format != "csv":
        raise ValueError("Invalid format")
    output = io.StringIO()
    columns = [
        "period",
        "actual_kwh",
        "baseline_kwh",
        "saved_kwh",
        "savings_vnd",
        "carbon_kg",
        "observed_seconds",
        "measured_seconds",
        "average_kw",
        "baseline_kw",
    ]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(report["points"])
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="beam-energy.csv"'},
    )


def gateway_user(request, his=False):
    if beam_state.demo_enabled:
        raise HTTPException(
            403, "External integrations are disabled in the isolated demo workspace"
        )
    configured = os.getenv(
        "BEAM_HIS_INTEGRATION_TOKEN" if his else "BEAM_INTEGRATION_TOKEN", ""
    )
    if configured and hmac.compare_digest(
        request.headers.get("authorization", ""), "Bearer " + configured
    ):
        return {
            "id": "HIS_GATEWAY" if his else "BMS_GATEWAY",
            "role": "CLINICIAN" if his else "ADMIN",
        }
    return current_user(request, {"ADMIN", "CLINICIAN"} if his else {"ADMIN"})


@app.post("/api/integrations/telemetry")
async def telemetry(request: Request):
    gateway_user(request)
    p = await body(request)
    async with beam_state._lock:
        return beam_state.ingest_telemetry(p)


@app.get("/api/integrations/targets")
async def targets(request: Request):
    gateway_user(request)
    return beam_state.v11.targets(datetime.now(timezone.utc))


@app.post("/api/integrations/actuation")
async def actuation(request: Request):
    actor = gateway_user(request)
    p = await body(request)
    async with beam_state._lock:
        receipt = beam_state.v11.receipt(p, actor["id"], datetime.now(timezone.utc))
    return {"ok": True, "receipt": receipt}


@app.post("/api/integrations/device-hours")
async def device_hours(request: Request):
    actor = gateway_user(request)
    p = await body(request)
    if beam_state.hospital.config["mode"] != "CONNECTED":
        raise ValueError("Connected mode required")
    d = beam_state.hospital.devices.get(p.get("device_id"))
    if not d:
        raise ValueError("Unknown device")
    timestamp = aware(p.get("timestamp"))
    if not 0 <= (datetime.now(timezone.utc) - timestamp).total_seconds() <= 300:
        raise ValueError("Stale or future timestamp")
    if d.get("runtime_observed_at") and timestamp <= aware(d["runtime_observed_at"]):
        raise ValueError("Out-of-order runtime")
    hours = number(p.get("runtime_hours"), "Runtime", d["runtime_hours"], 1e9)
    d.update(
        runtime_hours=hours,
        runtime_observed_at=timestamp.isoformat(),
        runtime_source=text(p.get("source"), "Runtime source", 120),
    )
    beam_state.hospital.persist()
    beam_state.store.audit(actor["id"], "DEVICE_HOURS", True, d["id"])
    beam_state.store.db.commit()
    return {"ok": True}


@app.post("/api/integrations/his/commands")
async def his_commands(request: Request):
    user = gateway_user(request, True)
    p = await body(request)
    if p.get("action") not in {
        "UPSERT_PATIENT",
        "ADD_EXTERNAL_CASE",
        "ASSIGN_CASE",
        "UPDATE_CASE",
        "MANUAL_SCHEDULE_CASE",
        "CANCEL_CASE",
        "START_CASE",
        "COMPLETE_CASE",
        "RECORD_OUTCOME",
        "RECORD_CLINICAL_ESTIMATE",
        "SET_CASE_CLINICAL_INPUTS",
        "RUN_CASE_PREDICTION",
    }:
        raise HTTPException(403, "HIS command not allowed")
    result = await execute(p, user)
    return JSONResponse(
        json.loads(encode(result)), status_code=200 if result["ok"] else 422
    )


STATIC_DIR = BASE_DIR / "static"


@app.get("/{full_path:path}", include_in_schema=False)
async def frontend(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "Unknown API endpoint")
    if not (STATIC_DIR / "index.html").is_file():
        return JSONResponse(
            {"detail": "Frontend not built; run tools/build_frontend.py"},
            status_code=503,
        )
    candidate = (STATIC_DIR / full_path).resolve()
    if not candidate.is_relative_to(STATIC_DIR.resolve()):
        raise HTTPException(404)
    return FileResponse(candidate if candidate.is_file() else STATIC_DIR / "index.html")
