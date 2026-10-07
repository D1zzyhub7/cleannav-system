"""Sequence, owner, and timeout fail-safe tests."""

import time

import pytest

from cleannav_vehicle_gateway.gateway_core import (
    CommandOwner,
    OwnerArbiter,
    SequenceDisposition,
    SequenceWindow,
)
from cleannav_vehicle_gateway.mock_autoware_gateway import MockAutowareGateway
from cleannav_vehicle_gateway.protocol import (
    ControlCommand,
    Hello,
    Heartbeat,
    PeerRole,
    ControlMode,
    Gear,
    MessageType,
    Packet,
    VehicleMode,
    decode_message,
    encode_message,
    unix_time_ms,
)


def _command(*, enabled=True, emergency=False):
    return ControlCommand(
        session_id=17,
        owner_id='J6M-GATEWAY',
        enable=enabled,
        emergency_stop=emergency,
        mode=ControlMode.TWIST_RAW,
        gear=Gear.DRIVE,
        validity_ms=300,
        target_speed_mps=0.03,
        target_yaw_rate_rps=0.1,
        target_steering_rad=0.0,
    )


def test_sequence_increasing_duplicate_and_out_of_order():
    window = SequenceWindow()

    assert window.accept(100) is SequenceDisposition.ACCEPT
    assert window.accept(101) is SequenceDisposition.ACCEPT
    assert window.accept(102) is SequenceDisposition.ACCEPT
    assert window.accept(102) is SequenceDisposition.DUPLICATE
    assert window.accept(101) is SequenceDisposition.OUT_OF_ORDER
    assert window.last_sequence == 102


def test_sequence_uint32_wraparound():
    window = SequenceWindow()

    assert window.accept(0xFFFFFFFE) is SequenceDisposition.ACCEPT
    assert window.accept(0xFFFFFFFF) is SequenceDisposition.ACCEPT
    assert window.accept(0) is SequenceDisposition.ACCEPT
    assert window.accept(1) is SequenceDisposition.ACCEPT
    assert window.accept(0xFFFFFFFF) is SequenceDisposition.OUT_OF_ORDER


@pytest.mark.parametrize(
    'session_valid,sequence_valid',
    [
        (False, True),
        (True, False),
    ],
)
def test_any_invalid_transport_gate_rejects_without_claiming_owner(
    session_valid, sequence_valid
):
    arbiter = OwnerArbiter()
    arbiter.note_peer_heartbeat(1.0)

    accepted = arbiter.accept_j6m_command(
        _command(),
        now_monotonic=1.01,
        session_valid=session_valid,
        sequence_valid=sequence_valid,
    )

    assert accepted is False
    assert arbiter.owner is CommandOwner.NONE
    assert arbiter.last_command is None


def test_j6m_claim_requires_peer_heartbeat_and_autonomous_vehicle_mode():
    arbiter = OwnerArbiter()
    without_heartbeat = arbiter.accept_j6m_command(
        _command(),
        now_monotonic=1.0,
        session_valid=True,
        sequence_valid=True,
    )
    assert without_heartbeat is False

    arbiter.set_vehicle_mode(VehicleMode.MANUAL)
    arbiter.note_peer_heartbeat(2.0)
    manual = arbiter.accept_j6m_command(
        _command(),
        now_monotonic=2.01,
        session_valid=True,
        sequence_valid=True,
    )
    assert manual is False
    assert arbiter.owner is CommandOwner.NONE


def test_valid_command_claims_and_timeout_releases_j6m_owner():
    arbiter = OwnerArbiter(command_timeout_sec=0.3)
    arbiter.note_peer_heartbeat(5.0)

    accepted = arbiter.accept_j6m_command(
        _command(),
        now_monotonic=5.05,
        session_valid=True,
        sequence_valid=True,
    )
    assert accepted is True
    assert arbiter.owner is CommandOwner.J6M
    assert arbiter.last_command is not None

    assert arbiter.tick(5.20) is False
    assert arbiter.tick(5.36) is True
    assert arbiter.owner is CommandOwner.NONE
    assert arbiter.last_command is None


