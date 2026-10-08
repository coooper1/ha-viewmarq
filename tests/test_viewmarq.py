import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

from custom_components.viewmarq import protocol as vm


class Display:
    """Independent wire-level fixture; binds only to loopback, never a real display."""
    def __init__(self, base=400001, order="big", status=b"OK\r", corrupt=False):
        self.base, self.order, self.status, self.corrupt = base, order, status, corrupt
        self.writes, self.errors = [], []
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        self.sock = socket.create_connection(self.server.getsockname(), timeout=2)
        return self

    def __exit__(self, *args):
        self.sock.close()
        self.thread.join(3)
        self.server.close()
        if self.thread.is_alive() or self.errors:
            raise AssertionError(f"Fixture failure: {self.errors}")

    @staticmethod
    def receive(sock, size):
        result = b""
        while len(result) < size:
            chunk = sock.recv(size - len(result))
            if not chunk:
                raise EOFError
            result += chunk
        return result

    def text_words(self, text, count):
        data = text.ljust(count * 2, b"\0")
        return [int.from_bytes(data[i:i+2], self.order) for i in range(0, count * 2, 2)]

    def run(self):
        try:
            connection, _ = self.server.accept()
            with connection:
                connection.settimeout(3)
                while True:
                    tid, proto, length, unit = struct.unpack(">HHHB", self.receive(connection, 7))
                    pdu = self.receive(connection, length - 1)
                    function, address, count = struct.unpack(">BHH", pdu[:5])
                    if proto != 0 or unit != 1:
                        raise AssertionError("Bad request header")
                    documented = address + self.base
                    if function == 3:
                        if documented == 445000:
                            values = self.text_words(b"MD4-0112T-1", count)
                        elif documented == 445108:
                            values = [0, 0x80 if self.order == "little" else 0, 502, 60, 7]
                        elif documented == 411000:
                            values = [0]
                        elif documented == 411500:
                            values = self.text_words(self.status, count)
                        else:
                            values = None
                        reply = b"\x83\x02" if values is None else bytes([3, count * 2]) + struct.pack(f">{count}H", *values)
                    elif function == 16:
                        if documented != 411000 or pdu[5] != count * 2 or len(pdu) != 6 + count * 2:
                            raise AssertionError("Bad write request")
                        values = struct.unpack(f">{count}H", pdu[6:])
                        self.writes.append(b"".join(v.to_bytes(2, self.order) for v in values))
                        reply = pdu[:5]
                    else:
                        raise AssertionError(f"Unexpected function {function}")
                    packet = struct.pack(">HHHB", tid + int(self.corrupt), 0, len(reply) + 1, unit) + reply
                    # Fragment the response to exercise real TCP framing.
                    connection.sendall(packet[:4])
                    connection.sendall(packet[4:])
        except (EOFError, ConnectionResetError):
            pass
        except Exception as error:
            self.errors.append(repr(error))


class ProtocolTests(unittest.TestCase):
    def test_known_message_and_register_vector(self):
        self.assertEqual(vm.message("Hi", 1), b"<ID 1><CLR><CS 0><GRN><T>Hi</T>\r")
        self.assertEqual(vm.registers(b"<ID 1>\r", "big"), [0x3c49, 0x4420, 0x313e, 0x0d00])
        self.assertEqual(vm.registers(b"<ID 1>\r", "little"), [0x493c, 0x2044, 0x3e31, 0x000d])

    def test_input_restrictions(self):
        for text in ("", "a" * 201, "x\r", "x\n", "<CLR>", "café"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                vm.message(text, 1)
        with self.assertRaises(ValueError):
            vm.message("hello", 0)

    def test_probe_has_no_writes(self):
        for base in (400000, 400001):
            for order in ("big", "little"):
                with self.subTest(base=base, order=order), Display(base, order) as display:
                    result = vm.inspect(vm.Modbus(display.sock, 1), base)
                    self.assertEqual(result["model"], "MD4-0112T-1")
                    self.assertEqual(result["display_id"], 7)
                    self.assertEqual(result["model_byte_order"], order)
                    self.assertEqual(display.writes, [])

    def test_complete_send_each_mapping_and_order(self):
        for base in (400000, 400001):
            for order in ("big", "little"):
                with self.subTest(base=base, order=order), Display(base, order) as display:
                    result = vm.send(vm.Modbus(display.sock, 1), {"register_base": base, "byte_order": order, "display_id": 7}, "Hello HA")
                    self.assertTrue(result["ok"])
                    self.assertEqual(len(display.writes), 1)
                    self.assertEqual(display.writes[0].rstrip(b"\0"), b"<ID 7><CLR><CS 0><GRN><T>Hello HA</T>\r")

    def test_display_error_is_not_success(self):
        with Display(status=b"E6\r") as display, self.assertRaisesRegex(vm.ProtocolError, "E6"):
            vm.send(vm.Modbus(display.sock, 1), {"register_base": 400001, "byte_order": "big", "display_id": 7}, "Hi")
        self.assertEqual(len(display.writes), 1)  # Do not retry an uncertain write.

    def test_wrong_identity_prevents_write(self):
        with Display() as display, self.assertRaisesRegex(vm.ProtocolError, "display_id"):
            vm.send(vm.Modbus(display.sock, 1), {"register_base": 400001, "byte_order": "big", "display_id": 1}, "Hi")
        self.assertEqual(display.writes, [])

    def test_exception_and_mismatched_transaction(self):
        with Display() as display, self.assertRaisesRegex(vm.ProtocolError, "exception 2"):
            vm.Modbus(display.sock, 1).read(1, 1)
        with Display(corrupt=True) as display, self.assertRaisesRegex(vm.ProtocolError, "header"):
            vm.Modbus(display.sock, 1).read(44999, 10)

    def test_command_buffer_timeout(self):
        client = unittest.mock.Mock()
        client.read.return_value = [123]
        with patch.object(vm.time, "monotonic", side_effect=[0, 0, 6]), patch.object(vm.time, "sleep"), self.assertRaises(TimeoutError):
            vm.wait_ready(client, 10999)

    def test_local_lock_and_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            with vm.exclusive(path):
                with self.assertRaises(RuntimeError):
                    with vm.exclusive(path):
                        pass
            self.assertFalse(Path(str(path) + ".lock").exists())

    def test_missing_host_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps({"host": None}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "host"):
                vm.load_config(path)

    def test_maximum_text_stays_within_one_write(self):
        self.assertLessEqual(len(vm.registers(vm.message("a" * 200, 247), "big")), 123)


if __name__ == "__main__":
    unittest.main()
