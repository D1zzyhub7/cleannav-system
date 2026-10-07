"""Versioned, ABI-independent UDP wire format for NET-OFFLINE-V1.

All integer and floating-point fields use network byte order (big endian).
The trailing CRC-32 covers the complete fixed header followed by the payload.
The CRC field itself is not part of that input because it is stored after the
covered bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import math
import struct
import time
import zlib


MAGIC = b'CNVG'
VERSION = 1
SEMANTIC_REVISION = '1.1'
MAX_DATAGRAM_BYTES = 512
MAX_PAYLOAD_BYTES = MAX_DATAGRAM_BYTES - 24 - 4

# magic, version, type, flags, sequence, Unix timestamp ms, payload length,
# reserved. This is exactly 24 bytes; CRC32 is appended after payload.
HEADER = struct.Struct('!4sBBHIQHH')
CRC = struct.Struct('!I')


class MessageType(IntEnum):
    HELLO = 1
    HEARTBEAT = 2
    CONTROL_COMMAND = 3
    VEHICLE_STATE = 4
    GATEWAY_STATUS = 5


class PeerRole(IntEnum):
    J6M_GATEWAY = 1
    AUTOWARE_PC = 2
    AUTOWARE_MOCK = 2


class ControlMode(IntEnum):
    TWIST_RAW = 0
    ACKERMANN = 1


class Gear(IntEnum):
    UNSPECIFIED = 0
    PARK = 1
    REVERSE = 2
    NEUTRAL = 3
    DRIVE = 4
    LOW = 5


class VehicleMode(IntEnum):
    UNKNOWN = 0
    MANUAL = 1
    AUTONOMOUS = 2
    ESTOP = 3
    FAULT = 4


class GatewayState(IntEnum):
    DISCONNECTED = 0
    WAITING = 1
    ACTIVE = 2
    STALE = 3
    FAULT = 4
    ESTOP = 5


class ProtocolError(ValueError):
    """Raised when a datagram does not conform to NET-OFFLINE-V1."""


@dataclass(frozen=True)
class Packet:
    message_type: MessageType
    sequence: int
    timestamp_ms: int
    payload: bytes


@dataclass(frozen=True)
class Hello:
    session_id: int
    role: PeerRole
    owner_id: str


@dataclass(frozen=True)
class Heartbeat:
    session_id: int
    owner_id: str


@dataclass(frozen=True)
class ControlCommand:
    session_id: int
    owner_id: str
    enable: bool
    emergency_stop: bool
    mode: ControlMode
    gear: Gear
    validity_ms: int
    target_speed_mps: float
    target_yaw_rate_rps: float
    target_steering_rad: float


@dataclass(frozen=True)
class VehicleState:
    session_id: int
    owner_id: str
    speed_mps: float
    steering_rad: float
    gear: Gear
    vehicle_mode: VehicleMode
    emergency: bool
    gateway_alive: bool
    driver_alive: bool
    fault_code: int


@dataclass(frozen=True)
class GatewayStatus:
    session_id: int
    state: GatewayState
    last_rx_age_ms: int
    last_tx_age_ms: int
    rx_sequence: int
    tx_sequence: int
    dropped_packets: int
    malformed_packets: int
    stale_packets: int
    out_of_order_packets: int


PAYLOAD_STRUCTS = {
    MessageType.HELLO: struct.Struct('!QB16s'),
    MessageType.HEARTBEAT: struct.Struct('!Q16s'),
    MessageType.CONTROL_COMMAND: struct.Struct('!Q16sBBBbHfff'),
    MessageType.VEHICLE_STATE: struct.Struct('!Q16sffbBBBBI'),
    MessageType.GATEWAY_STATUS: struct.Struct('!QB8I'),
}


def unix_time_ms() -> int:
    """Return wall-clock milliseconds since Unix epoch for cross-host age checks."""
    return time.time_ns() // 1_000_000


def _validate_u32(value: int, field: str) -> int:
    if not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
        raise ProtocolError(f'{field} must be an unsigned 32-bit integer')
    return value


def _validate_u64(value: int, field: str) -> int:
    if not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise ProtocolError(f'{field} must be an unsigned 64-bit integer')
    return value


def _owner_bytes(owner_id: str) -> bytes:
    try:
        encoded = owner_id.encode('ascii')
    except (AttributeError, UnicodeEncodeError) as exc:
        raise ProtocolError('owner_id must be ASCII') from exc
    if not encoded or len(encoded) > 16 or b'\0' in encoded:
        raise ProtocolError('owner_id must contain 1..16 non-NUL ASCII bytes')
    return encoded.ljust(16, b'\0')


def _owner_string(raw: bytes) -> str:
    head, separator, tail = raw.partition(b'\0')
    if not separator and len(raw) != 16:
        raise ProtocolError('owner_id has invalid wire width')
    if separator and any(tail):
        raise ProtocolError('owner_id padding must be zero')
    try:
        value = head.decode('ascii')
    except UnicodeDecodeError as exc:
        raise ProtocolError('owner_id is not ASCII') from exc
    if not value:
        raise ProtocolError('owner_id cannot be empty')
    return value


def encode_payload(message: object) -> tuple[MessageType, bytes]:
    """Encode a typed payload without serializing any Python object layout."""
    try:
        if isinstance(message, Hello):
            payload = PAYLOAD_STRUCTS[MessageType.HELLO].pack(
                _validate_u64(message.session_id, 'session_id'),
                int(PeerRole(message.role)),
                _owner_bytes(message.owner_id),
            )
            return MessageType.HELLO, payload
        if isinstance(message, Heartbeat):
            payload = PAYLOAD_STRUCTS[MessageType.HEARTBEAT].pack(
                _validate_u64(message.session_id, 'session_id'),
                _owner_bytes(message.owner_id),
            )
            return MessageType.HEARTBEAT, payload
        if isinstance(message, ControlCommand):
            values = (
                _validate_u64(message.session_id, 'session_id'),
                _owner_bytes(message.owner_id),
                int(bool(message.enable)),
                int(bool(message.emergency_stop)),
                int(ControlMode(message.mode)),
                int(Gear(message.gear)),
                int(message.validity_ms),
                float(message.target_speed_mps),
                float(message.target_yaw_rate_rps),
                float(message.target_steering_rad),
            )
            if not 1 <= values[6] <= 5000:
                raise ProtocolError('validity_ms must be in 1..5000')
            if not all(math.isfinite(value) for value in values[7:]):
                raise ProtocolError('control values must be finite')
            payload = PAYLOAD_STRUCTS[MessageType.CONTROL_COMMAND].pack(*values)
            return MessageType.CONTROL_COMMAND, payload
        if isinstance(message, VehicleState):
            floats = (float(message.speed_mps), float(message.steering_rad))
            if not all(math.isfinite(value) for value in floats):
                raise ProtocolError('vehicle state values must be finite')
            if not 0 <= message.fault_code <= 0xFFFFFFFF:
                raise ProtocolError('fault_code must be an unsigned 32-bit integer')
            payload = PAYLOAD_STRUCTS[MessageType.VEHICLE_STATE].pack(
                _validate_u64(message.session_id, 'session_id'),
                _owner_bytes(message.owner_id),
                *floats,
                int(Gear(message.gear)),
                int(VehicleMode(message.vehicle_mode)),
                int(bool(message.emergency)),
                int(bool(message.gateway_alive)),
                int(bool(message.driver_alive)),
                int(message.fault_code),
            )
            return MessageType.VEHICLE_STATE, payload
        if isinstance(message, GatewayStatus):
            counters = (
                message.last_rx_age_ms,
                message.last_tx_age_ms,
                message.rx_sequence,
                message.tx_sequence,
                message.dropped_packets,
                message.malformed_packets,
                message.stale_packets,
                message.out_of_order_packets,
            )
            if any(not 0 <= value <= 0xFFFFFFFF for value in counters):
                raise ProtocolError('gateway status counters must be uint32')
            payload = PAYLOAD_STRUCTS[MessageType.GATEWAY_STATUS].pack(
                _validate_u64(message.session_id, 'session_id'),
                int(GatewayState(message.state)),
                *counters,
            )
            return MessageType.GATEWAY_STATUS, payload
    except (OverflowError, struct.error, TypeError, ValueError) as exc:
        if isinstance(exc, ProtocolError):
            raise
        raise ProtocolError(f'invalid payload: {exc}') from exc
    raise ProtocolError(f'unsupported payload type: {type(message).__name__}')


def decode_payload(packet: Packet) -> object:
    """Decode a validated packet payload to its corresponding dataclass."""
    payload_struct = PAYLOAD_STRUCTS.get(packet.message_type)
    if payload_struct is None or len(packet.payload) != payload_struct.size:
        raise ProtocolError('wrong payload length for message type')
    try:
        values = payload_struct.unpack(packet.payload)
        if packet.message_type is MessageType.HELLO:
            session_id, role, owner = values
            return Hello(session_id, PeerRole(role), _owner_string(owner))
        if packet.message_type is MessageType.HEARTBEAT:
            session_id, owner = values
            return Heartbeat(session_id, _owner_string(owner))
        if packet.message_type is MessageType.CONTROL_COMMAND:
            (
                session_id, owner, enable, estop, mode, gear, validity,
                speed, yaw_rate, steering,
            ) = values
            if enable not in (0, 1) or estop not in (0, 1):
                raise ProtocolError('control booleans must be 0 or 1')
            if not 1 <= validity <= 5000:
                raise ProtocolError('validity_ms must be in 1..5000')
            if not all(math.isfinite(value) for value in (speed, yaw_rate, steering)):
                raise ProtocolError('control values must be finite')
            return ControlCommand(
                session_id, _owner_string(owner), bool(enable), bool(estop),
                ControlMode(mode), Gear(gear), validity, speed, yaw_rate, steering,
            )
        if packet.message_type is MessageType.VEHICLE_STATE:
            (
                session_id, owner, speed, steering, gear, vehicle_mode,
                emergency, gateway_alive, driver_alive, fault_code,
            ) = values
            flags = (emergency, gateway_alive, driver_alive)
            if any(value not in (0, 1) for value in flags):
                raise ProtocolError('vehicle state booleans must be 0 or 1')
            if not all(math.isfinite(value) for value in (speed, steering)):
                raise ProtocolError('vehicle state values must be finite')
            return VehicleState(
                session_id, _owner_string(owner), speed, steering,
                Gear(gear), VehicleMode(vehicle_mode), bool(emergency),
                bool(gateway_alive), bool(driver_alive), fault_code,
            )
        if packet.message_type is MessageType.GATEWAY_STATUS:
            session_id, state, *counters = values
            return GatewayStatus(session_id, GatewayState(state), *counters)
    except (ValueError, struct.error) as exc:
        if isinstance(exc, ProtocolError):
            raise
        raise ProtocolError(f'invalid payload enum or field: {exc}') from exc
    raise ProtocolError('unsupported message type')


def encode_packet(
    message_type: MessageType,
    sequence: int,
    payload: bytes,
    *,
    timestamp_ms: int | None = None,
) -> bytes:
    """Encode one complete datagram with header and IEEE CRC-32."""
    try:
        message_type = MessageType(message_type)
    except ValueError as exc:
        raise ProtocolError('unknown message type') from exc
    sequence = _validate_u32(sequence, 'sequence')
    timestamp_ms = unix_time_ms() if timestamp_ms is None else timestamp_ms
    _validate_u64(timestamp_ms, 'timestamp_ms')
    if not isinstance(payload, bytes) or len(payload) > MAX_PAYLOAD_BYTES:
        raise ProtocolError('payload must be bytes and fit the V1 datagram limit')
    header = HEADER.pack(
        MAGIC, VERSION, int(message_type), 0, sequence, timestamp_ms,
        len(payload), 0,
    )
    covered = header + payload
    return covered + CRC.pack(zlib.crc32(covered) & 0xFFFFFFFF)


def encode_message(
    message: object,
    sequence: int,
    *,
    timestamp_ms: int | None = None,
) -> bytes:
    message_type, payload = encode_payload(message)
    return encode_packet(
        message_type, sequence, payload, timestamp_ms=timestamp_ms
    )


def decode_packet(datagram: bytes) -> Packet:
    """Validate a complete packet before exposing its payload."""
    if not isinstance(datagram, bytes):
        raise ProtocolError('datagram must be bytes')
    if len(datagram) < HEADER.size + CRC.size or len(datagram) > MAX_DATAGRAM_BYTES:
        raise ProtocolError('invalid datagram size')
    try:
        magic, version, raw_type, flags, sequence, timestamp_ms, payload_len, reserved = (
            HEADER.unpack_from(datagram)
        )
    except struct.error as exc:
        raise ProtocolError('truncated fixed header') from exc
    if magic != MAGIC:
        raise ProtocolError('bad magic')
    if version != VERSION:
        raise ProtocolError(f'unsupported protocol version: {version}')
    if flags != 0 or reserved != 0:
        raise ProtocolError('unsupported flags or nonzero reserved field')
    try:
        message_type = MessageType(raw_type)
    except ValueError as exc:
        raise ProtocolError(f'unknown message type: {raw_type}') from exc
    expected_size = HEADER.size + payload_len + CRC.size
    if payload_len > MAX_PAYLOAD_BYTES or len(datagram) != expected_size:
        raise ProtocolError('payload length does not match datagram')
    covered, crc_bytes = datagram[:-CRC.size], datagram[-CRC.size:]
    received_crc, = CRC.unpack(crc_bytes)
    calculated_crc = zlib.crc32(covered) & 0xFFFFFFFF
    if received_crc != calculated_crc:
        raise ProtocolError('bad CRC32')
    return Packet(
        message_type=message_type,
        sequence=sequence,
        timestamp_ms=timestamp_ms,
        payload=datagram[HEADER.size:-CRC.size],
    )


def decode_message(datagram: bytes) -> tuple[Packet, object]:
    packet = decode_packet(datagram)
    return packet, decode_payload(packet)


def timestamp_is_fresh(
    timestamp_ms: int,
    validity_ms: int,
    *,
    now_ms: int | None = None,
    max_future_skew_ms: int = 200,
) -> bool:
    """Diagnostic-only Unix timestamp sanity helper; never gate V1.1 control."""
    if validity_ms < 0 or max_future_skew_ms < 0:
        return False
    now_ms = unix_time_ms() if now_ms is None else now_ms
    age_ms = now_ms - timestamp_ms
    return -max_future_skew_ms <= age_ms <= validity_ms


def is_loopback_address(address: str) -> bool:
    """Return whether an IPv4 or IPv6 address is loopback."""
    import ipaddress

    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False

