"""Exercise the actual English demo launcher through HTTP, without a browser."""

import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="beam-demo-transport-") as folder:
        data = Path(folder) / "demo"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        env = {**os.environ, "BEAM_ALLOWED_ORIGINS": origin}
        with (Path(folder) / "server.log").open("w+") as log, httpx.Client(
            base_url=origin, headers={"Origin": origin}, timeout=30, trust_env=False
        ) as client:
            process = None

            def start():
                process = subprocess.Popen(
                    [sys.executable, str(ROOT / "RUN_BEAM.py"), "--demo", "--demo-data-dir", str(data), "--port", str(port)],
                    cwd=ROOT, env=env, stdout=log, stderr=log,
                )
                for _ in range(300):
                    if process.poll() is not None:
                        raise RuntimeError("Demo launcher stopped")
                    try:
                        if client.get("/health").status_code == 200:
                            return process
                    except httpx.ConnectError:
                        pass
                    time.sleep(0.1)
                process.terminate()
                process.wait(timeout=10)
                raise RuntimeError("Demo launcher did not become healthy")

            def stop():
                nonlocal process
                if process:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    process = None

            commands = 0

            def command(action, command_id=None, **fields):
                nonlocal commands
                commands += 1
                result = client.post("/api/commands", json={"action": action, "command_id": command_id or f"demo-http-{commands}", **fields})
                assert result.status_code == 200, result.text
                result = result.json()
                assert result["ok"], result
                return result

            try:
                process = start()
                assert client.get("/health").json()["version"] == "11.1.0"
                assert client.get("/api/session").json()["demo_available"]
                assert client.get("/api/hospital").status_code == 401
                assert client.post("/api/demo/login", json={}, headers={"Origin": "https://untrusted.invalid"}).status_code == 403
                signed_in = client.post("/api/demo/login", json={})
                assert signed_in.status_code == 200, signed_in.text
                assert signed_in.json()["user"]["role"] == "ADMIN"
                assert not (data / "bootstrap-key.txt").exists()
                page = client.get("/").text
                assert 'lang="en"' in page and "v11.1 Hospital Intelligence" in page
                for asset in re.findall(r'(?:src|href)="(/assets/[^"]+)"', page):
                    assert client.get(asset).status_code == 200
                state = client.get("/api/state").json()
                assert state["system"]["demo"]["active"]
                cases = state["his"]["cases"]
                current = next(c for c in cases if c["status"] == "SCHEDULED")
                room_id = current["scheduled_room_id"]
                room = client.get("/api/rooms/" + room_id).json()
                prediction = room["current_case"]["clinical"]
                assert prediction["predicted_success_percent"] is not None
                assert prediction["cohort"]["source"] == "SIMULATION"
                assert room["forecast"]["thermal"]["eligible"]
                assert room["control"]["virtual_bms"]
                assert room["finance"]["projected_payback_years"] is not None
                models = client.get("/api/clinical/models").json()["models"]
                assert len(models) == 3 and all(m["status"] == "DEMO_READY" and m["review"] is None for m in models)
                features = {x["feature"]: x["value"] for x in prediction["contributions"] if x["feature"] != "age_years"}
                features["asa_class"] += 1
                command("SET_CASE_CLINICAL_INPUTS", case_id=current["id"], observed_at=prediction["inputs_observed_at"], source="Synthetic smoke-test inputs", features=features)
                changed = client.get("/api/rooms/" + room_id).json()["current_case"]["clinical"]
                assert changed["predicted_success_percent"] < prediction["predicted_success_percent"]
                saved = command("RUN_CASE_PREDICTION", command_id="saved-demo-prediction", case_id=current["id"])
                assert command("RUN_CASE_PREDICTION", command_id="saved-demo-prediction", case_id=current["id"])["replayed"]
                command("SET_ROOM_MANUAL_TARGETS", room_id=room_id, temp_c=22, humidity=52, airflow_percent=95)
                control = client.get("/api/rooms/" + room_id).json()["control"]
                assert control["target_temp_c"] == 22 and control["virtual_bms"]
                command("RELEASE_ROOM_AUTOMATION", room_id=room_id)
                pending = [c["id"] for c in cases if c["status"] == "UNSCHEDULED"][:2]
                proposal = command("PREVIEW_SCHEDULE", case_ids=pending)["plan"]
                command("APPLY_SCHEDULE_PLAN", plan_id=proposal["id"])
                for resolution in ("second", "minute", "hour", "day", "month", "year"):
                    energy = client.get("/api/energy", params={"scope": room_id, "source": "SIMULATION", "resolution": resolution}).json()
                    assert energy["points"] and energy["totals"]["measured_seconds"] == 0
                assert client.get("/api/energy", params={"source": "CONNECTED"}).json()["points"] == []
                assert client.get("/api/energy?resolution=day&format=csv").text.startswith("\ufeffperiod,")
                assert client.post("/api/integrations/telemetry", json={}).status_code == 403
                blocked = client.post("/api/commands", json={"action": "SET_HOSPITAL_CONFIG", "config": {"mode": "CONNECTED"}, "command_id": "demo-stays-simulated"})
                assert blocked.status_code == 422 and not blocked.json()["ok"]
                before = client.get("/api/energy?resolution=year").json()["totals"]["observed_seconds"]
                stop()
                process = start()
                after = client.get("/api/energy?resolution=year").json()["totals"]["observed_seconds"]
                assert 0 <= after - before < 60
                restarted = client.get("/api/rooms/" + room_id).json()["current_case"]["clinical"]
                assert any(p["id"] == saved["prediction"]["id"] for p in restarted["recorded_predictions"])
                assert command("RUN_CASE_PREDICTION", command_id="saved-demo-prediction", case_id=current["id"])["replayed"]
                print(f"PASS English demo: launcher, same-origin presenter login, populated room/models/traits/equipment/ROI, {commands} HTTP commands, editable computed prediction, scheduling, virtual BMS, six energy resolutions, isolation and restart without duplicate history")
            except Exception:
                log.seek(0)
                print(log.read())
                raise
            finally:
                stop()


if __name__ == "__main__":
    main()