def test_disable_releases_owner_and_clears_last_nonzero_command():
    arbiter = OwnerArbiter()
    arbiter.note_peer_heartbeat(1.0)
    arbiter.accept_j6m_command(
        _command(),
        now_monotonic=1.01,
        session_valid=True,
        sequence_valid=True,
    )

    accepted = arbiter.accept_j6m_command(
        _command(enabled=False),
        now_monotonic=1.05,
        session_valid=True,
        sequence_valid=True,
    )

    assert accepted is True
    assert arbiter.owner is CommandOwner.NONE
    assert arbiter.last_command is None


def test_legacy_autoware_owner_cannot_be_stolen_by_j6m():
    arbiter = OwnerArbiter()
    arbiter.claim_legacy_autoware()
    arbiter.note_peer_heartbeat(1.0)

    accepted = arbiter.accept_j6m_command(
        _command(),
        now_monotonic=1.01,
        session_valid=True,
        sequence_valid=True,
    )

    assert accepted is False
    assert arbiter.owner is CommandOwner.LEGACY_AUTOWARE


def test_estop_requires_valid_session_and_sequence_then_latches():
    arbiter = OwnerArbiter()
    arbiter.note_peer_heartbeat(1.0)

    invalid = arbiter.accept_j6m_command(
        _command(emergency=True),
        now_monotonic=1.01,
        session_valid=False,
        sequence_valid=True,
    )
    assert invalid is False
    assert arbiter.emergency_latched is False

    valid = arbiter.accept_j6m_command(
        _command(emergency=True),
        now_monotonic=1.02,
        session_valid=True,
        sequence_valid=True,
    )
    assert valid is True
    assert arbiter.emergency_latched is True
    assert arbiter.owner is CommandOwner.NONE

    later_command = arbiter.accept_j6m_command(
        _command(),
        now_monotonic=1.03,
        session_valid=True,
        sequence_valid=True,
    )
    assert later_command is False



def test_command_validity_expires_before_peer_rx_timeout():
    arbiter = OwnerArbiter(command_timeout_sec=0.45)
    arbiter.note_peer_heartbeat(1.0)

    assert arbiter.accept_j6m_command(
        _command(),
        now_monotonic=1.01,
        session_valid=True,
        sequence_valid=True,
        command_valid_for_sec=0.10,
    )
    assert arbiter.tick(1.09) is False
    assert arbiter.tick(1.11) is True
    assert arbiter.owner is CommandOwner.NONE
    assert arbiter.last_command is None


@pytest.mark.parametrize('timestamp_offset_ms', [-86_400_000, 86_400_000])
def test_wall_clock_skew_does_not_reject_fresh_udp_command(timestamp_offset_ms):
    mock = MockAutowareGateway()
    now = time.monotonic()
    mock.j6_session_id = 17
    mock.j6_owner_id = 'J6M-GATEWAY'
    mock._last_hello_rx_monotonic = now
    mock.arbiter.note_peer_heartbeat(now)
    packet, decoded_command = decode_message(encode_message(
        _command(), 100, timestamp_ms=unix_time_ms() + timestamp_offset_ms
    ))

    mock._handle_packet(packet, decoded_command, now)

    assert mock.snapshot()['stale_packets'] == 0
    assert mock._rx_windows[MessageType.CONTROL_COMMAND].last_sequence == 100
    assert mock.arbiter.owner is CommandOwner.J6M
    assert mock.arbiter.last_command is not None


