"""Configurable Modbus TCP gateway. Default is telemetry-only; --apply is explicit.

Supported: input/holding registers, uint16/int16/uint32/float32, word/byte order.
No device-specific addresses are assumed. PLC interlocks remain authoritative.
"""

import argparse
import json
import math
import os
import socket
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FORMATS = {"uint16": "H", "int16": "h", "uint32": "I", "float32": "f"}


def finite(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError("Finite numeric engineering value required")
    return float(value)


def point_spec(point):
    if not isinstance(point, dict) or point.get("type") not in FORMATS:
        raise ValueError("Register mapping requires an explicit supported type")
    count = 2 if point["type"] in {"uint32", "float32"} else 1
    address = point.get("address")
    if type(address) is not int or not 0 <= address <= 65536 - count:
        raise ValueError("Use a zero-based register address in 0..65535")
    if point.get("word_order", "big") not in {"big", "little"} or point.get(
        "byte_order", "big"
    ) not in {"big", "little"}:
        raise ValueError("Explicit big/little word and byte ordering required")
    if finite(point.get("scale", 1)) <= 0:
        raise ValueError("Positive scale required")
    finite(point.get("offset", 0))
    return address, count


def transform_words(raw, point):
    words = [raw[i : i + 2] for i in range(0, len(raw), 2)]
    if point.get("byte_order", "big") == "little":
        words = [w[::-1] for w in words]
    if point.get("word_order", "big") == "little":
        words.reverse()
    return b"".join(words)


def decode_registers(raw, point):
    _, count = point_spec(point)
    if len(raw) != count * 2:
        raise ValueError("Register width mismatch")
    result = struct.unpack(">" + FORMATS[point["type"]], transform_words(raw, point))[0]
    return finite(result) * point.get("scale", 1) + point.get("offset", 0)


def encode_registers(value, point):
    point_spec(point)
    value = finite(value)
    lo, hi = finite(point.get("min")), finite(point.get("max"))
    if not lo <= value <= hi:
        raise ValueError("Target outside commissioned engineering bounds")
    raw = (value - point.get("offset", 0)) / point.get("scale", 1)
    if point["type"] != "float32":
        raw = round(raw)
    return transform_words(struct.pack(">" + FORMATS[point["type"]], raw), point)


class ModbusTCP:
    def __init__(self, config):
        self.host = config["host"]
        self.port = config.get("port", 502)
        self.unit = config.get("unit_id", 1)
        self.timeout = config.get("timeout_seconds", 2)
        if (
            type(self.port) is not int
            or not 1 <= self.port <= 65535
            or type(self.unit) is not int
            or not 0 <= self.unit <= 255
        ):
            raise ValueError("Invalid Modbus port or unit ID")
        if not 0.1 <= finite(self.timeout) <= 5:
            raise ValueError("Timeout must be 0.1 to 5 seconds")
        self.transaction = 0

    @staticmethod
    def receive(sock, count):
        data = bytearray()
        while len(data) < count:
            chunk = sock.recv(count - len(data))
            if not chunk:
                raise ConnectionError("PLC closed a partial frame")
            data.extend(chunk)
        return bytes(data)

    def request(self, pdu):
        self.transaction = (self.transaction + 1) % 65536
        header = struct.pack(">HHHB", self.transaction, 0, len(pdu) + 1, self.unit)
        with socket.create_connection(
            (self.host, self.port), timeout=self.timeout
        ) as sock:
            sock.sendall(header + pdu)
            tid, protocol, length, unit = struct.unpack(">HHHB", self.receive(sock, 7))
            if (tid, protocol, unit) != (
                self.transaction,
                0,
                self.unit,
            ) or not 2 <= length <= 254:
                raise ValueError("Invalid Modbus MBAP response")
            response = self.receive(sock, length - 1)
        if response[0] == pdu[0] | 0x80:
            raise ValueError("PLC exception code " + str(response[1]))
        if response[0] != pdu[0]:
            raise ValueError("Unexpected PLC function response")
        return response

    def read(self, point):
        address, count = point_spec(point)
        register = point.get("register", "holding")
        if register not in {"holding", "input"}:
            raise ValueError("Supported register banks: holding or input")
        response = self.request(
            struct.pack(">BHH", 3 if register == "holding" else 4, address, count)
        )
        if len(response) != 2 + count * 2 or response[1] != count * 2:
            raise ValueError("Invalid register byte count")
        return decode_registers(response[2:], point)

    def write(self, point, value):
        if point.get("register", "holding") != "holding":
            raise ValueError("Only explicit holding-register mappings are writable")
        address, count = point_spec(point)
        raw = encode_registers(value, point)
        response = self.request(
            struct.pack(">BHHB", 16, address, count, len(raw)) + raw
        )
        if response != struct.pack(">BHH", 16, address, count):
            raise ValueError("PLC write acknowledgement mismatch")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Gateway API redirects are not accepted")


class BeamAPI:
    def __init__(self, url, token):
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Explicit BEAM origin URL required")
        if parsed.scheme == "http" and parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError("Use HTTPS for a remote BEAM server")
        if not token:
            raise ValueError("Set the BEAM_INTEGRATION_TOKEN environment variable")
        self.url = url.rstrip("/")
        self.token = token
        self.client = urllib.request.build_opener(
            NoRedirect, urllib.request.ProxyHandler({})
        )

    def call(self, path, payload=None):
        raw = (
            json.dumps(payload, allow_nan=False).encode()
            if payload is not None
            else None
        )
        request = urllib.request.Request(
            self.url + path,
            data=raw,
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with self.client.open(request, timeout=5) as response:
                return json.loads(response.read(1_000_000))
        except urllib.error.HTTPError as exc:
            raise ValueError(f"BEAM HTTP {exc.code}; inspect server audit") from None


def sample(plc, points, scope):
    required = (
        {"power_kw"}
        if scope == "facility"
        else {"power_kw", "temp_c", "humidity", "airflow_m3h"}
    )
    if not required.issubset(points):
        raise ValueError("Missing telemetry mapping for " + scope)
    values = {key: plc.read(point) for key, point in points.items()}
    return {
        "scope": scope,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "MODBUS_TCP_REGISTER_MAP",
        **values,
    }


def apply_room(plc, mapping, target, expires_at, apply=False):
    if not apply:
        return False, None, "Telemetry-only mode; writes disabled"
    if mapping.get("commissioned") is not True or not mapping.get(
        "commissioning_reference"
    ):
        return False, None, "Room mapping has no commissioning reference"
    if not target.get("sensor_fresh"):
        return False, None, "No fresh room telemetry"
    outputs = mapping.get("targets", {})
    required = {"target_temp_c", "target_humidity", "target_airflow_m3h"}
    if set(outputs) != required:
        raise ValueError("Map all three target setpoints")
    # Validate the entire batch before the first write; overlapping addresses are rejected.
    addresses = set()
    for key, point in outputs.items():
        address, count = point_spec(point)
        if point.get("register", "holding") != "holding":
            raise ValueError("Writable points must be holding registers")
        occupied = set(range(address, address + count))
        if addresses & occupied:
            raise ValueError("Overlapping output registers")
        addresses |= occupied
        encode_registers(target[key], point)
    interlock = mapping.get("write_enable")
    if not interlock:
        return False, None, "No local PLC write-enable interlock mapped"
    ia, ic = point_spec(interlock)
    if interlock.get("register", "holding") == "holding" and addresses & set(
        range(ia, ia + ic)
    ):
        raise ValueError("Output cannot overlap the local interlock")
    expiry = datetime.fromisoformat(expires_at)
    if expiry.tzinfo is None:
        raise ValueError("Target expiry timezone required")
    for key, point in outputs.items():
        if datetime.now(timezone.utc) >= expiry:
            return False, None, "Proposal expired; PLC retains last values"
        if plc.read(interlock) != 1:
            return False, None, "Local PLC interlock blocks writes"
        plc.write(point, target[key])
    feedback = {key: plc.read(point) for key, point in outputs.items()}
    for key in outputs:
        tolerance = (
            0.5
            if key == "target_temp_c"
            else 1 if key == "target_humidity" else max(1, target[key] * 0.03)
        )
        if abs(feedback[key] - target[key]) > tolerance:
            return False, feedback, "Read-back mismatch; PLC intervention required"
    return (
        True,
        feedback,
        "Modbus write acknowledged; all setpoints read back within tolerance",
    )


def cycle(api, plc, config, apply=False):
    state = api.call("/api/integrations/targets")
    if state.get("contract") != "beam-gateway-v11" or state["mode"] != "CONNECTED":
        raise ValueError("Matched v11 backend in CONNECTED mode required")
    if config.get("facility"):
        api.call(
            "/api/integrations/telemetry", sample(plc, config["facility"], "facility")
        )
    for mapping in config.get("rooms", []):
        rid = mapping["room_id"]
        api.call("/api/integrations/telemetry", sample(plc, mapping["telemetry"], rid))
        # Fetch after telemetry, one proposal per room to keep the 15-second lease useful.
        proposal = api.call("/api/integrations/targets")
        target = next((r for r in proposal["rooms"] if r["room_id"] == rid), None)
        if not target:
            raise ValueError("Mapped room is not in BEAM conditioned rooms")
        try:
            applied, feedback, detail = apply_room(
                plc, mapping, target, proposal["expires_at"], apply
            )
        except (ValueError, OSError, struct.error) as exc:
            applied, feedback, detail = (
                False,
                None,
                "Gateway stopped the batch: " + str(exc),
            )
        api.call(
            "/api/integrations/actuation",
            {
                "proposal_id": proposal["proposal_id"],
                "revision": proposal["revision"],
                "room_id": rid,
                "applied": applied,
                "feedback": feedback,
                "detail": detail,
            },
        )
        print(
            json.dumps(
                {"room_id": rid, "applied": applied, "detail": detail},
                ensure_ascii=False,
            ),
            flush=True,
        )
    for mapping in config.get("device_hours", []):
        api.call(
            "/api/integrations/device-hours",
            {
                "device_id": mapping["device_id"],
                "runtime_hours": plc.read(mapping["point"]),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "MODBUS_TCP_LIFETIME_COUNTER",
            },
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write only commissioned room mappings with local PLC interlocks",
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    api = BeamAPI(config["beam_url"], os.environ.get("BEAM_INTEGRATION_TOKEN", ""))
    plc = ModbusTCP(config["plc"])
    interval = finite(config.get("poll_seconds", 5))
    if not 1 <= interval <= 60:
        raise ValueError("Polling interval must be 1..60 seconds")
    while True:
        try:
            cycle(api, plc, config, args.apply)
        except (ValueError, OSError, struct.error) as exc:
            print(
                json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
                flush=True,
            )
            if args.once:
                raise SystemExit(1)
        if args.once:
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
