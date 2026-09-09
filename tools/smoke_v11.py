"""Real HTTP/WebSocket v11 workflow against the shipped launcher; isolated test DB."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "beam-backend"))
from storage import Store


async def websocket_role(origin, client, case_id, patient_id):
    cookie = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
    async with websockets.connect(
        origin.replace("http://", "ws://") + "/ws",
        origin=origin,
        additional_headers={"Cookie": cookie},
        proxy=None,
    ) as ws:
        initial = json.loads(await ws.recv())
        assert initial["payload"]["system"]["telemetry_contract"] == "beam-final-v11"
        records = initial["payload"]["his"]["cases"]
        selected = next(c for c in records if c["id"] == case_id)
        assert selected["patient_id"] is None
        assert patient_id not in json.dumps(initial)
        await ws.send(
            json.dumps(
                {
                    "action": "SET_ROOM_FINANCE",
                    "room_id": "forbidden",
                    "allocation_percent": 10,
                    "command_id": "viewer-v11-denied",
                }
            )
        )
        for _ in range(6):
            message = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if message.get("command_id") == "viewer-v11-denied":
                assert message["type"] == "COMMAND_REJECTED"
                return
        raise AssertionError("No rejection acknowledgement")


def main():
    with tempfile.TemporaryDirectory(prefix="beam-v11-smoke-") as folder:
        data = Path(folder) / "runtime"
        data.mkdir()
        store = Store(data / "beam.sqlite3")
        store.put("config", {"mode": "CONNECTED"})
        store.put("seeded", True)
        store.db.commit()
        store.db.close()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        env = {**os.environ, "BEAM_DATA_DIR": str(data), "BEAM_ALLOWED_ORIGINS": origin}
        with (Path(folder) / "server.log").open("w+") as log, httpx.Client(
            base_url=origin, headers={"Origin": origin}, trust_env=False, timeout=15
        ) as client:
            proc = None

            def start():
                proc = subprocess.Popen(
                    [sys.executable, str(ROOT / "RUN_BEAM.py"), "--port", str(port)],
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=log,
                )
                for _ in range(100):
                    if proc.poll() is not None:
                        raise RuntimeError("Server stopped")
                    try:
                        if client.get("/health").status_code == 200:
                            return proc
                    except httpx.ConnectError:
                        pass
                    time.sleep(0.1)
                proc.terminate()
                proc.wait(timeout=5)
                raise RuntimeError("Server startup timeout")

            def stop(proc):
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

            counter = 0

            def command(action, **fields):
                nonlocal counter
                counter += 1
                response = client.post(
                    "/api/commands",
                    json={
                        "action": action,
                        "command_id": f"v11-http-{counter}",
                        **fields,
                    },
                )
                assert response.status_code == 200, response.text
                return response.json()

            try:
                proc = start()
                assert client.get("/api/rooms/overview").status_code == 401
                response = client.post(
                    "/api/setup",
                    json={
                        "key": (data / "bootstrap-key.txt").read_text(),
                        "username": "v11-admin",
                        "password": "isolated-v11-password",
                    },
                )
                assert response.status_code == 200, response.text
                command("TOGGLE_AUTOPILOT", value=False)
                state = client.get("/api/state").json()
                room = next(
                    r
                    for r in state["rooms"]
                    if r["category"] == "OPERATING_ROOM"
                    and "GENERAL" in r["capabilities"]
                )
                rid = room["id"]
                pid = command(
                    "UPSERT_PATIENT",
                    record={
                        "mrn": "HTTP-SYNTHETIC",
                        "name": "Synthetic smoke patient",
                        "date_of_birth": "1985-01-01",
                        "sex": "UNKNOWN",
                    },
                )["record_id"]
                for role in ("SURGEON", "ANESTHESIOLOGIST", "NURSE"):
                    command(
                        "UPSERT_STAFF",
                        record={
                            "staff_code": "HTTP-" + role,
                            "name": "Synthetic " + role,
                            "role": role,
                            "specialties": ["GENERAL"],
                        },
                    )
                for kind in ("ANESTHESIA_MACHINE", "PATIENT_MONITOR", "SURGICAL_TABLE"):
                    did = command(
                        "UPSERT_DEVICE",
                        record={
                            "asset_tag": "HTTP-" + kind,
                            "name": "Synthetic " + kind,
                            "type": kind,
                            "room_id": rid,
                            "status": "AVAILABLE",
                            "commissioned_on": "2025-01-01",
                            "design_life_hours": 20000,
                            "runtime_hours": 100,
                            "maintenance_interval_hours": 1000,
                            "last_service_hours": 0,
                        },
                    )["record_id"]
                    command(
                        "SERVICE_DEVICE",
                        device_id=did,
                        efficiency_percent=99,
                        inspection_passed=True,
                        cost_vnd=0,
                        notes="Isolated HTTP fixture, no physical inspection",
                    )
                command(
                    "SET_DEVICE_ENGINEERING",
                    device_id=did,
                    minimum_performance_percent=80,
                    replacement_cost_vnd=2000000,
                    evidence="Synthetic specification",
                )
                command(
                    "RECORD_DEVICE_INSPECTION",
                    device_id=did,
                    observed_at=datetime.now(timezone.utc).isoformat(),
                    runtime_hours=100,
                    performance_percent=99,
                    evidence="Synthetic fixture",
                )
                cid = command(
                    "ADD_EXTERNAL_CASE",
                    case_label="HTTP-CASE",
                    procedure="Test procedure",
                    specialty="GENERAL",
                    urgency="ELECTIVE",
                    estimated_duration_min=60,
                    patient_id=pid,
                )["case_id"]
                plan = command("PREVIEW_SCHEDULE", case_ids=[cid])["plan"]
                assert len(plan["items"]) == 1, plan
                command("APPLY_SCHEDULE_PLAN", plan_id=plan["id"])
                rid = plan["items"][0]["scheduled_room_id"]
                detail = client.get("/api/rooms/" + rid).json()
                assert detail["current_case"]["patient"]["id"] == pid
                assert len(detail["current_case"]["team"]) == 3
                assert (
                    detail["current_case"]["clinical"]["predicted_success_percent"]
                    is None
                )
                command(
                    "SET_CASE_CLINICAL_INPUTS",
                    case_id=cid,
                    features={"asa_class": 2},
                    observed_at=datetime.now(timezone.utc).isoformat(),
                    source="Isolated fixture",
                )
                command("SET_ROOM_FINANCE", room_id=rid, allocation_percent=100)
                command("SET_HOSPITAL_CONFIG", config={"capex_vnd": 500000})
                command(
                    "RECORD_BMS_COST",
                    room_id=rid,
                    cost_vnd=100,
                    evidence="Synthetic incremental invoice",
                )
                command("RELEASE_ROOM_AUTOMATION", room_id=rid)
                for scope in ("facility", rid):
                    payload = {
                        "scope": scope,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "power_kw": 3,
                        "source": "Isolated HTTP fixture",
                    }
                    if scope == "facility":
                        payload["delta_p_pa"] = 15
                    else:
                        payload.update(
                            temp_c=20, humidity=45, airflow_m3h=room["max_airflow_m3h"]
                        )
                    response = client.post("/api/integrations/telemetry", json=payload)
                    assert response.status_code == 200, response.text
                # Wait for one measured tick before issuing a proposal, not for a fixed simulated interval.
                for _ in range(40):
                    if (
                        client.get(
                            "/api/energy",
                            params={
                                "scope": rid,
                                "source": "CONNECTED",
                                "resolution": "second",
                            },
                        ).json()["totals"]["observed_seconds"]
                        > 0
                    ):
                        break
                    time.sleep(0.1)
                else:
                    raise AssertionError("No measured samples")
                proposal = client.get("/api/integrations/targets").json()
                target = next(r for r in proposal["rooms"] if r["room_id"] == rid)
                response = client.post(
                    "/api/integrations/actuation",
                    json={
                        "proposal_id": proposal["proposal_id"],
                        "room_id": rid,
                        "revision": proposal["revision"],
                        "applied": True,
                        "feedback": {
                            k: target[k]
                            for k in (
                                "target_temp_c",
                                "target_humidity",
                                "target_airflow_m3h",
                            )
                        },
                        "detail": "HTTP contract fixture; no physical actuation",
                    },
                )
                assert response.status_code == 200, response.text
                for resolution in ("second", "minute", "hour", "day", "month", "year"):
                    report = client.get(
                        "/api/energy",
                        params={
                            "scope": rid,
                            "source": "CONNECTED",
                            "resolution": resolution,
                        },
                    ).json()
                    assert report["finance"]["capex_vnd"] == 500000
                    assert report["totals"]["measured_seconds"] > 0
                    assert report["source"] == "CONNECTED"
                assert (
                    client.get(
                        "/api/energy", params={"scope": rid, "source": "SIMULATION"}
                    ).json()["totals"]["observed_seconds"]
                    == 0
                )
                created = client.post(
                    "/api/users",
                    json={
                        "username": "v11-viewer",
                        "password": "isolated-viewer-password",
                        "role": "VIEWER",
                    },
                )
                assert created.status_code == 200, created.text
                with httpx.Client(
                    base_url=origin, headers={"Origin": origin}, trust_env=False
                ) as viewer:
                    assert (
                        viewer.post(
                            "/api/login",
                            json={
                                "username": "v11-viewer",
                                "password": "isolated-viewer-password",
                            },
                        ).status_code
                        == 200
                    )
                    assert viewer.get("/api/hospital").json()["patients"] == []
                    assert viewer.get("/api/clinical/models").status_code == 403
                    assert (
                        viewer.get("/api/rooms/" + rid)
                        .json()["current_case"]["patient"]
                        .get("mrn")
                        is None
                    )
                    asyncio.run(websocket_role(origin, viewer, cid, pid))
                stop(proc)
                proc = None
                proc = start()
                detail = client.get("/api/rooms/" + rid).json()
                assert detail["current_case"]["patient"]["id"] == pid
                assert (
                    detail["control"]["receipt"]["proposal_id"]
                    == proposal["proposal_id"]
                )
                assert detail["finance"]["service_cost_vnd"] == 100
                assert detail["instant_energy"]["actual_kw"] is None
                print(
                    f"PASS v11 integration: {counter} HTTP commands; room/resources/schedule, engineering, source-specific six-resolution energy/ROI, gateway receipt, HTTP+WS role redaction and restart"
                )
            except Exception:
                log.seek(0)
                print(log.read())
                raise
            finally:
                if proc is not None:
                    stop(proc)


if __name__ == "__main__":
    main()
