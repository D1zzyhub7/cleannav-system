"""Packet replay regressions use a localhost UDP receiver only."""

import socket

import pytest

from cleannav_vehicle_gateway.gateway_core import SequenceDisposition, SequenceWindow
from cleannav_vehicle_gateway.protocol import (
    Heartbeat,
    ProtocolError,
    decode_message,
    encode_message,
)
from cleannav_vehicle_gateway.replay import parse_datagram_blob, replay_datagrams


def _packet(sequence):
    return encode_message(
        Heartbeat(0x1234, 'J6M-GATEWAY'), sequence, timestamp_ms=1700000000000 + sequence
    )


def _receiver():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(('127.0.0.1', 0))
    udp.settimeout(0.5)
    return udp


def test_parse_single_concatenated_and_length_prefixed_datagrams():
    first, second = _packet(1), _packet(2)
    assert parse_datagram_blob(first) == [first]
    assert parse_datagram_blob(first + second) == [first, second]
    framed = len(first).to_bytes(2, 'big') + first + len(second).to_bytes(2, 'big') + second
    assert parse_datagram_blob(framed) == [first, second]


def test_localhost_normal_duplicate_and_out_of_order_replay():
    first, second = _packet(10), _packet(11)
    with _receiver() as udp:
        port = udp.getsockname()[1]
        assert replay_datagrams([first], target_port=port) == 1
        assert udp.recvfrom(1024)[0] == first

        assert replay_datagrams([first], target_port=port, duplicate=True) == 2
        assert [udp.recvfrom(1024)[0], udp.recvfrom(1024)[0]] == [first, first]

        assert replay_datagrams([first, second], target_port=port, out_of_order=True) == 2
        window = SequenceWindow()
        rx = [udp.recvfrom(1024)[0], udp.recvfrom(1024)[0]]
        seqs = [decode_message(datagram)[0].sequence for datagram in rx]
        assert seqs == [11, 10]
        assert [window.accept(seq) for seq in seqs] == [
            SequenceDisposition.ACCEPT,
            SequenceDisposition.OUT_OF_ORDER,
        ]


def test_localhost_corrupt_and_stale_session_replay():
    packet = _packet(4)
    with _receiver() as udp:
        port = udp.getsockname()[1]
        assert replay_datagrams([packet], target_port=port, corrupt_byte=24) == 1
        corrupt = udp.recvfrom(1024)[0]
        with pytest.raises(ProtocolError, match='CRC'):
            decode_message(corrupt)

        assert replay_datagrams([packet], target_port=port, stale_session_id=0xAABB) == 1
        changed = udp.recvfrom(1024)[0]
        _, message = decode_message(changed)
        assert message.session_id == 0xAABB


def test_replay_hard_rejects_non_loopback_and_legacy_ivcu_ports():
    packet = _packet(1)
    with pytest.raises(ValueError, match='127.0.0.1'):
        replay_datagrams([packet], target_ip='192.0.2.1', target_port=39182)
    with pytest.raises(ValueError, match='reserved'):
        replay_datagrams([packet], target_port=4501)
