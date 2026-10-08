"""Small, dependency-free ViewMarq Modbus TCP client. Python 3.10+."""
import argparse
import base64
from contextlib import contextmanager
import json
from pathlib import Path
import re
import socket
import struct
import sys
import time


class ProtocolError(RuntimeError):
    pass


def dimensions(model):
    found = re.match(r"MD4-(01|02|04)(12|24)", model)
    if not found:
        raise ValueError(f"Unverified display geometry for {model}; supported MD4 1/2/4-row, 12/24-character models")
    return int(found[1]), int(found[2])


FONTS = {"standard": (1, 5, 8), "compact": (0, 5, 7), "large": (4, 10, 14), "tall": (5, 10, 16)}


def layout(model, font="standard"):
    physical_rows, physical_columns = dimensions(model)
    code, width, height = FONTS[font]
    pixel_width, pixel_height = physical_columns * 6, physical_rows * 8
    if height > pixel_height:
        raise ValueError("This font is taller than the display")
    return {"rows": pixel_height // height, "columns": pixel_width // (width + 1),
            "pixel_width": pixel_width, "pixel_height": pixel_height,
            "font_code": code, "cell_width": width + 1, "cell_height": height}


def page_message(text, display_id, model, color="green", font="standard", alignment="center"):
    geometry = layout(model, font)
    rows, columns = geometry["rows"], geometry["columns"]
    lines = text.split("\n")
    if len(lines) > rows or any(len(line) > columns for line in lines):
        raise ValueError("Page does not fit the display")
    colors = {"green": "GRN", "red": "RED", "amber": "AMB"}
    line_colors = [color] * len(lines) if isinstance(color, str) else list(color)
    if len(line_colors) != len(lines) or any(c not in colors for c in line_colors) or not 1 <= display_id <= 247:
        raise ValueError("Invalid page color or display ID")
    # Chapter 5: back apostrophe (ASCII 0x60) displays the degree glyph.
    lines = [line.replace("°", chr(96)) for line in lines]
    if any(any(ord(c) < 32 or ord(c) > 126 or c in "<>" for c in line) for line in lines):
        raise ValueError("Unsupported display character")
    if alignment not in ("left", "center", "right"):
        raise ValueError("Invalid alignment")
    command = f"<ID {display_id}><CLR><WIN 0 0 {geometry['pixel_width'] - 1} {geometry['pixel_height'] - 1}><LJ><CS {geometry['font_code']}>"
    first_row = max(0, (rows - len(lines)) // 2)
    for index, line in enumerate(lines):
        row = index + first_row
        spare = max(0, geometry["pixel_width"] - len(line) * geometry["cell_width"])
        x = 0 if alignment == "left" else spare if alignment == "right" else spare // 2
        command += f"<{colors[line_colors[index]]}><POS {x} {row * geometry['cell_height']}><T>{line}</T>"
    payload = (command + "\r").encode("ascii")
    if len(payload) > 246:
        raise ValueError("Page exceeds single Modbus transaction size")
    return payload


def registers(data, order):
    data += b"\0" * (len(data) % 2)
    return [int.from_bytes(data[i:i + 2], order) for i in range(0, len(data), 2)]


def string(words, order):
    return b"".join(w.to_bytes(2, order) for w in words).split(b"\0", 1)[0].decode("ascii", errors="replace").strip()


def message(text, display_id, color="green", scroll="static", speed="medium", font="compact"):
    if not isinstance(text, str) or not text or len(text) > 200:
        raise ValueError("Message must contain 1 to 200 characters")
    if any(ord(c) < 32 or ord(c) > 126 or c in "<>" for c in text):
        raise ValueError("Use printable ASCII text without < or > (no embedded commands)")
    if type(display_id) is not int or not 1 <= display_id <= 247:
        raise ValueError("display_id must be 1..247; broadcast is not supported")
    colors = {"green": "GRN", "red": "RED", "amber": "AMB"}
    effects = {"static": "", "left": "<SL>"}
    speeds = {"slow": "S", "medium": "M", "fast": "F"}
    if color not in colors or scroll not in effects or speed not in speeds:
        raise ValueError("Invalid color, scroll mode, or speed")
    effect = effects[scroll] + (f"<S {speeds[speed]}>" if scroll != "static" else "")
    result = f"<ID {display_id}><CLR><CS {FONTS[font][0]}><{colors[color]}>{effect}<T>{text}</T>\r".encode("ascii")
    if len(result) > 246:
        raise ValueError("Formatted message exceeds single Modbus write limit; shorten the text")
    return result


class Modbus:
    def __init__(self, sock, unit):
        self.sock, self.unit, self.transaction = sock, unit, 0

    def receive(self, size, deadline):
        result = bytearray()
        while len(result) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out receiving Modbus response")
            self.sock.settimeout(remaining)
            chunk = self.sock.recv(size - len(result))
            if not chunk:
                raise ProtocolError("Display closed the connection before a complete reply")
            result.extend(chunk)
        return bytes(result)

    def exchange(self, pdu):
        self.transaction = (self.transaction + 1) & 0xffff
        header = struct.pack(">HHHB", self.transaction, 0, len(pdu) + 1, self.unit)
        self.sock.settimeout(2)
        self.sock.sendall(header + pdu)
        deadline = time.monotonic() + 2
        tid, protocol, length, unit = struct.unpack(">HHHB", self.receive(7, deadline))
        if (tid, protocol, unit) != (self.transaction, 0, self.unit) or not 2 <= length <= 254:
            raise ProtocolError("Invalid Modbus response header")
        reply = self.receive(length - 1, deadline)
        if reply[0] == (pdu[0] | 0x80):
            raise ProtocolError(f"Modbus exception {reply[1] if len(reply) > 1 else 'missing'} for function {pdu[0]}")
        if reply[0] != pdu[0]:
            raise ProtocolError("Unexpected Modbus function")
        return reply

    def read(self, address, count):
        if not 1 <= count <= 125 or not 0 <= address <= 65536 - count:
            raise ValueError("Invalid read range")
        reply = self.exchange(struct.pack(">BHH", 3, address, count))
        if len(reply) != 2 + 2 * count or reply[1] != 2 * count:
            raise ProtocolError("Wrong register count in read response")
        return list(struct.unpack(f">{count}H", reply[2:]))

    def write(self, address, words):
        if not 1 <= len(words) <= 123 or not 0 <= address <= 65536 - len(words):
            raise ValueError("Message exceeds single Modbus write limit")
        prefix = struct.pack(">BHH", 16, address, len(words))
        reply = self.exchange(prefix + bytes([len(words) * 2]) + struct.pack(f">{len(words)}H", *words))
        if reply != prefix:
            raise ProtocolError("Write acknowledgement does not match request; outcome uncertain")


def inspect(client, register_base):
    words = client.read(445000 - register_base, 10)
    models = {order: string(words, order) for order in ("big", "little")}
    matches = [order for order, model in models.items() if re.fullmatch(r"MD\d-[A-Z0-9-]+", model)]
    if len(matches) != 1:
        raise ProtocolError(f"No unambiguous ViewMarq model at base {register_base}: {models}")
    settings = client.read(445108 - register_base, 5)
    if not 1 <= settings[4] <= 247:
        raise ProtocolError("Invalid ASCII display ID; verify register addressing")
    return {"register_base": register_base, "model": models[matches[0]],
            "model_byte_order": matches[0], "heartbeat_seconds": settings[0],
            "option_flags": settings[1], "byte_swap_strings": bool(settings[1] & 0x80),
            "display_id": settings[4]}


def wait_ready(client, address):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if client.read(address, 1)[0] == 0:
            return
        time.sleep(0.1)
    raise TimeoutError("Command buffer did not clear; check byte order, CR terminator, and other writers")


def send(client, config, text):
    # Validate before any writes. Never automatically try alternate write addresses/orders.
    if config.get("page_layout"):
        payload = page_message(text, config["display_id"], config["model"], config.get("color", "green"), config.get("font", "standard"), config.get("alignment", "center"))
    else:
        payload = message(text, config.get("display_id"), config.get("color", "green"), config.get("scroll", "static"), config.get("speed", "medium"), config.get("font", "compact"))
    order = config.get("byte_order")
    if order not in ("big", "little"):
        raise ValueError("Set byte_order to big or little after inspecting display settings")
    base = config["register_base"]
    identity = inspect(client, base)
    if identity["display_id"] != config["display_id"]:
        raise ProtocolError(f"Configured display_id differs from device: {identity['display_id']}")
    command = 411000 - base
    wait_ready(client, command)
    time.sleep(0.1)
    client.write(command, registers(payload, order))
    # A Modbus acknowledgement alone does not mean the display accepted its ASCII command.
    time.sleep(0.1)
    wait_ready(client, command)
    status = string(client.read(411500 - base, 32), order).strip("\r\n ")
    if status != "OK":
        raise ProtocolError(f"Display did not report OK: {status!r}; message may have been sent")
    return {"ok": True, "status": status, "model": identity["model"], "text": text}


@contextmanager
def exclusive(config_path):
    # Local guard, plus HA's queued script. Other PLCs/software must not write concurrently.
    lock = Path(str(config_path) + ".lock")
    try:
        handle = lock.open("x")
    except FileExistsError as error:
        raise RuntimeError(f"Another send is active (or stale lock): {lock}") from error
    try:
        handle.close()
        yield
    finally:
        lock.unlink()


def load_config(path):
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    if not isinstance(config.get("host"), str) or not config["host"].strip():
        raise ValueError("Set host in the configuration to the display's actual IP or hostname")
    for key, low, high in (("port", 1, 65535), ("unit_id", 0, 255)):
        if type(config.get(key)) is not int or not low <= config[key] <= high:
            raise ValueError(f"{key} must be {low}..{high}")
    if config.get("register_base") not in (400000, 400001):
        raise ValueError("register_base must be 400000 or 400001")
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--probe", action="store_true", help="Read identity at both possible address bases; no writes")
    actions.add_argument("--text")
    actions.add_argument("--message-b64", help="Base64 UTF-8 text for Home Assistant")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.probe:
            results = []
            for base in (400001, 400000):
                try:
                    with socket.create_connection((config["host"], config["port"]), timeout=2) as sock:
                        results.append(inspect(Modbus(sock, config["unit_id"]), base))
                except (OSError, ProtocolError) as error:
                    results.append({"register_base": base, "error": str(error)})
            print(json.dumps({"probe": results}))
            return 0 if sum("model" in item for item in results) == 1 else 1
        text = args.text if args.text is not None else base64.b64decode(args.message_b64, validate=True).decode("utf-8")
        message(text, config.get("display_id"))
        with exclusive(args.config.resolve()):
            with socket.create_connection((config["host"], config["port"]), timeout=2) as sock:
                result = send(Modbus(sock, config["unit_id"]), config, text)
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
