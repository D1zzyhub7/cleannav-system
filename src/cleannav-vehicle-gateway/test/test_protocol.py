"""NET-OFFLINE-V1 wire-format tests."""

from dataclasses import fields, replace
import struct

import pytest

from cleannav_vehicle_gateway.protocol import (
    HEADER,
    ControlCommand,
    REQUIRED_CAPABILITIES,
    ControlMode,
    GatewayState,
    GatewayStatus,
    Gear,
    Heartbeat,
    Hello,
    MessageType,
    PeerRole,
    ProtocolError,
    VehicleMode,
    VehicleState,
    capabilities_compatible,
    decode_message,
    decode_packet,
    encode_message,
    encode_packet,
    timestamp_is_fresh,
    unix_time_ms,
)


def _messages():
    return (
        Hello(12, PeerRole.J6M_GATEWAY, 'J6M-GATEWAY'),
        Heartbeat(12, 'J6M-GATEWAY'),
        ControlCommand(
            12, 'J6M-GATEWAY', True, False, ControlMode.TWIST_RAW,
            Gear.DRIVE, 300, 0.03, 0.2, 0.0,
        ),
        VehicleState(
            14, 'MOCK-AUTOWARE', 0.02, 0.1, Gear.DRIVE,
            VehicleMode.AUTONOMOUS, False, True, True, 0,
        ),
        GatewayStatus(
            14, GatewayState.ACTIVE, 20, 10, 8, 9, 0, 0, 0, 0,
        ),
    )


@pytest.mark.parametrize('sequence,message', [
    (index, message) for index, message in enumerate(_messages())
])
def test_every_v1_message_round_trips(sequence, message):
    timestamp = unix_time_ms()

    datagram = encode_message(message, sequence, timestamp_ms=timestamp)
    packet, decoded = decode_message(datagram)

    assert packet.message_type == tuple(MessageType)[sequence]
    assert packet.sequence == sequence
    assert packet.timestamp_ms == timestamp
    assert type(decoded) is type(message)
    float_fields = {
        ControlCommand: {
            'target_speed_mps',
            'target_yaw_rate_rps',
            'target_steering_rad',
        },
        VehicleState: {'speed_mps', 'steering_rad'},
    }.get(type(message), set())
    for field in fields(message):
        expected = getattr(message, field.name)
        actual = getattr(decoded, field.name)
        if field.name in float_fields:
            assert actual == pytest.approx(expected, rel=1e-6, abs=1e-7)
        else:
            assert actual == expected


def test_header_uses_network_byte_order_and_fixed_width():
    message = Heartbeat(0x0102030405060708, 'J6M-GATEWAY')
    datagram = encode_message(
        message, 0x01020304, timestamp_ms=0x0102030405060708
    )

    assert HEADER.size == 24
    assert datagram[:4] == b'CNVG'
    assert datagram[4] == 1
    assert datagram[8:12] == b'\x01\x02\x03\x04'
    assert datagram[12:20] == b'\x01\x02\x03\x04\x05\x06\x07\x08'


def test_crc_covers_header_and_payload():
    datagram = encode_message(
        Heartbeat(1, 'J6M-GATEWAY'), 2, timestamp_ms=3
    )
    assert decode_message(datagram)[1] == Heartbeat(1, 'J6M-GATEWAY')

    corrupted = bytearray(datagram)
    corrupted[-5] ^= 0x01
    with pytest.raises(ProtocolError, match='CRC'):
        decode_packet(bytes(corrupted))


@pytest.mark.parametrize(
    'mutation,expected',
    [
        (lambda raw: raw.__setitem__(slice(0, 4), b'BAD!'), 'magic'),
        (lambda raw: raw.__setitem__(4, 2), 'version'),
        (lambda raw: raw.__setitem__(5, 255), 'message type'),
        (lambda raw: raw.__setitem__(6, 1), 'flags'),
        (lambda raw: raw.__setitem__(slice(20, 22), b'\x00\x01'), 'length'),
    ],
)
def test_malformed_headers_are_rejected(mutation, expected):
    datagram = encode_message(
        Heartbeat(1, 'J6M-GATEWAY'), 2, timestamp_ms=3
    )
    corrupted = bytearray(datagram)
    mutation(corrupted)

    with pytest.raises(ProtocolError, match=expected):
        decode_packet(bytes(corrupted))


def test_wrong_typed_payload_length_is_rejected():
    datagram = encode_packet(MessageType.HEARTBEAT, 1, b'wrong', timestamp_ms=1)
    packet = decode_packet(datagram)

    with pytest.raises(ProtocolError, match='payload length'):
        from cleannav_vehicle_gateway.protocol import decode_payload
        decode_payload(packet)


def test_nonfinite_command_values_are_rejected():
    command = replace(
        _messages()[2],
        target_speed_mps=float('nan'),
    )
    with pytest.raises(ProtocolError, match='finite'):
        encode_message(command, 1)


def test_timestamp_diagnostic_sanity_helper_only():
    now = 10_000

    assert timestamp_is_fresh(9_800, 300, now_ms=now, max_future_skew_ms=200)
    assert not timestamp_is_fresh(9_600, 300, now_ms=now, max_future_skew_ms=200)
    assert not timestamp_is_fresh(10_201, 300, now_ms=now, max_future_skew_ms=200)


def test_v1_payload_has_no_c_struct_padding_assumption():
    command = _messages()[2]
    datagram = encode_message(command, 1, timestamp_ms=2)

    assert len(datagram) == HEADER.size + struct.calcsize('!Q16sBBBbHfff') + 4



def test_v11_hello_capability_negotiation_fails_closed():
    compatible = Hello(42, PeerRole.AUTOWARE_PC, 'AUTOWARE-PC')
    packet, decoded = decode_message(encode_message(compatible, 1, timestamp_ms=1))
    assert packet.flags == REQUIRED_CAPABILITIES
    assert capabilities_compatible(decoded.capabilities)
    assert capabilities_compatible(REQUIRED_CAPABILITIES)
    assert not capabilities_compatible(REQUIRED_CAPABILITIES & ~1)
    assert not capabilities_compatible(REQUIRED_CAPABILITIES | (1 << 15))

    old_hello = encode_message(
        Hello(42, PeerRole.AUTOWARE_PC, 'AUTOWARE-PC', capabilities=0),
        2, timestamp_ms=2,
    )
    _, old_message = decode_message(old_hello)
    assert not capabilities_compatible(old_message.capabilities)


def test_only_hello_may_advertise_capability_flags():
    with pytest.raises(ProtocolError, match='only defined for HELLO'):
        encode_packet(MessageType.HEARTBEAT, 1, b'', timestamp_ms=1, flags=1)
