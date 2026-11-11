"""Transport-independent freshness and command-owner logic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .protocol import ControlCommand, VehicleMode


class SequenceDisposition(Enum):
    ACCEPT = 'accept'
    DUPLICATE = 'duplicate'
    OUT_OF_ORDER = 'out_of_order'


class SequenceWindow:
    """RFC-1982-style uint32 sequence comparison with a half-range rule."""

    def __init__(self) -> None:
        self.last_sequence: int | None = None

    def reset(self) -> None:
        self.last_sequence = None

    def accept(self, sequence: int) -> SequenceDisposition:
        if not 0 <= sequence <= 0xFFFFFFFF:
            return SequenceDisposition.OUT_OF_ORDER
        if self.last_sequence is None:
            self.last_sequence = sequence
            return SequenceDisposition.ACCEPT
        delta = (sequence - self.last_sequence) & 0xFFFFFFFF
        if delta == 0:
            return SequenceDisposition.DUPLICATE
        if delta >= 0x80000000:
            return SequenceDisposition.OUT_OF_ORDER
        self.last_sequence = sequence
        return SequenceDisposition.ACCEPT


class CommandOwner(Enum):
    NONE = 'OWNER_NONE'
    LEGACY_AUTOWARE = 'OWNER_LEGACY_AUTOWARE'
    J6M = 'OWNER_J6M'


@dataclass
class AcceptedCommand:
    command: ControlCommand
    valid_until_monotonic: float


class OwnerArbiter:
    """Offline mock peer acceptance policy; it never publishes /vehicle_cmd.

    Production owner selection and safe transitions are in the standalone C++
    CommandArbiter, which requires an explicit operator request.
    """

    def __init__(self, command_timeout_sec: float = 0.5) -> None:
        if command_timeout_sec <= 0:
            raise ValueError('command_timeout_sec must be positive')
        self.command_timeout_sec = command_timeout_sec
        self.owner = CommandOwner.NONE
        self.vehicle_mode = VehicleMode.AUTONOMOUS
        self.emergency_latched = False
        self.peer_heartbeat_monotonic: float | None = None
        self.last_command: AcceptedCommand | None = None

    def set_vehicle_mode(self, mode: VehicleMode) -> None:
        self.vehicle_mode = VehicleMode(mode)
        if self.vehicle_mode is not VehicleMode.AUTONOMOUS:
            self._clear_j6m_owner()

    def note_peer_heartbeat(self, now_monotonic: float) -> None:
        self.peer_heartbeat_monotonic = now_monotonic

    def claim_legacy_autoware(self) -> None:
        if not self.emergency_latched:
            self.owner = CommandOwner.LEGACY_AUTOWARE
            self.last_command = None

    def release_owner(self) -> None:
        self.owner = CommandOwner.NONE
        self.last_command = None

    def latch_estop(self) -> None:
        self.emergency_latched = True
        self.owner = CommandOwner.NONE
        self.last_command = None

    def reset_estop_local(self) -> None:
        """Mock/local-only reset; no remote E-stop clear message exists in V1."""
        self.emergency_latched = False
        self.owner = CommandOwner.NONE
        self.last_command = None

    def accept_j6m_command(
        self,
        command: ControlCommand,
        *,
        now_monotonic: float,
        session_valid: bool,
        sequence_valid: bool,
        command_valid_for_sec: float | None = None,
    ) -> bool:
        """Accept a command only when the session and sequence gates are valid."""
        if not (session_valid and sequence_valid):
            return False
        if command_valid_for_sec is None:
            command_valid_for_sec = command.validity_ms / 1000.0
        if command_valid_for_sec <= 0:
            return False
        if command.emergency_stop:
            self.latch_estop()
            return True
        if self.emergency_latched:
            return False
        if not command.enable:
            if self.owner is CommandOwner.J6M:
                self.release_owner()
            return True
        if self.owner is CommandOwner.LEGACY_AUTOWARE:
            return False
        if self.vehicle_mode is not VehicleMode.AUTONOMOUS:
            return False
        heartbeat_at = self.peer_heartbeat_monotonic
        if (
            heartbeat_at is None
            or now_monotonic - heartbeat_at > self.command_timeout_sec
        ):
            return False
        self.owner = CommandOwner.J6M
        self.last_command = AcceptedCommand(
            command,
            now_monotonic + min(
                self.command_timeout_sec, command_valid_for_sec
            ),
        )
        return True

    def tick(self, now_monotonic: float) -> bool:
        """Expire J6M authority and command on either heartbeat or command loss."""
        if self.owner is not CommandOwner.J6M:
            return False
        heartbeat_at = self.peer_heartbeat_monotonic
        command = self.last_command
        expired = (
            heartbeat_at is None
            or command is None
            or now_monotonic - heartbeat_at > self.command_timeout_sec
            or now_monotonic >= command.valid_until_monotonic
        )
        if expired:
            self._clear_j6m_owner()
            return True
        return False

    def _clear_j6m_owner(self) -> None:
        if self.owner is CommandOwner.J6M:
            self.owner = CommandOwner.NONE
            self.last_command = None

