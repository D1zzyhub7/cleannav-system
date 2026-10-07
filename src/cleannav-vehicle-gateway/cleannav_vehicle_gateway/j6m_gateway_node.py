"""ROS 2 side of the offline-first vehicle-level UDP gateway."""

from __future__ import annotations

import ipaddress
import math
import secrets
import socket
import time

from cleannav_interfaces.msg import SafetyStatus
from diagnostic_msgs.msg import DiagnosticStatus, KeyValue
from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Float64, Int8, String

from .protocol import (
    ControlCommand,
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
    decode_message,
    encode_message,
    unix_time_ms,
)
from .gateway_core import SequenceDisposition, SequenceWindow


OFFLINE_BIND_IP = '127.0.0.1'
OFFLINE_BIND_PORT = 39181
OFFLINE_PEER_IP = '127.0.0.1'
OFFLINE_PEER_PORT = 39182
OFFLINE_CMD_VEL_TIMEOUT_MS = 350
OFFLINE_PEER_TIMEOUT_MS = 450
OFFLINE_STATE_TIMEOUT_MS = 1000
OFFLINE_COMMAND_VALIDITY_MS = 300


class J6MVehicleGatewayNode(Node):
    """Convert post-Safety ROS 2 commands to V1 UDP and return vehicle state."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            'j6m_vehicle_gateway',
            automatically_declare_parameters_from_overrides=False,
            **kwargs,
        )
        self._bind_ip = str(self.declare_parameter(
            'bind_ip', OFFLINE_BIND_IP
        ).value)
        self._bind_port = int(self.declare_parameter(
            'bind_port', OFFLINE_BIND_PORT
        ).value)
        self._peer_ip = str(self.declare_parameter(
            'peer_ip', OFFLINE_PEER_IP
        ).value)
        self._peer_port = int(self.declare_parameter(
            'peer_port', OFFLINE_PEER_PORT
        ).value)
        self._offline_test_mode = bool(self.declare_parameter(
            'offline_test_mode', True
        ).value)
        self._owner_id = str(self.declare_parameter(
            'owner_id', 'J6M-GATEWAY'
        ).value)
        self._control_mode = ControlMode(int(self.declare_parameter(
            'control_mode', int(ControlMode.TWIST_RAW)
        ).value))
        self._cmd_vel_timeout_ms = int(self.declare_parameter(
            'cmd_vel_timeout_ms', OFFLINE_CMD_VEL_TIMEOUT_MS
        ).value)
        self._safety_status_timeout_ms = int(self.declare_parameter(
            'safety_status_timeout_ms', 1500
        ).value)
        self._peer_timeout_ms = int(self.declare_parameter(
            'peer_timeout_ms', OFFLINE_PEER_TIMEOUT_MS
        ).value)
        self._state_timeout_ms = int(self.declare_parameter(
            'state_timeout_ms', OFFLINE_STATE_TIMEOUT_MS
        ).value)
        self._command_validity_ms = int(self.declare_parameter(
            'command_validity_ms', OFFLINE_COMMAND_VALIDITY_MS
        ).value)
        self._safe_burst_ms = int(self.declare_parameter(
            'safe_burst_ms', 300
        ).value)
        self._control_period_ms = int(self.declare_parameter(
            'control_period_ms', 50
        ).value)
        self._heartbeat_period_ms = int(self.declare_parameter(
            'heartbeat_period_ms', 100
        ).value)
        self._hello_period_ms = int(self.declare_parameter(
            'hello_period_ms', 500
        ).value)
        self._status_period_ms = int(self.declare_parameter(
            'status_period_ms', 250
        ).value)
        self._connect_timeout_ms = int(self.declare_parameter(
            'connect_timeout_ms', 2000
        ).value)
        self._target_steering_timeout_ms = int(self.declare_parameter(
            'target_steering_timeout_ms', 350
        ).value)
        self._safety_topic = str(self.declare_parameter(
            'safety_status_topic', '/cleannav/safety_status'
        ).value)
        self._cmd_vel_topic = str(self.declare_parameter(
            'cmd_vel_topic', '/cmd_vel'
        ).value)
        self._estop_topic = str(self.declare_parameter(
            'emergency_stop_topic', '/cleannav/safety/emergency_stop'
        ).value)
        self._steering_topic = str(self.declare_parameter(
            'target_steering_topic', '/cleannav/vehicle/target_steering'
        ).value)
        self._gear_topic = str(self.declare_parameter(
            'target_gear_topic', '/cleannav/vehicle/target_gear'
        ).value)

        self._validate_parameters()
        try:
            self._bind_ip = str(ipaddress.IPv4Address(self._bind_ip))
            self._peer_ip = str(ipaddress.IPv4Address(self._peer_ip))
        except ipaddress.AddressValueError as exc:
            raise ValueError('V1 currently requires IPv4 addresses') from exc

        self._session_id = secrets.randbits(64)
        self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._udp.bind((self._bind_ip, self._bind_port))
        self._udp.setblocking(False)

        self._sequences = {message_type: 0 for message_type in MessageType}
        self._rx_windows: dict[MessageType, SequenceWindow] = {}
        self._peer_session_id: int | None = None
        self._retired_peer_sessions: set[int] = set()
        self._peer_owner_id: str | None = None
        self._peer_role: PeerRole | None = None
        self._peer_hello_rx: float | None = None
        self._peer_heartbeat_rx: float | None = None
        self._peer_state_rx: float | None = None
        self._peer_state: VehicleState | None = None
        self._peer_status: GatewayStatus | None = None
        self._peer_status_rx: float | None = None

        self._latest_cmd_vel: tuple[float, float] | None = None
        self._cmd_vel_rx: float | None = None
        self._target_steering: float | None = None
        self._target_steering_rx: float | None = None
        self._target_gear = Gear.UNSPECIFIED
        self._target_gear_rx: float | None = None
        self._safety_status: SafetyStatus | None = None
        self._safety_status_rx: float | None = None
        self._estop_input = False

        self._last_rx: float | None = None
        self._last_tx: float | None = None
        self._last_hello_tx: float | None = None
        self._last_heartbeat_tx: float | None = None
        self._last_control_tx: float | None = None
        self._last_status_tx: float | None = None
        self._safe_burst_until = 0.0
        self._was_enabled = False
        self._ever_enabled = False
        self._pending_estop = False
        self._last_diagnostic_tx: float | None = None
        self._started_monotonic = time.monotonic()
        self._fatal_error = ''
        self._tx_control_sequence = 0
        self._rx_state_sequence = 0
        self._counters = {
            'dropped_packets': 0,
            'malformed_packets': 0,
            'stale_packets': 0,
            'out_of_order_packets': 0,
            'duplicate_packets': 0,
        }
        self._gateway_state = GatewayState.WAITING

        self._speed_pub = self.create_publisher(
            Float64, '/cleannav/vehicle/speed', 10
        )
        self._steering_pub = self.create_publisher(
            Float64, '/cleannav/vehicle/steering', 10
        )
        self._gear_pub = self.create_publisher(
            Int8, '/cleannav/vehicle/gear', 10
        )
        self._mode_pub = self.create_publisher(
            String, '/cleannav/vehicle/mode', 10
        )
        self._status_pub = self.create_publisher(
            DiagnosticStatus, '/cleannav/vehicle/gateway_status', 10
        )
        self._cmd_sub = self.create_subscription(
            Twist, self._cmd_vel_topic, self._cmd_vel_cb, 10
        )
        self._safety_sub = self.create_subscription(
            SafetyStatus, self._safety_topic, self._safety_status_cb, 10
        )
        self._estop_sub = self.create_subscription(
            Bool, self._estop_topic, self._estop_cb, 10
        )
        self._steering_sub = self.create_subscription(
            Float64, self._steering_topic, self._steering_cb, 10
        )
        self._gear_sub = self.create_subscription(
            Int8, self._gear_topic, self._gear_cb, 10
        )
        self._timer = self.create_timer(0.02, self._timer_cb)

        self.get_logger().info(
            'NET-OFFLINE-V1 gateway bound to '
            f'{self._bind_ip}:{self._bind_port}, peer '
            f'{self._peer_ip}:{self._peer_port}, '
            f'offline_test_mode={self._offline_test_mode}, '
            f'mode={self._control_mode.name}'
        )

    def _validate_parameters(self) -> None:
        if (
            not self._owner_id
            or not self._owner_id.isascii()
            or len(self._owner_id.encode('ascii')) > 16
        ):
            raise ValueError('owner_id must be 1..16 ASCII characters')
        if not 1 <= self._bind_port <= 65535 or not 1 <= self._peer_port <= 65535:
            raise ValueError('UDP ports must be in 1..65535')
        if self._bind_port in (4500, 4501, 6667) or self._peer_port in (4500, 4501, 6667):
            raise ValueError('legacy IVCU UDP ports are reserved and forbidden')
        if self._offline_test_mode and (
            self._bind_ip != OFFLINE_BIND_IP or self._peer_ip != OFFLINE_PEER_IP
        ):
            raise ValueError(
                'offline_test_mode requires bind_ip and peer_ip to be 127.0.0.1'
            )
        timeouts = (
            self._cmd_vel_timeout_ms,
            self._safety_status_timeout_ms,
            self._peer_timeout_ms,
            self._state_timeout_ms,
            self._command_validity_ms,
            self._safe_burst_ms,
            self._control_period_ms,
            self._heartbeat_period_ms,
            self._hello_period_ms,
            self._status_period_ms,
            self._connect_timeout_ms,
        )
        if any(value <= 0 for value in timeouts):
            raise ValueError('all timeout and period parameters must be positive')
        if self._command_validity_ms > min(
            self._cmd_vel_timeout_ms, self._peer_timeout_ms
        ):
            raise ValueError(
                'command_validity_ms must not exceed command or peer timeout'
            )

    def _cmd_vel_cb(self, message: Twist) -> None:
        values = (
            float(message.linear.x),
            float(message.angular.z),
        )
        if not all(math.isfinite(value) for value in values):
            self._counters['malformed_packets'] += 1
            self._latest_cmd_vel = None
            self._cmd_vel_rx = None
            return
        self._latest_cmd_vel = values
        self._cmd_vel_rx = time.monotonic()

    def _safety_status_cb(self, message: SafetyStatus) -> None:
        self._safety_status = message
        self._safety_status_rx = time.monotonic()
        if message.emergency_stop_active:
            self._pending_estop = True

    def _estop_cb(self, message: Bool) -> None:
        self._estop_input = bool(message.data)
        if self._estop_input:
            self._pending_estop = True

    def _steering_cb(self, message: Float64) -> None:
        value = float(message.data)
        if not math.isfinite(value):
            self._target_steering = None
            self._target_steering_rx = None
            self._counters['malformed_packets'] += 1
            return
        self._target_steering = value
        self._target_steering_rx = time.monotonic()

    def _gear_cb(self, message: Int8) -> None:
        try:
            self._target_gear = Gear(int(message.data))
            self._target_gear_rx = time.monotonic()
        except ValueError:
            self._target_gear = Gear.UNSPECIFIED
            self._target_gear_rx = None
            self._counters['malformed_packets'] += 1

    def _timer_cb(self) -> None:
        now = time.monotonic()
        self._receive_available(now)
        if self._fatal_error:
            self._gateway_state = GatewayState.FAULT
        self._send_periodic(now)
        self._update_status(now)
        if (
            self._last_diagnostic_tx is None
            or self._elapsed_ms(self._last_diagnostic_tx, now)
            >= self._status_period_ms
        ):
            self._publish_diagnostic(now)
            self._last_diagnostic_tx = now

    def _receive_available(self, now: float) -> None:
        while True:
            try:
                datagram, source = self._udp.recvfrom(1024)
            except BlockingIOError:
                return
            except OSError as exc:
                self._counters['dropped_packets'] += 1
                self._fatal_error = str(exc)
                return
            if source != (self._peer_ip, self._peer_port):
                self._counters['dropped_packets'] += 1
                continue
            try:
                packet, message = decode_message(datagram)
            except ProtocolError:
                self._counters['malformed_packets'] += 1
                continue
            self._handle_packet(packet, message, time.monotonic())

    def _handle_packet(self, packet, message, now: float) -> None:
        if packet.message_type is MessageType.HELLO:
            if not isinstance(message, Hello) or message.role is not PeerRole.AUTOWARE_MOCK:
                self._counters['malformed_packets'] += 1
                return
            if message.session_id != self._peer_session_id:
                if message.session_id in self._retired_peer_sessions:
                    self._counters['dropped_packets'] += 1
                    return
                if self._peer_session_id is not None:
                    self._retired_peer_sessions.add(self._peer_session_id)
                self._peer_session_id = message.session_id
                self._peer_owner_id = message.owner_id
                self._peer_role = message.role
                self._rx_windows = {}
                self._peer_heartbeat_rx = None
                self._peer_state_rx = None
                self._peer_state = None
                self._peer_status = None
                self._peer_status_rx = None
            self._peer_hello_rx = now
            self._last_rx = now
            return

        if packet.message_type is MessageType.HEARTBEAT:
            if not isinstance(message, Heartbeat) or not self._valid_peer_session(message):
                self._counters['dropped_packets'] += 1
                return
            if not self._sequence_accept(MessageType.HEARTBEAT, packet.sequence):
                return
            self._peer_heartbeat_rx = now
            self._last_rx = now
            return

        if packet.message_type is MessageType.VEHICLE_STATE:
            if not isinstance(message, VehicleState) or not self._valid_peer_session(message):
                self._counters['dropped_packets'] += 1
                return
            if not self._sequence_accept(MessageType.VEHICLE_STATE, packet.sequence):
                return
            self._peer_state = message
            self._peer_state_rx = now
            self._last_rx = now
            self._rx_state_sequence = packet.sequence
            self._publish_vehicle_state(message)
            return

        if packet.message_type is MessageType.GATEWAY_STATUS:
            if not isinstance(message, GatewayStatus) or (
                self._peer_session_id is None
                or message.session_id != self._peer_session_id
            ):
                self._counters['dropped_packets'] += 1
                return
            if not self._sequence_accept(MessageType.GATEWAY_STATUS, packet.sequence):
                return
            self._peer_status = message
            self._peer_status_rx = now
            self._last_rx = now
            return

        self._counters['malformed_packets'] += 1

    def _valid_peer_session(self, message: Heartbeat | VehicleState) -> bool:
        return (
            self._peer_session_id is not None
            and message.session_id == self._peer_session_id
            and message.owner_id == self._peer_owner_id
        )

    def _sequence_accept(
        self, message_type: MessageType, sequence: int
    ) -> bool:
        result = self._rx_windows.setdefault(
            message_type, SequenceWindow()
        ).accept(sequence)
        if result is SequenceDisposition.DUPLICATE:
            self._counters['duplicate_packets'] += 1
            self._counters['out_of_order_packets'] += 1
            return False
        if result is SequenceDisposition.OUT_OF_ORDER:
            self._counters['out_of_order_packets'] += 1
            return False
        return True

    def _publish_vehicle_state(self, state: VehicleState) -> None:
        self._speed_pub.publish(Float64(data=float(state.speed_mps)))
        self._steering_pub.publish(Float64(data=float(state.steering_rad)))
        self._gear_pub.publish(Int8(data=int(state.gear)))
        self._mode_pub.publish(String(data=VehicleMode(state.vehicle_mode).name))

    def _send_periodic(self, now: float) -> None:
        if (
            self._last_hello_tx is None
            or self._elapsed_ms(self._last_hello_tx, now) >= self._hello_period_ms
        ):
            self._send_message(
                Hello(
                    session_id=self._session_id,
                    role=PeerRole.J6M_GATEWAY,
                    owner_id=self._owner_id,
                ),
                MessageType.HELLO,
            )
            self._last_hello_tx = now
        if (
            self._last_heartbeat_tx is None
            or self._elapsed_ms(self._last_heartbeat_tx, now)
            >= self._heartbeat_period_ms
        ):
            self._send_message(
                Heartbeat(self._session_id, self._owner_id),
                MessageType.HEARTBEAT,
            )
            self._last_heartbeat_tx = now

        control_due = (
            self._last_control_tx is None
            or self._elapsed_ms(self._last_control_tx, now)
            >= self._control_period_ms
        )
        if control_due:
            ready, estop_active = self._command_ready(now)
            if ready:
                command = self._build_command(
                    enable=True, emergency_stop=False, now=now
                )
                self._send_message(command, MessageType.CONTROL_COMMAND)
                self._last_control_tx = now
                self._was_enabled = True
                self._ever_enabled = True
                self._pending_estop = False
            else:
                if self._was_enabled or self._pending_estop:
                    self._safe_burst_until = max(
                        self._safe_burst_until,
                        now + self._safe_burst_ms / 1000.0,
                    )
                    self._was_enabled = False
                    self._pending_estop = False
                if now <= self._safe_burst_until:
                    safe = self._build_command(
                        enable=False,
                        emergency_stop=estop_active,
                        now=now,
                    )
                    self._send_message(safe, MessageType.CONTROL_COMMAND)
                    self._last_control_tx = now

        if (
            self._last_status_tx is None
            or self._elapsed_ms(self._last_status_tx, now)
            >= self._status_period_ms
        ):
            self._send_message(self._wire_status(now), MessageType.GATEWAY_STATUS)
            self._last_status_tx = now

    def _command_ready(self, now: float) -> tuple[bool, bool]:
        safety = self._safety_status
        safety_fresh = (
            safety is not None
            and self._safety_status_rx is not None
            and self._elapsed_ms(self._safety_status_rx, now)
            <= self._safety_status_timeout_ms
        )
        command_fresh = (
            self._latest_cmd_vel is not None
            and self._cmd_vel_rx is not None
            and self._elapsed_ms(self._cmd_vel_rx, now)
            <= self._cmd_vel_timeout_ms
        )
        peer_fresh = (
            self._peer_session_id is not None
            and self._peer_heartbeat_rx is not None
            and self._peer_state_rx is not None
            and self._peer_hello_rx is not None
            and self._elapsed_ms(self._peer_heartbeat_rx, now)
            <= self._peer_timeout_ms
            and self._elapsed_ms(self._peer_state_rx, now)
            <= self._state_timeout_ms
        )
        state = self._peer_state
        estop_active = (
            self._estop_input
            or (safety is not None and safety.emergency_stop_active)
            or (state is not None and state.emergency)
            or (state is not None and state.vehicle_mode is VehicleMode.ESTOP)
        )
        safety_allowed = (
            safety_fresh
            and safety is not None
            and safety.autonomous_enabled
            and not safety.block_all
            and not safety.emergency_stop_active
        )
        mode_allowed = (
            state is not None
            and state.vehicle_mode is VehicleMode.AUTONOMOUS
            and state.gateway_alive
            and state.driver_alive
            and state.fault_code == 0
        )
        steering_fresh = (
            self._target_steering is not None
            and self._target_steering_rx is not None
            and self._elapsed_ms(self._target_steering_rx, now)
            <= self._target_steering_timeout_ms
        )
        mode_input_ready = (
            self._control_mode is ControlMode.TWIST_RAW or steering_fresh
        )
        ready = (
            not self._fatal_error
            and safety_allowed
            and command_fresh
            and peer_fresh
            and mode_allowed
            and mode_input_ready
            and not estop_active
        )
        return ready, estop_active

    def _build_command(
        self,
        *,
        enable: bool,
        emergency_stop: bool,
        now: float,
    ) -> ControlCommand:
        speed = 0.0
        yaw_rate = 0.0
        steering = 0.0
        gear = Gear.UNSPECIFIED
        if enable and self._latest_cmd_vel is not None:
            speed, input_yaw_rate = self._latest_cmd_vel
            if self._control_mode is ControlMode.TWIST_RAW:
                yaw_rate = input_yaw_rate
            elif (
                self._target_steering is not None
                and self._target_steering_rx is not None
                and self._elapsed_ms(self._target_steering_rx, now)
                <= self._target_steering_timeout_ms
            ):
                steering = self._target_steering
            if (
                self._target_gear_rx is not None
                and self._elapsed_ms(self._target_gear_rx, now) <= 5000
            ):
                gear = self._target_gear
        return ControlCommand(
            session_id=self._session_id,
            owner_id=self._owner_id,
            enable=enable,
            emergency_stop=emergency_stop,
            mode=self._control_mode,
            gear=gear,
            validity_ms=self._command_validity_ms,
            target_speed_mps=speed,
            target_yaw_rate_rps=yaw_rate,
            target_steering_rad=steering,
        )

    def _wire_status(self, now: float) -> GatewayStatus:
        return GatewayStatus(
            session_id=self._session_id,
            state=self._gateway_state,
            last_rx_age_ms=self._age_ms(self._last_rx, now),
            last_tx_age_ms=self._age_ms(self._last_tx, now),
            rx_sequence=self._rx_state_sequence,
            tx_sequence=self._tx_control_sequence,
            dropped_packets=self._counters['dropped_packets'],
            malformed_packets=self._counters['malformed_packets'],
            stale_packets=self._counters['stale_packets'],
            out_of_order_packets=self._counters['out_of_order_packets'],
        )

    def _send_message(self, message: object, message_type: MessageType) -> None:
        sequence = self._sequences[message_type]
        self._sequences[message_type] = (sequence + 1) & 0xFFFFFFFF
        try:
            datagram = encode_message(message, sequence)
            self._udp.sendto(datagram, (self._peer_ip, self._peer_port))
            now = time.monotonic()
            self._last_tx = now
            if message_type is MessageType.CONTROL_COMMAND:
                self._tx_control_sequence = sequence
        except (OSError, ProtocolError) as exc:
            self._counters['dropped_packets'] += 1
            self._fatal_error = str(exc)

    def _update_status(self, now: float) -> None:
        ready, estop_active = self._command_ready(now)
        if estop_active:
            self._gateway_state = GatewayState.ESTOP
            return
        if self._fatal_error:
            self._gateway_state = GatewayState.FAULT
            return
        if self._peer_session_id is None:
            if self._elapsed_ms(self._started_monotonic, now) >= self._connect_timeout_ms:
                self._gateway_state = GatewayState.DISCONNECTED
            else:
                self._gateway_state = GatewayState.WAITING
            return
        peer_fresh = (
            self._peer_heartbeat_rx is not None
            and self._peer_state_rx is not None
            and self._elapsed_ms(self._peer_heartbeat_rx, now) <= self._peer_timeout_ms
            and self._elapsed_ms(self._peer_state_rx, now) <= self._state_timeout_ms
        )
        if not peer_fresh:
            self._gateway_state = GatewayState.STALE
        elif (
            ready
            and self._peer_status is not None
            and self._peer_status_rx is not None
            and self._elapsed_ms(self._peer_status_rx, now) <= self._peer_timeout_ms * 2
            and self._peer_status.state is GatewayState.ACTIVE
        ):
            self._gateway_state = GatewayState.ACTIVE
        elif (
            self._peer_status is not None
            and self._peer_status.state is GatewayState.ESTOP
        ):
            self._gateway_state = GatewayState.ESTOP
        elif (
            self._peer_status is not None
            and self._peer_status.state is GatewayState.FAULT
        ):
            self._gateway_state = GatewayState.FAULT
        elif (
            self._ever_enabled
            and self._cmd_vel_rx is not None
            and self._elapsed_ms(self._cmd_vel_rx, now) > self._cmd_vel_timeout_ms
        ):
            self._gateway_state = GatewayState.STALE
        else:
            self._gateway_state = GatewayState.WAITING

    def _publish_diagnostic(self, now: float) -> None:
        status = DiagnosticStatus()
        status.name = 'cleannav_vehicle_gateway'
        status.hardware_id = 'NET-OFFLINE-V1'
        status.message = self._gateway_state.name
        if self._gateway_state in (GatewayState.FAULT, GatewayState.ESTOP):
            status.level = DiagnosticStatus.ERROR
        elif self._gateway_state in (GatewayState.STALE, GatewayState.DISCONNECTED):
            status.level = DiagnosticStatus.STALE
        elif self._gateway_state is GatewayState.ACTIVE:
            status.level = DiagnosticStatus.OK
        else:
            status.level = DiagnosticStatus.WARN

        values = {
            'state': self._gateway_state.name,
            'offline_test_mode': str(self._offline_test_mode).lower(),
            'peer_role': self._peer_role.name if self._peer_role else 'UNKNOWN',
            'owner_id': self._owner_id,
            'session_id': str(self._session_id),
            'last_rx_age_ms': str(self._age_ms(self._last_rx, now)),
            'last_tx_age_ms': str(self._age_ms(self._last_tx, now)),
            'rx_sequence': str(self._rx_state_sequence),
            'tx_sequence': str(self._tx_control_sequence),
            **{key: str(value) for key, value in self._counters.items()},
            'error': self._fatal_error,
        }
        status.values = [
            KeyValue(key=key, value=value) for key, value in values.items()
        ]
        self._status_pub.publish(status)

    def _elapsed_ms(self, start: float, now: float) -> int:
        return max(0, int((now - start) * 1000))

    def _age_ms(self, value: float | None, now: float) -> int:
        if value is None:
            return 0xFFFFFFFF
        return min(0xFFFFFFFF, self._elapsed_ms(value, now))

    def destroy_node(self):
        try:
            self._udp.close()
        finally:
            return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = J6MVehicleGatewayNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

