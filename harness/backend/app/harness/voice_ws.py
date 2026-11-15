"""A minimal RFC 6455 client for VoiceStudio's streaming recogniser.

The speech service exposes ``WS /v1/audio/transcriptions/stream``. It is a
loopback service, and it refuses WebSocket upgrades carrying a browser
``Origin`` (403) while accepting a native client with none (101). The harness
is that native client, so it needs its own socket framing. ``httpx`` cannot
upgrade and adding ``websockets`` for one call would add a dependency to the
shipped bundle, so this module owns the ~180 lines it actually needs.

Scope is deliberately narrow -- only ``voicestudio.speech.v1``:

* client side only, one unfragmented frame per send;
* reassembly of fragmented incoming messages;
* ping/pong and close handshakes;
* a per-receive timeout surfacing as ``None`` (idle), never an exception,
  because "the recogniser went quiet" is a normal turn boundary.

No permessage-deflate, no subprotocol negotiation, no server role. The framing
was validated against VoiceStudio 0.5.6 in the DDSA voice slice before being
moved here; this is the same client with the slice-specific discovery removed.
"""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import struct
from typing import Optional, Union
from urllib.parse import urlsplit

GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
OP_CONT, OP_TEXT, OP_BINARY = 0x0, 0x1, 0x2
OP_CLOSE, OP_PING, OP_PONG = 0x8, 0x9, 0xA


class WebSocketError(RuntimeError):
    """The peer broke the protocol, or refused the handshake."""


def _mask(payload: bytes, key: bytes) -> bytes:
    if not payload:
        return b''
    repeated = (key * (len(payload) // 4 + 1))[:len(payload)]
    return bytes(a ^ b for a, b in zip(payload, repeated))


class WebSocket:
    """One open connection. Not thread-safe; drive it from a single thread."""

    def __init__(self, sock: socket.socket, response_headers: dict[str, str]):
        self._sock = sock
        self.headers = response_headers
        self.closed = False
        self._fragments: list[bytes] = []
        self._fragment_opcode = 0

    def _read_exact(self, count: int) -> bytes:
        chunks, remaining = [], count
        while remaining > 0:
            chunk = self._sock.recv(remaining)
            if not chunk:
                raise WebSocketError('connection closed mid-frame')
            chunks.append(chunk)
            remaining -= len(chunk)
        return b''.join(chunks)

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if self.closed:
            raise WebSocketError('send on a closed socket')
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack('!H', length)
        else:
            header.append(0x80 | 127)
            header += struct.pack('!Q', length)
        key = os.urandom(4)
        header += key
        self._sock.sendall(bytes(header) + _mask(payload, key))

    def send_bytes(self, data: bytes) -> None:
        self._send_frame(OP_BINARY, data)

    def send_text(self, text: str) -> None:
        self._send_frame(OP_TEXT, text.encode('utf-8'))

    def recv(self, timeout: Optional[float] = None) -> Union[bytes, str, None]:
        """Next complete message, or ``None`` when the peer goes quiet.

        A genuine close returns ``None`` once and marks the socket closed, so a
        caller cannot mistake silence for a transcript.
        """
        if self.closed:
            return None
        previous = self._sock.gettimeout()
        if timeout is not None:
            self._sock.settimeout(timeout)
        try:
            while True:
                try:
                    first = self._read_exact(2)
                except (socket.timeout, TimeoutError):
                    return None
                fin = bool(first[0] & 0x80)
                opcode = first[0] & 0x0F
                masked = bool(first[1] & 0x80)
                length = first[1] & 0x7F
                if length == 126:
                    length = struct.unpack('!H', self._read_exact(2))[0]
                elif length == 127:
                    length = struct.unpack('!Q', self._read_exact(8))[0]
                key = self._read_exact(4) if masked else b''
                payload = self._read_exact(length) if length else b''
                if masked:
                    payload = _mask(payload, key)

                if opcode == OP_PING:
                    self._send_frame(OP_PONG, payload)
                    continue
                if opcode == OP_PONG:
                    continue
                if opcode == OP_CLOSE:
                    self._send_frame(OP_CLOSE, payload[:2])
                    self.close()
                    return None

                if opcode == OP_CONT:
                    self._fragments.append(payload)
                    if not fin:
                        continue
                    data = b''.join(self._fragments)
                    complete_opcode = self._fragment_opcode
                    self._fragments, self._fragment_opcode = [], 0
                    return (data.decode('utf-8', 'replace')
                            if complete_opcode == OP_TEXT else data)
                if not fin:
                    self._fragments = [payload]
                    self._fragment_opcode = opcode
                    continue
                return (payload.decode('utf-8', 'replace')
                        if opcode == OP_TEXT else payload)
        finally:
            if timeout is not None and not self.closed:
                self._sock.settimeout(previous)

    def close(self) -> None:
        if self.closed:
            return
        try:
            self._send_frame(OP_CLOSE, b'\x03\xe8')
        except OSError:
            pass
        self.closed = True
        try:
            self._sock.close()
        except OSError:
            pass

    def __enter__(self) -> WebSocket:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def connect(url: str, timeout: float = 5.0,
            extra_headers: Optional[dict[str, str]] = None) -> WebSocket:
    """Open ``ws://host:port/path?query``. No ``Origin`` header, on purpose.

    A browser-origin WebSocket upgrade is refused by VoiceStudio (403 vs 101).
    This process is not a browser, so omitting the header is correct rather
    than a workaround.
    """
    parts = urlsplit(url)
    if parts.scheme not in ('ws', 'http'):
        raise WebSocketError(f'unsupported scheme for a plain socket: {parts.scheme}')
    host = parts.hostname or '127.0.0.1'
    port = parts.port or 80
    path = parts.path or '/'
    if parts.query:
        path += '?' + parts.query

    sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(timeout)
    key = base64.b64encode(os.urandom(16)).decode('ascii')
    lines = [
        f'GET {path} HTTP/1.1',
        f'Host: {host}:{port}',
        'Upgrade: websocket',
        'Connection: Upgrade',
        f'Sec-WebSocket-Key: {key}',
        'Sec-WebSocket-Version: 13',
    ]
    for name, value in (extra_headers or {}).items():
        lines.append(f'{name}: {value}')
    sock.sendall(('\r\n'.join(lines) + '\r\n\r\n').encode('ascii'))

    head = b''
    while b'\r\n\r\n' not in head:
        chunk = sock.recv(1)
        if not chunk:
            sock.close()
            raise WebSocketError('server closed during the handshake')
        head += chunk
        if len(head) > 16384:
            sock.close()
            raise WebSocketError('handshake response too large')
    text = head.decode('latin-1')
    status_line = text.split('\r\n', 1)[0]
    if ' 101 ' not in status_line + ' ':
        sock.close()
        raise WebSocketError(f'handshake refused: {status_line}')
    headers: dict[str, str] = {}
    for line in text.split('\r\n')[1:]:
        if ':' in line:
            name, value = line.split(':', 1)
            headers[name.strip().lower()] = value.strip()
    expected = base64.b64encode(
        hashlib.sha1((key + GUID).encode('ascii')).digest()).decode('ascii')
    if headers.get('sec-websocket-accept') != expected:
        sock.close()
        raise WebSocketError('Sec-WebSocket-Accept mismatch')
    sock.settimeout(None)
    return WebSocket(sock, headers)
