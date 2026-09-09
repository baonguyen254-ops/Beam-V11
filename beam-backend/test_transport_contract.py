from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx
from datetime import datetime, timedelta

import websockets

URL = "ws://127.0.0.1:8011/ws"


async def main(url: str, cookie: str, origin: str) -> None:
    async with websockets.connect(
        url,
        max_size=4_000_000,
        origin=origin,
        additional_headers={"Cookie": cookie},
        proxy=None,
    ) as ws:
        init = json.loads(await ws.recv())
        assert init["type"] == "STATE_INIT"
        state = init["payload"]
        assert state["system"]["version"] == "11.1.0"
        assert state["system"]["telemetry_contract"] == "beam-final-v11"
        assert len(state["floorplan"]["rooms"]) == 62
        provenance = state["roi"]["baseline_provenance"]
        assert provenance["calibrated"] is True
        assert provenance["calibration_tier"] == "FULL_ANNUAL_TABULAR"
        assert provenance["reference_resolution"] == "MONTHLY_MEAN"
        # The first sample is observed after startup, not invented for STATE_INIT.
        while state["roi"]["session_seconds"] == 0:
            update = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if update["type"] == "STATE_UPDATE":
                state = update["payload"]
        assert (
            state["roi"]["calibration_method"]
            == "MONTHLY_MEAN_FACILITY_REFERENCE_END_USE_SCALED_CONTROL_RATIO"
        )
        command_counter = 0

        async def command(payload: dict, expect_ok: bool = True):
            nonlocal command_counter, state
            command_counter += 1
            cid = f"transport-{command_counter}"
            await ws.send(
                json.dumps({**payload, "command_id": cid, "actor": "TransportTest"})
            )
            ack = None
            # Server sends direct ACK/REJECT and also broadcasts a state snapshot.
            # Accept either order and retain the latest state.
            for _ in range(8):
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
                if msg.get("type") == "STATE_UPDATE":
                    state = msg["payload"]
                elif msg.get("command_id") == cid and msg.get("type") in {
                    "COMMAND_ACK",
                    "COMMAND_REJECTED",
                }:
                    ack = msg
                    if (msg["type"] == "COMMAND_ACK") == expect_ok:
                        # wait briefly for the post-command state broadcast
                        try:
                            nxt = json.loads(
                                await asyncio.wait_for(ws.recv(), timeout=0.6)
                            )
                            if nxt.get("type") == "STATE_UPDATE":
                                state = nxt["payload"]
                        except asyncio.TimeoutError:
                            pass
                        break
            assert ack is not None, payload
            assert (ack["type"] == "COMMAND_ACK") == expect_ok, ack
            return ack

        await command({"action": "SET_LIGHTING", "value": 42})
        assert state["lighting"]["level_percent"] == 42
        await command({"action": "SET_TEMPERATURE_SETPOINT", "value": 21})
        await command({"action": "SET_HUMIDITY_SETPOINT", "value": 51})
        await command({"action": "SET_FAN_SPEED", "value": 75})
        assert state["controls"] == {
            "temp_setpoint": 21.0,
            "rh_setpoint": 51.0,
            "fan_speed": 75.0,
        }
        await command(
            {"action": "APPLY_CONTROL_PROFILE", "profile": "CLINICAL_STANDARD"}
        )
        assert state["controls"] == {
            "temp_setpoint": 20.0,
            "rh_setpoint": 50.0,
            "fan_speed": 75.0,
        }
        assert state["lighting"]["level_percent"] == 70
        await command({"action": "SET_PRESSURE_POLICY", "policy": "ENHANCED"})
        assert state["sterility"]["positive_pressure_policy"] == "ENHANCED"
        await command({"action": "SET_PRESSURE_POLICY", "policy": "STANDARD"})
        assert state["sterility"]["positive_pressure_policy"] == "STANDARD"

        await command({"action": "TOGGLE_ENERGY_AI", "value": False})
        assert state["energy_ai"]["enabled"] is False
        await command({"action": "TOGGLE_ENERGY_AI", "value": True})
        assert state["energy_ai"]["enabled"] is True

        first_or = next(r for r in state["rooms"] if r["category"] == "OPERATING_ROOM")
        for field in [
            "power_density_w_m2",
            "session_utilization_percent",
            "alarm_severity",
            "alarm_reasons",
            "trend",
            "openstudio_space_calibration",
            "lighting_design_w_m2",
            "equipment_design_w_m2",
            "max_airflow_source",
        ]:
            assert field in first_or, field
        await command(
            {
                "action": "SET_ROOM_MODE",
                "room_id": first_or["id"],
                "mode": "MAXIMUM_RUNNING",
            }
        )
        updated_or = next(r for r in state["rooms"] if r["id"] == first_or["id"])
        assert updated_or["manual_mode"] == "MAXIMUM_RUNNING"
        await command(
            {"action": "SET_ROOM_MODE", "room_id": first_or["id"], "mode": "BALANCE"}
        )
        await command(
            {
                "action": "SET_ROOM_MANUAL_TARGETS",
                "room_id": first_or["id"],
                "temp_c": 19.5,
                "humidity": 48,
                "airflow_percent": 72,
            }
        )
        updated_or = next(r for r in state["rooms"] if r["id"] == first_or["id"])
        assert updated_or["manual_targets"] == {
            "temp_c": 19.5,
            "humidity": 48.0,
            "airflow_percent": 72.0,
        }
        await command(
            {"action": "RESET_ROOM_MANUAL_TARGETS", "room_id": first_or["id"]}
        )
        updated_or = next(r for r in state["rooms"] if r["id"] == first_or["id"])
        assert updated_or["manual_targets"] is None

        await command({"action": "TOGGLE_AUTOPILOT", "value": False})
        assert state["autopilot"] is False
        patient_ack = await command(
            {
                "action": "UPSERT_PATIENT",
                "record": {
                    "mrn": "TRANSPORT-1",
                    "name": "Transport test only",
                    "date_of_birth": "1980-01-01",
                    "sex": "UNKNOWN",
                },
            }
        )
        ack = await command(
            {
                "action": "ADD_EXTERNAL_CASE",
                "case_label": "EXT-CONTRACT",
                "procedure": "Contract Test Procedure",
                "specialty": "GENERAL",
                "urgency": "URGENT",
                "estimated_duration_min": 55,
                "patient_id": patient_ack["record_id"],
                "notes": "No patient identifier",
            }
        )
        case_id = ack.get("case_id")
        assert case_id
        case = next(c for c in state["his"]["cases"] if c["id"] == case_id)
        assert case["status"] == "UNSCHEDULED"
        eligible = case["eligible_room_ids"][0]
        future = (datetime.now().astimezone() + timedelta(days=1)).replace(
            second=0, microsecond=0
        )
        await command(
            {
                "action": "MANUAL_SCHEDULE_CASE",
                "case_id": case_id,
                "room_id": eligible,
                "start": future.isoformat(),
            }
        )
        case = next(c for c in state["his"]["cases"] if c["id"] == case_id)
        assert case["status"] == "SCHEDULED"
        assert case["scheduled_room_id"] == eligible
        await command({"action": "TOGGLE_AUTOPILOT", "value": True})

        await command({"action": "STRESS_TEST_PRESSURE"})
        assert state["sterility"]["pressure_alarm"] is True
        await command({"action": "RESTORE_PRESSURE"})
        assert state["sterility"]["pressure_alarm"] is False

        for mode in [
            "Immediate Smoke/Purge Mode",
            "Post-Op Sterilization Mode",
            "Negative Pressure Isolation Mode",
        ]:
            await command({"action": "EMERGENCY_MODE", "mode": mode})
            assert state["emergency_mode"] == mode
            await command({"action": "CLEAR_EMERGENCY_MODE"})
            assert state["emergency_mode"] is None

        await command({"action": "NO_SUCH_COMMAND"}, expect_ok=False)
        print(
            f"PASS transport contract: {command_counter} WebSocket commands validated"
        )


def run_isolated_transport():
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="beam-transport-") as folder:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        env = {**os.environ, "BEAM_DATA_DIR": folder, "BEAM_ALLOWED_ORIGINS": origin}
        with (Path(folder) / "server.log").open("w+") as log:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=root,
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                with httpx.Client(
                    base_url=origin,
                    trust_env=False,
                    headers={"Origin": origin},
                    timeout=10,
                ) as client:
                    for _ in range(100):
                        if proc.poll() is not None:
                            raise RuntimeError("Server stopped during startup")
                        try:
                            if client.get("/health").status_code == 200:
                                break
                        except httpx.ConnectError:
                            pass
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("Server did not start")
                    response = client.post(
                        "/api/setup",
                        json={
                            "key": (Path(folder) / "bootstrap-key.txt").read_text(),
                            "username": "transport",
                            "password": "transport-test-password",
                        },
                    )
                    assert response.status_code == 200, response.text
                    cookie = "; ".join(
                        f"{key}={value}" for key, value in client.cookies.items()
                    )
                    asyncio.run(main(f"ws://127.0.0.1:{port}/ws", cookie, origin))
            except Exception:
                log.seek(0)
                print(log.read())
                raise
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


if __name__ == "__main__":
    run_isolated_transport()
