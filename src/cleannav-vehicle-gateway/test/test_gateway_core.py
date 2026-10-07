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
    ControlMode,
    Gear,
    MessageType,
    Packet,
    VehicleMode,
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
    'session_valid,sequence_valid,timestamp_valid',
    [
        (False, True, True),
        (True, False, True),
        (True, True, False),
    ],
)
def test_any_invalid_transport_gate_rejects_without_claiming_owner(
    session_valid, sequence_valid, timestamp_valid
):
    arbiter = OwnerArbiter()
    arbiter.note_peer_heartbeat(1.0)

    accepted = arbiter.accept_j6m_command(
        _command(),
        now_monotonic=1.01,
        session_valid=session_valid,
        sequence_valid=sequence_valid,
        timestamp_valid=timestamp_valid,
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
        timestamp_valid=True,
    )
    assert without_heartbeat is False

    arbiter.set_vehicle_mode(VehicleMode.MANUAL)
    arbiter.note_peer_heartbeat(2.0)
    manual = arbiter.accept_j6m_command(
        _command(),
        now_monotonic=2.01,
        session_valid=True,
        sequence_valid=True,
        timestamp_valid=True,
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
        timestamp_valid=True,
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
        timestamp_valid=True,
    )

    accepted = arbiter.accept_j6m_command(
        _command(enabled=False),
        now_monotonic=1.05,
        session_valid=True,
        sequence_valid=True,
        timestamp_valid=True,
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
        timestamp_valid=True,
    )

    assert accepted is False
    assert arbiter.owner is CommandOwner.LEGACY_AUTOWARE


def test_estop_requires_valid_session_sequence_and_timestamp_then_latches():
    arbiter = OwnerArbiter()
    arbiter.note_peer_heartbeat(1.0)

    invalid = arbiter.accept_j6m_command(
        _command(emergency=True),
        now_monotonic=1.01,
        session_valid=False,
        sequence_valid=True,
        timestamp_valid=True,
    )
    assert invalid is False
    assert arbiter.emergency_latched is False

    valid = arbiter.accept_j6m_command(
        _command(emergency=True),
        now_monotonic=1.02,
        session_valid=True,
        sequence_valid=True,
        timestamp_valid=True,
    )
    assert valid is True
    assert arbiter.emergency_latched is True
    assert arbiter.owner is CommandOwner.NONE

    later_command = arbiter.accept_j6m_command(
        _command(),
        now_monotonic=1.03,
        session_valid=True,
        sequence_valid=True,
        timestamp_valid=True,
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
        timestamp_valid=True,
        command_valid_for_sec=0.10,
    )
    assert arbiter.tick(1.09) is False
    assert arbiter.tick(1.11) is True
    assert arbiter.owner is CommandOwner.NONE
    assert arbiter.last_command is None


def test_mock_rejects_stale_udp_command_before_sequence_advance():
    mock = MockAutowareGateway()
    now = time.monotonic()
    mock.j6_session_id = 17
    mock.j6_owner_id = 'J6M-GATEWAY'
    mock._last_hello_rx_monotonic = now
    mock.arbiter.note_peer_heartbeat(now)
    packet = Packet(
        MessageType.CONTROL_COMMAND,
        100,
        unix_time_ms() - 1000,
        b'',
    )

    mock._handle_packet(packet, _command(), now)

    assert mock.snapshot()['stale_packets'] == 1
    assert MessageType.CONTROL_COMMAND not in mock._rx_windows
    assert mock.arbiter.owner is CommandOwner.NONE
    assert mock.arbiter.last_command is None
