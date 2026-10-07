"""UDP-only Autoware-side mock peer for localhost offline verification."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import ipaddress
import secrets
import select
import signal
import socket
import threading
import time

from .gateway_core import (
    CommandOwner,
    OwnerArbiter,
    SequenceDisposition,
    SequenceWindow,
)
from .protocol import (
    ControlCommand,
    GatewayState,
    Gear,
    GatewayStatus as GatewayStatusMessage,
    Heartbeat,
    Hello,
    MessageType,
    PeerRole,
    ProtocolError,
    VehicleMode,
    VehicleState,
    decode_message,
    encode_message,
    unix_time_ms,
)


OFFLINE_BIND_IP = '127.0.0.1'
OFFLINE_BIND_PORT = 39182
OFFLINE_PEER_IP = '127.0.0.1'
OFFLINE_PEER_PORT = 39181
OFFLINE_RX_TIMEOUT_MS = 450


@dataclass
class MockFaults:
    drop_rx: bool = False
    drop_tx: bool = False
    freeze_state: bool = False
    duplicate_seq: bool = False
    out_of_order: bool = False
    malformed: bool = False
    delay_ms: int = 0
    timestamp_offset_ms: int = 0


class MockAutowareGateway:
    """Mock peer that validates commands and returns simulated state."""

    def __init__(
        self,
        *,
        bind_ip: str = OFFLINE_BIND_IP,
        bind_port: int = OFFLINE_BIND_PORT,
        peer_ip: str = OFFLINE_PEER_IP,
        peer_port: int = OFFLINE_PEER_PORT,
        rx_timeout_ms: int = OFFLINE_RX_TIMEOUT_MS,
        faults: MockFaults | None = None,
        initial_owner: CommandOwner = CommandOwner.NONE,
        vehicle_mode: VehicleMode = VehicleMode.AUTONOMOUS,
        dynamics_tau_sec: float = 0.25,
    ) -> None:
        self.bind_ip = self._loopback(bind_ip)
        self.peer_ip = self._loopback(peer_ip)
        self.bind_port = int(bind_port)
        self.peer_port = int(peer_port)
        if not 0 <= self.bind_port <= 65535 or not 1 <= self.peer_port <= 65535:
            raise ValueError('invalid UDP port')
        if self.bind_port in (4500, 4501, 6667) or self.peer_port in (4500, 4501, 6667):
            raise ValueError('legacy IVCU UDP ports are reserved and forbidden')
        if rx_timeout_ms <= 0 or dynamics_tau_sec <= 0:
            raise ValueError('timeouts and dynamics time constant must be positive')
        self.rx_timeout_sec = rx_timeout_ms / 1000.0
        self.dynamics_tau_sec = dynamics_tau_sec
        self.faults = faults or MockFaults()
        self.session_id = secrets.randbits(64)
        self.owner_id = 'MOCK-AUTOWARE'
        self.j6_session_id: int | None = None
        self._retired_j6_sessions: set[int] = set()
        self.j6_owner_id: str | None = None
        self.arbiter = OwnerArbiter(self.rx_timeout_sec)
        self.arbiter.vehicle_mode = VehicleMode(vehicle_mode)
        if initial_owner is CommandOwner.LEGACY_AUTOWARE:
            self.arbiter.claim_legacy_autoware()

        self._sequences = {message_type: 0 for message_type in MessageType}
        self._rx_windows: dict[MessageType, SequenceWindow] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._last_rx_monotonic: float | None = None
        self._last_valid_command_monotonic: float | None = None
        self._last_tx_monotonic: float | None = None
        self._last_state_monotonic: float | None = None
        self._last_hello_rx_monotonic: float | None = None
        self._last_hello_tx_monotonic: float | None = None
        self._last_heartbeat_rx_monotonic: float | None = None
        self._last_heartbeat_tx_monotonic: float | None = None
        self._last_status_monotonic: float | None = None
        self._last_fault_monotonic: float | None = None
        self._last_state_datagram: bytes | None = None
        self._previous_state_datagram: bytes | None = None
        self._malformed_sent = False
        self._accepted_commands = 0
        self._rejected_commands = 0
        self._rejected_sessions = 0
        self._duplicate_commands = 0
        self._out_of_order_commands = 0
        self._malformed_packets = 0
        self._stale_packets = 0
        self._last_command: ControlCommand | None = None
        self._speed_mps = 0.0
        self._steering_rad = 0.0
        self._gear = Gear.UNSPECIFIED

    @staticmethod
    def _loopback(address: str) -> str:
        parsed = ipaddress.ip_address(address)
        if not parsed.is_loopback:
            raise ValueError('mock gateway only accepts loopback addresses')
        return str(parsed)

    @property
    def local_address(self) -> tuple[str, int]:
        if self._socket is None:
            return self.bind_ip, self.bind_port
        return self._socket.getsockname()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp.bind((self.bind_ip, self.bind_port))
            udp.setblocking(False)
            self._socket = udp
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run, name='mock-autoware-udp', daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        with self._lock:
            self._thread = None
            if self._socket is not None:
                self._socket.close()
                self._socket = None

    def send_malformed(self) -> None:
        self._send_raw(b'CNVG\\x01\\xffbroken')

    def _run(self) -> None:
        previous = time.monotonic()
        while not self._stop_event.is_set():
            now = time.monotonic()
            self._receive_available()
            now = time.monotonic()
            self.arbiter.tick(now)
            self._advance_dynamics(now, previous)
            previous = now
            self._send_periodic(now)
            self._stop_event.wait(0.01)

    def _receive_available(self) -> None:
        udp = self._socket
        if udp is None:
            return
        readable, _, _ = select.select([udp], [], [], 0)
        if not readable:
            return
        while True:
            try:
                datagram, source = udp.recvfrom(1024)
            except BlockingIOError:
                return
            if source != (self.peer_ip, self.peer_port):
                continue
            received_at = time.monotonic()
            self._last_rx_monotonic = received_at
            if self.faults.drop_rx:
                continue
            try:
                packet, message = decode_message(datagram)
            except ProtocolError:
                self._malformed_packets += 1
                continue
            self._handle_packet(packet, message, received_at)

    def _handle_packet(self, packet, message, now: float) -> None:
        if packet.message_type is MessageType.HELLO:
            if not isinstance(message, Hello) or message.role is not PeerRole.J6M_GATEWAY:
                self._malformed_packets += 1
                return
            if message.session_id != self.j6_session_id:
                if message.session_id in self._retired_j6_sessions:
                    self._rejected_sessions += 1
                    return
                if self.j6_session_id is not None:
                    self._retired_j6_sessions.add(self.j6_session_id)
                self.j6_session_id = message.session_id
                self.j6_owner_id = message.owner_id
                self._rx_windows = {}
                self.arbiter.peer_heartbeat_monotonic = None
                self._last_heartbeat_rx_monotonic = None
                self._last_valid_command_monotonic = None
                self._last_command = None
                if self.arbiter.owner is CommandOwner.J6M:
                    self.arbiter.release_owner()
            self._last_hello_rx_monotonic = now
            return

        if packet.message_type is MessageType.HEARTBEAT:
            if not isinstance(message, Heartbeat):
                self._malformed_packets += 1
                return
            if (
                message.session_id != self.j6_session_id
                or message.owner_id != self.j6_owner_id
            ):
                self._rejected_commands += 1
                return
            disposition = self._sequence(MessageType.HEARTBEAT, packet.sequence)
            if disposition is not SequenceDisposition.ACCEPT:
                self._count_sequence_rejection(disposition)
                return
            self.arbiter.note_peer_heartbeat(now)
            self._last_heartbeat_rx_monotonic = now
            return

        if packet.message_type is MessageType.CONTROL_COMMAND:
            if not isinstance(message, ControlCommand):
                self._malformed_packets += 1
                return
            session_valid = (
                message.session_id == self.j6_session_id
                and message.owner_id == self.j6_owner_id
                and self._last_hello_rx_monotonic is not None
                and now - self._last_hello_rx_monotonic <= self.rx_timeout_sec * 4
            )
            if not session_valid:
                self._rejected_commands += 1
                return
            disposition = self._sequence(
                MessageType.CONTROL_COMMAND, packet.sequence
            )
            if disposition is not SequenceDisposition.ACCEPT:
                self._count_sequence_rejection(disposition)
                return
            accepted = self.arbiter.accept_j6m_command(
                message,
                now_monotonic=now,
                session_valid=session_valid,
                sequence_valid=True,
                command_valid_for_sec=message.validity_ms / 1000.0,
            )
            if accepted:
                self._accepted_commands += 1
                self._last_valid_command_monotonic = now
                self._last_command = message if message.enable else None
            else:
                self._rejected_commands += 1

    def _sequence(
        self, message_type: MessageType, sequence: int
    ) -> SequenceDisposition:
        return self._rx_windows.setdefault(
            message_type, SequenceWindow()
        ).accept(sequence)

    def _count_sequence_rejection(self, result: SequenceDisposition) -> None:
        if result is SequenceDisposition.DUPLICATE:
            self._duplicate_commands += 1
        else:
            self._out_of_order_commands += 1

    def _advance_dynamics(self, now: float, previous: float) -> None:
        if self.faults.freeze_state:
            return
        dt = max(0.0, min(now - previous, 0.25))
        alpha = 1.0 - pow(2.718281828459045, -dt / self.dynamics_tau_sec)
        command = self.arbiter.last_command
        if (
            self.arbiter.owner is CommandOwner.J6M
            and command is not None
            and not self.arbiter.emergency_latched
        ):
            requested = command.command
            target_speed = requested.target_speed_mps
            target_steering = (
                requested.target_steering_rad
                if requested.mode.value == 1
                else 0.0
            )
            self._gear = requested.gear
        else:
            target_speed = 0.0
            target_steering = 0.0
            self._gear = Gear.UNSPECIFIED
        self._speed_mps += alpha * (target_speed - self._speed_mps)
        self._steering_rad += alpha * (target_steering - self._steering_rad)

    def _send_periodic(self, now: float) -> None:
        if self.faults.drop_tx:
            return
        if (
            self._last_hello_tx_monotonic is None
            or now - self._last_hello_tx_monotonic >= 0.5
        ):
            self._send_message(
                Hello(self.session_id, PeerRole.AUTOWARE_MOCK, self.owner_id)
            )
            self._last_hello_tx_monotonic = now
        if (
            self._last_heartbeat_tx_monotonic is None
            or now - self._last_heartbeat_tx_monotonic >= 0.1
        ):
            self._send_message(Heartbeat(self.session_id, self.owner_id))
            self._last_heartbeat_tx_monotonic = now
        if self._last_state_monotonic is None or now - self._last_state_monotonic >= 0.05:
            self._send_state(now)
            self._last_state_monotonic = now
        if (
            self._last_status_monotonic is None
            or now - self._last_status_monotonic >= 0.5
        ):
            self._send_status()
            self._last_status_monotonic = now
        if self.faults.malformed and not self._malformed_sent:
            self.send_malformed()
            self._malformed_sent = True

    def _send_state(self, now: float) -> None:
        state = VehicleState(
            session_id=self.session_id,
            owner_id=self.owner_id,
            speed_mps=self._speed_mps,
            steering_rad=self._steering_rad,
            gear=self._gear,
            vehicle_mode=(
                VehicleMode.ESTOP if self.arbiter.emergency_latched
                else self.arbiter.vehicle_mode
            ),
            emergency=self.arbiter.emergency_latched,
            gateway_alive=True,
            driver_alive=True,
            fault_code=0,
        )
        datagram = self._encode_next(state)
        self._send_raw(datagram)
        if self.faults.duplicate_seq:
            self._send_raw(datagram)
        if self.faults.out_of_order and self._previous_state_datagram is not None:
            self._send_raw(self._previous_state_datagram)
        self._previous_state_datagram = self._last_state_datagram
        self._last_state_datagram = datagram

    def _send_status(self) -> None:
        state = (
            GatewayState.ESTOP if self.arbiter.emergency_latched
            else GatewayState.ACTIVE
            if self.arbiter.owner is CommandOwner.J6M
            else GatewayState.WAITING
        )
        age = self._age_ms(self._last_rx_monotonic)
        message = GatewayStatusMessage(
            session_id=self.session_id,
            state=state,
            last_rx_age_ms=age,
            last_tx_age_ms=self._age_ms(self._last_tx_monotonic),
            rx_sequence=self._rx_windows.get(
                MessageType.CONTROL_COMMAND, SequenceWindow()
            ).last_sequence or 0,
            tx_sequence=self._sequences[MessageType.VEHICLE_STATE],
            dropped_packets=0,
            malformed_packets=self._malformed_packets,
            stale_packets=self._stale_packets,
            out_of_order_packets=(
                self._duplicate_commands + self._out_of_order_commands
            ),
        )
        self._send_message(message)

    def _send_message(self, message: object) -> None:
        self._send_raw(self._encode_next(message))

    def _encode_next(self, message: object, *, timestamp_ms: int | None = None) -> bytes:
        message_type = self._message_type(message)
        sequence = self._sequences[message_type]
        self._sequences[message_type] = (sequence + 1) & 0xFFFFFFFF
        if timestamp_ms is None:
            timestamp_ms = self._timestamp_ms()
        return encode_message(message, sequence, timestamp_ms=timestamp_ms)

    def _timestamp_ms(self) -> int:
        """Return diagnostic timestamp with optional test-only clock offset."""
        offset = self.faults.timestamp_offset_ms
        return unix_time_ms() + offset

    @staticmethod
    def _message_type(message: object) -> MessageType:
        if isinstance(message, Hello):
            return MessageType.HELLO
        if isinstance(message, Heartbeat):
            return MessageType.HEARTBEAT
        if isinstance(message, VehicleState):
            return MessageType.VEHICLE_STATE
        if isinstance(message, GatewayStatusMessage):
            return MessageType.GATEWAY_STATUS
        raise TypeError(f'unsupported mock message {type(message).__name__}')

    def _send_raw(self, datagram: bytes) -> None:
        udp = self._socket
        if udp is None or self.faults.drop_tx:
            return
        if self.faults.delay_ms:
            time.sleep(self.faults.delay_ms / 1000.0)
        try:
            udp.sendto(datagram, (self.peer_ip, self.peer_port))
            self._last_tx_monotonic = time.monotonic()
        except OSError:
            pass

    @staticmethod
    def _age_ms(value: float | None) -> int:
        if value is None:
            return 0xFFFFFFFF
        return min(0xFFFFFFFF, max(0, int((time.monotonic() - value) * 1000)))

    def snapshot(self) -> dict[str, object]:
        return {
            'owner': self.arbiter.owner.value,
            'emergency_latched': self.arbiter.emergency_latched,
            'speed_mps': self._speed_mps,
            'steering_rad': self._steering_rad,
            'accepted_commands': self._accepted_commands,
            'rejected_commands': self._rejected_commands,
            'rejected_sessions': self._rejected_sessions,
            'duplicate_commands': self._duplicate_commands,
            'out_of_order_commands': self._out_of_order_commands,
            'malformed_packets': self._malformed_packets,
            'stale_packets': self._stale_packets,
            'local_address': self.local_address,
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Loopback-only Autoware protocol mock for offline testing'
    )
    parser.add_argument('--bind-ip', default=OFFLINE_BIND_IP)
    parser.add_argument('--bind-port', type=int, default=OFFLINE_BIND_PORT)
    parser.add_argument('--peer-ip', default=OFFLINE_PEER_IP)
    parser.add_argument('--peer-port', type=int, default=OFFLINE_PEER_PORT)
    parser.add_argument('--rx-timeout-ms', type=int, default=OFFLINE_RX_TIMEOUT_MS)
    parser.add_argument('--drop-rx', action='store_true')
    parser.add_argument('--drop-tx', action='store_true')
    parser.add_argument('--freeze-state', action='store_true')
    parser.add_argument('--duplicate-seq', action='store_true')
    parser.add_argument('--out-of-order', action='store_true')
    parser.add_argument('--malformed', action='store_true')
    parser.add_argument('--timestamp-offset-ms', type=int, default=0)
    parser.add_argument('--delay-ms', type=int, default=0)
    parser.add_argument(
        '--initial-owner',
        choices=('none', 'legacy-autoware'),
        default='none',
    )
    parser.add_argument(
        '--vehicle-mode',
        choices=('auto', 'manual'),
        default='auto',
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    initial_owner = (
        CommandOwner.LEGACY_AUTOWARE
        if args.initial_owner == 'legacy-autoware'
        else CommandOwner.NONE
    )
    vehicle_mode = (
        VehicleMode.AUTONOMOUS
        if args.vehicle_mode == 'auto'
        else VehicleMode.MANUAL
    )
    faults = MockFaults(
        drop_rx=args.drop_rx,
        drop_tx=args.drop_tx,
        freeze_state=args.freeze_state,
        duplicate_seq=args.duplicate_seq,
        out_of_order=args.out_of_order,
        malformed=args.malformed,
        delay_ms=args.delay_ms,
        timestamp_offset_ms=args.timestamp_offset_ms,
    )
    gateway = MockAutowareGateway(
        bind_ip=args.bind_ip,
        bind_port=args.bind_port,
        peer_ip=args.peer_ip,
        peer_port=args.peer_port,
        rx_timeout_ms=args.rx_timeout_ms,
        faults=faults,
        initial_owner=initial_owner,
        vehicle_mode=vehicle_mode,
    )
    stopping = threading.Event()

    def stop_handler(_signum, _frame) -> None:
        stopping.set()

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    gateway.start()
    print(
        f'mock Autoware gateway bound only to {gateway.local_address}; '
        f'peer={gateway.peer_ip}:{gateway.peer_port}; mode={vehicle_mode.name}',
        flush=True,
    )
    try:
        while not stopping.wait(1.0):
            print(gateway.snapshot(), flush=True)
    finally:
        gateway.stop()


if __name__ == '__main__':
    main()

