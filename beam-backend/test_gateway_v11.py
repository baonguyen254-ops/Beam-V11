"""Gateway protocol tests use a localhost fake PLC, never hospital hardware."""

import socketserver
import struct
import sys
import threading
from datetime import timedelta
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from gateway_modbus import ModbusTCP, decode_registers, encode_registers, apply_room
from test_v10 import NOW


@pytest.mark.parametrize(
    "kind,value",
    [("uint16", 123), ("int16", -21), ("uint32", 100000), ("float32", 23.75)],
)
@pytest.mark.parametrize("order", ["big", "little"])
def test_register_codec(kind, value, order):
    p = {
        "address": 0,
        "type": kind,
        "word_order": order,
        "byte_order": order,
        "min": -1000,
        "max": 1e9,
    }
    assert decode_registers(encode_registers(value, p), p) == pytest.approx(value)


class FakeHandler(socketserver.BaseRequestHandler):
    def handle(self):
        header = ModbusTCP.receive(self.request, 7)
        tid, _, length, unit = struct.unpack(">HHHB", header)
        pdu = ModbusTCP.receive(self.request, length - 1)
        fn, address, count = struct.unpack(">BHH", pdu[:5])
        registers = self.server.registers
        if fn in {3, 4}:
            response = bytes([fn, count * 2]) + b"".join(
                struct.pack(">H", registers.get(address + i, 0)) for i in range(count)
            )
        elif fn == 16:
            for i in range(count):
                registers[address + i] = struct.unpack(
                    ">H", pdu[6 + i * 2 : 8 + i * 2]
                )[0]
            response = pdu[:5]
        else:
            response = bytes([fn | 128, 1])
        self.request.sendall(
            struct.pack(">HHHB", tid, 0, len(response) + 1, unit) + response
        )


def test_modbus_tcp_write_readback_and_interlocks():
    with socketserver.TCPServer(("127.0.0.1", 0), FakeHandler) as server:
        server.registers = {0: 1}
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            plc = ModbusTCP({"host": "127.0.0.1", "port": server.server_address[1]})
            outputs = {
                k: {"address": 10 + i * 2, "type": "float32", "min": 0, "max": maximum}
                for i, (k, maximum) in enumerate(
                    (
                        ("target_temp_c", 30),
                        ("target_humidity", 100),
                        ("target_airflow_m3h", 10000),
                    )
                )
            }
            mapping = {
                "commissioned": True,
                "commissioning_reference": "FAKE PLC TEST ONLY",
                "write_enable": {"address": 0, "type": "uint16"},
                "targets": outputs,
            }
            target = {
                "target_temp_c": 21,
                "target_humidity": 45,
                "target_airflow_m3h": 2200,
                "sensor_fresh": True,
            }
            expiry = (NOW() + timedelta(seconds=15)).isoformat()
            assert not apply_room(plc, mapping, target, expiry)[0]
            assert server.registers == {0: 1}
            applied, feedback, _ = apply_room(plc, mapping, target, expiry, True)
            assert applied and feedback["target_temp_c"] == 21
            server.registers[0] = 0
            assert not apply_room(
                plc, mapping, {**target, "target_temp_c": 22}, expiry, True
            )[0]
            assert plc.read(outputs["target_temp_c"]) == 21
            server.registers[0] = 1
            with pytest.raises(ValueError):
                apply_room(
                    plc, mapping, {**target, "target_airflow_m3h": 20000}, expiry, True
                )
            assert plc.read(outputs["target_temp_c"]) == 21
            with pytest.raises(ValueError):
                apply_room(
                    plc,
                    {**mapping, "write_enable": outputs["target_temp_c"]},
                    target,
                    expiry,
                    True,
                )
            assert not apply_room(
                plc, mapping, target, (NOW() - timedelta(seconds=1)).isoformat(), True
            )[0]
        finally:
            server.shutdown()
            worker.join(timeout=2)