def test_new_session_resets_sequence_window_and_rejects_retired_session_replay():
    mock = MockAutowareGateway()
    now = time.monotonic()
    old_session = 0x1111
    new_session = 0x2222
    mock._handle_packet(
        Packet(MessageType.HELLO, 0, unix_time_ms(), b''),
        Hello(old_session, PeerRole.J6M_GATEWAY, 'J6M-GATEWAY'), now,
    )
    mock._handle_packet(
        Packet(MessageType.HEARTBEAT, 90, unix_time_ms(), b''),
        Heartbeat(old_session, 'J6M-GATEWAY'), now,
    )
    old_command = ControlCommand(
        session_id=old_session, owner_id='J6M-GATEWAY', enable=True,
        emergency_stop=False, mode=ControlMode.TWIST_RAW, gear=Gear.DRIVE,
        validity_ms=300, target_speed_mps=0.03, target_yaw_rate_rps=0.1,
        target_steering_rad=0.0,
    )
    mock._handle_packet(
        Packet(MessageType.CONTROL_COMMAND, 100, unix_time_ms(), b''),
        old_command, now,
    )
    assert mock.arbiter.owner is CommandOwner.J6M

    mock._handle_packet(
        Packet(MessageType.HELLO, 0, unix_time_ms(), b''),
        Hello(new_session, PeerRole.J6M_GATEWAY, 'J6M-GATEWAY'), now + 0.01,
    )
    assert mock.j6_session_id == new_session
    assert mock.arbiter.owner is CommandOwner.NONE
    assert mock.arbiter.peer_heartbeat_monotonic is None
    assert mock._rx_windows == {}

    # An old HELLO cannot roll the active peer back to a retired session.
    mock._handle_packet(
        Packet(MessageType.HELLO, 1, unix_time_ms(), b''),
        Hello(old_session, PeerRole.J6M_GATEWAY, 'J6M-GATEWAY'), now + 0.02,
    )
    mock._handle_packet(
        Packet(MessageType.CONTROL_COMMAND, 101, unix_time_ms(), b''),
        old_command, now + 0.03,
    )
    assert mock.j6_session_id == new_session
    assert mock.arbiter.owner is CommandOwner.NONE
    assert mock._rx_windows == {}
    assert mock.snapshot()['rejected_sessions'] == 1

    mock._handle_packet(
        Packet(MessageType.HEARTBEAT, 0, unix_time_ms(), b''),
        Heartbeat(new_session, 'J6M-GATEWAY'), now + 0.04,
    )
    fresh_command = ControlCommand(
        session_id=new_session, owner_id='J6M-GATEWAY', enable=True,
        emergency_stop=False, mode=ControlMode.TWIST_RAW, gear=Gear.DRIVE,
        validity_ms=300, target_speed_mps=0.02, target_yaw_rate_rps=0.0,
        target_steering_rad=0.0,
    )
    mock._handle_packet(
        Packet(MessageType.CONTROL_COMMAND, 0, unix_time_ms() + 86_400_000, b''),
        fresh_command, now + 0.05,
    )
    assert mock._rx_windows[MessageType.CONTROL_COMMAND].last_sequence == 0
    assert mock.arbiter.owner is CommandOwner.J6M


def test_j6_session_hello_does_not_displace_explicit_legacy_owner():
    mock = MockAutowareGateway(initial_owner=CommandOwner.LEGACY_AUTOWARE)
    now = time.monotonic()
    mock._handle_packet(
        Packet(MessageType.HELLO, 0, unix_time_ms(), b''),
        Hello(77, PeerRole.J6M_GATEWAY, 'J6M-GATEWAY'), now,
    )
    mock._handle_packet(
        Packet(MessageType.HEARTBEAT, 0, unix_time_ms(), b''),
        Heartbeat(77, 'J6M-GATEWAY'), now,
    )
    command = ControlCommand(
        session_id=77, owner_id='J6M-GATEWAY', enable=True,
        emergency_stop=False, mode=ControlMode.TWIST_RAW, gear=Gear.DRIVE,
        validity_ms=300, target_speed_mps=0.02, target_yaw_rate_rps=0.0,
        target_steering_rad=0.0,
    )
    mock._handle_packet(Packet(MessageType.CONTROL_COMMAND, 0, 0, b''), command, now + 0.01)
    assert mock.arbiter.owner is CommandOwner.LEGACY_AUTOWARE


def test_gateway_processes_create_independent_random_session_ids(monkeypatch):
    generated = iter((0x1020304050607080, 0x8070605040302010))
    calls = []

    def fake_randbits(width):
        calls.append(width)
        return next(generated)

    monkeypatch.setattr('cleannav_vehicle_gateway.mock_autoware_gateway.secrets.randbits', fake_randbits)
    first = MockAutowareGateway()
    second = MockAutowareGateway()
    assert calls == [64, 64]
    assert first.session_id != second.session_id


def test_mock_rejects_legacy_ivcu_ports_even_on_loopback():
    with pytest.raises(ValueError, match='legacy IVCU'):
        MockAutowareGateway(bind_port=4500)
    with pytest.raises(ValueError, match='legacy IVCU'):
        MockAutowareGateway(peer_port=6667)
