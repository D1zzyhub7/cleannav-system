"""Loopback-only CNVG datagram replay and fault-injection helpers."""

from __future__ import annotations

import ipaddress
import socket
import time
import zlib
from typing import Iterable

from .protocol import CRC, HEADER, MAGIC, MAX_DATAGRAM_BYTES


FORBIDDEN_LEGACY_PORTS = {4500, 4501, 6667}


def parse_datagram_blob(blob: bytes) -> list[bytes]:
    """Read a raw datagram, concatenated CNVG datagrams, or uint16-BE frames."""
    if not blob:
        raise ValueError('input contains no datagrams')
    if blob.startswith(MAGIC):
        result = []
        offset = 0
        while offset < len(blob):
            if len(blob) - offset < HEADER.size:
                raise ValueError('truncated CNVG header in concatenated input')
            payload_len = int.from_bytes(blob[offset + 20:offset + 22], 'big')
            size = HEADER.size + payload_len + CRC.size
            if size > MAX_DATAGRAM_BYTES or offset + size > len(blob):
                raise ValueError('invalid CNVG datagram boundary')
            result.append(blob[offset:offset + size])
            offset += size
            if offset < len(blob) and not blob[offset:].startswith(MAGIC):
                raise ValueError('trailing bytes after CNVG datagram')
        return result

    result = []
    offset = 0
    while offset < len(blob):
        if len(blob) - offset < 2:
            raise ValueError('truncated uint16-BE frame prefix')
        size = int.from_bytes(blob[offset:offset + 2], 'big')
        offset += 2
        if size < HEADER.size + CRC.size or size > MAX_DATAGRAM_BYTES:
            raise ValueError('framed datagram size is outside CNVG bounds')
        if offset + size > len(blob):
            raise ValueError('truncated framed datagram')
        result.append(blob[offset:offset + size])
        offset += size
    return result


def mutate_session_id(datagram: bytes, session_id: int) -> bytes:
    """Replace payload session_id and reseal CRC; session_id is first payload field."""
    if not 0 <= session_id <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError('session_id must be uint64')
    if len(datagram) < HEADER.size + 8 + CRC.size:
        raise ValueError('packet has no complete session_id field')
    payload_len = int.from_bytes(datagram[20:22], 'big')
    if payload_len < 8 or len(datagram) != HEADER.size + payload_len + CRC.size:
        raise ValueError('packet framing does not contain a session_id')
    changed = bytearray(datagram)
    changed[HEADER.size:HEADER.size + 8] = session_id.to_bytes(8, 'big')
    changed[-CRC.size:] = (zlib.crc32(changed[:-CRC.size]) & 0xFFFFFFFF).to_bytes(4, 'big')
    return bytes(changed)


def replay_datagrams(
    datagrams: Iterable[bytes],
    *,
    target_ip: str = '127.0.0.1',
    target_port: int,
    duplicate: bool = False,
    out_of_order: bool = False,
    corrupt_byte: int | None = None,
    delay_ms: int = 0,
    stale_session_id: int | None = None,
) -> int:
    """Send transformed CNVG packets to IPv4 localhost only; return sends count."""
    try:
        address = ipaddress.ip_address(target_ip)
    except ValueError as exc:
        raise ValueError('replay target must be exactly 127.0.0.1') from exc
    if not address.is_loopback or str(address) != '127.0.0.1':
        raise ValueError('replay target must be exactly 127.0.0.1')
    if not 1 <= target_port <= 65535 or target_port in FORBIDDEN_LEGACY_PORTS:
        raise ValueError('invalid or reserved legacy IVCU UDP port')
    if delay_ms < 0:
        raise ValueError('delay_ms cannot be negative')

    packets = list(datagrams)
    if not packets:
        raise ValueError('no datagrams to replay')
    if any(not packet or len(packet) > MAX_DATAGRAM_BYTES for packet in packets):
        raise ValueError('each datagram must contain 1..512 bytes')
    if stale_session_id is not None:
        packets = [mutate_session_id(packet, stale_session_id) for packet in packets]
    if corrupt_byte is not None:
        changed = bytearray(packets[0])
        if not 0 <= corrupt_byte < len(changed):
            raise ValueError('corrupt byte offset is outside first datagram')
        changed[corrupt_byte] ^= 0x01
        packets[0] = bytes(changed)
    if out_of_order:
        packets.reverse()
    if duplicate:
        packets = [packet for packet in packets for _ in (0, 1)]

    sent = 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        for index, packet in enumerate(packets):
            udp.sendto(packet, ('127.0.0.1', target_port))
            sent += 1
            if delay_ms and index + 1 < len(packets):
                time.sleep(delay_ms / 1000.0)
    return sent
