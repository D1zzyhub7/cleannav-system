"""ROS 2 + UDP integration tests confined to 127.0.0.1."""

from __future__ import annotations

import os
import socket
import threading
import time

os.environ['ROS_LOCALHOST_ONLY'] = '1'

import pytest
import rclpy
from cleannav_interfaces.msg import SafetyStatus
from diagnostic_msgs.msg import DiagnosticStatus
from geometry_msgs.msg import Twist
from rclpy.executors import MultiThreadedExecutor
from rclpy.parameter import Parameter
from std_msgs.msg import Bool, Float64
from std_srvs.srv import SetBool

from cleannav_safety_supervisor.safety_supervisor_node import SafetySupervisorNode
from cleannav_vehicle_gateway.j6m_gateway_node import J6MVehicleGatewayNode
from cleannav_vehicle_gateway.mock_autoware_gateway import (
    MockAutowareGateway,
    MockFaults,
)
from cleannav_vehicle_gateway.protocol import GatewayState


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.bind(('127.0.0.1', 0))
        return int(udp.getsockname()[1])


def _gateway_node(bind_port: int, peer_port: int, **overrides):
    params = {
        'bind_ip': '127.0.0.1',
        'bind_port': bind_port,
        'peer_ip': '127.0.0.1',
        'peer_port': peer_port,
        'offline_test_mode': True,
        'control_mode': 0,
        'cmd_vel_timeout_ms': 350,
        'safety_status_timeout_ms': 1500,
        'peer_timeout_ms': 450,
        'state_timeout_ms': 1000,
        'command_validity_ms': 300,
        'safe_burst_ms': 300,
        'control_period_ms': 50,
        'status_period_ms': 100,
    }
    params.update(overrides)
    parameters = [
        Parameter(name, value=value) for name, value in params.items()
    ]
    return J6MVehicleGatewayNode(parameter_overrides=parameters)


def _start_executor(*nodes):
    executor = MultiThreadedExecutor(num_threads=3)
    for node in nodes:
        executor.add_node(node)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    return executor, thread


def _stop_stack(executor, thread, mock, nodes):
    if mock is not None:
        mock.stop()
    if executor is not None:
        executor.shutdown(timeout_sec=2.0)
    if thread is not None:
        thread.join(timeout=2.0)
    for node in nodes:
        if node is not None:
            node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


def test_ros2_safety_gateway_mock_vehicle_state_loopback():
    rclpy.init()
    j6_port = _free_loopback_port()
    mock_port = _free_loopback_port()
    while mock_port == j6_port:
        mock_port = _free_loopback_port()

    mock = MockAutowareGateway(
        bind_ip='127.0.0.1',
        bind_port=mock_port,
        peer_ip='127.0.0.1',
        peer_port=j6_port,
    )
    safety = SafetySupervisorNode()
    safety._block_all = False
    safety._autonomous_timeout_sec = 30.0
    gateway = _gateway_node(j6_port, mock_port)
    harness = rclpy.create_node('vehicle_gateway_integration_harness')

    candidate_pub = harness.create_publisher(
        Twist, '/cleannav/cmd_vel_candidate', 10
    )
    estop_pub = harness.create_publisher(
        Bool, '/cleannav/safety/emergency_stop', 10
    )
    received_speed: list[float] = []
    diagnostics: list[DiagnosticStatus] = []
    harness.create_subscription(
        Float64,
        '/cleannav/vehicle/speed',
        lambda msg: received_speed.append(float(msg.data)),
        10,
    )
    harness.create_subscription(
        DiagnosticStatus,
        '/cleannav/vehicle/gateway_status',
        diagnostics.append,
        10,
    )

    mock.start()
    executor, thread = _start_executor(safety, gateway, harness)
    nodes = (safety, gateway, harness)
    try:
        request = SetBool.Request()
        request.data = True
        response = safety._autonomous_srv_cb(request, SetBool.Response())
        assert response.success

        command = Twist()
        command.linear.x = 0.03
        command.angular.z = 0.0
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            candidate_pub.publish(command)
            if (
                any(speed > 0.01 for speed in received_speed)
                and any(item.message == 'ACTIVE' for item in diagnostics)
            ):
                break
            time.sleep(0.05)

        assert any(speed > 0.01 for speed in received_speed)
        assert any(item.message == 'ACTIVE' for item in diagnostics)
        assert mock.snapshot()['owner'] == 'OWNER_J6M'
        assert mock.snapshot()['local_address'][0] == '127.0.0.1'

        mock.send_malformed()
        malformed_deadline = time.monotonic() + 1.0
        while time.monotonic() < malformed_deadline:
            if any(
                any(
                    item.key == 'malformed_packets' and int(item.value) >= 1
                    for item in status.values
                )
                for status in diagnostics
            ):
                break
            time.sleep(0.02)
        assert any(
            any(
                item.key == 'malformed_packets' and int(item.value) >= 1
                for item in status.values
            )
            for status in diagnostics
        )

        estop_pub.publish(Bool(data=True))
        estop_deadline = time.monotonic() + 2.0
        while time.monotonic() < estop_deadline:
            if (
                mock.snapshot()['emergency_latched']
                and any(
                    item.message == GatewayState.ESTOP.name
                    for item in diagnostics
                )
            ):
                break
            time.sleep(0.02)
        assert mock.snapshot()['emergency_latched'] is True
        assert any(item.message == GatewayState.ESTOP.name for item in diagnostics)
    finally:
        _stop_stack(executor, thread, mock, nodes)


def test_stale_ros_command_releases_mock_owner_and_marks_stale():
    rclpy.init()
    j6_port = _free_loopback_port()
    mock_port = _free_loopback_port()
    while mock_port == j6_port:
        mock_port = _free_loopback_port()

    mock = MockAutowareGateway(
        bind_ip='127.0.0.1',
        bind_port=mock_port,
        peer_ip='127.0.0.1',
        peer_port=j6_port,
    )
    gateway = _gateway_node(j6_port, mock_port)
    harness = rclpy.create_node('vehicle_gateway_stale_cmd_harness')
    safety_pub = harness.create_publisher(
        SafetyStatus, '/cleannav/safety_status', 10
    )
    cmd_pub = harness.create_publisher(Twist, '/cmd_vel', 10)
    diagnostics: list[DiagnosticStatus] = []
    harness.create_subscription(
        DiagnosticStatus,
        '/cleannav/vehicle/gateway_status',
        diagnostics.append,
        10,
    )
    safety_status = SafetyStatus()
    safety_status.interface_version = '1.1'
    safety_status.autonomous_enabled = True
    safety_status.block_all = False
    command = Twist()
    command.linear.x = 0.03

    mock.start()
    executor, thread = _start_executor(gateway, harness)
    nodes = (gateway, harness)
    try:
        active_deadline = time.monotonic() + 2.0
        while time.monotonic() < active_deadline:
            safety_pub.publish(safety_status)
            cmd_pub.publish(command)
            if mock.snapshot()['owner'] == 'OWNER_J6M':
                break
            time.sleep(0.02)
        assert mock.snapshot()['owner'] == 'OWNER_J6M'

        stale_deadline = time.monotonic() + 2.0
        while time.monotonic() < stale_deadline:
            safety_pub.publish(safety_status)
            if (
                mock.snapshot()['owner'] == 'OWNER_NONE'
                and any(
                    item.message == GatewayState.STALE.name
                    for item in diagnostics
                )
            ):
                break
            time.sleep(0.02)
        assert mock.snapshot()['owner'] == 'OWNER_NONE'
        assert any(item.message == GatewayState.STALE.name for item in diagnostics)
    finally:
        _stop_stack(executor, thread, mock, nodes)


def test_peer_disconnect_marks_gateway_stale():
    rclpy.init()
    j6_port = _free_loopback_port()
    mock_port = _free_loopback_port()
    while mock_port == j6_port:
        mock_port = _free_loopback_port()

    mock = MockAutowareGateway(
        bind_ip='127.0.0.1',
        bind_port=mock_port,
        peer_ip='127.0.0.1',
        peer_port=j6_port,
        faults=MockFaults(),
    )
    gateway = _gateway_node(j6_port, mock_port)
    harness = rclpy.create_node('vehicle_gateway_disconnect_harness')
    diagnostics: list[DiagnosticStatus] = []
    harness.create_subscription(
        DiagnosticStatus,
        '/cleannav/vehicle/gateway_status',
        diagnostics.append,
        10,
    )
    mock.start()
    executor, thread = _start_executor(gateway, harness)
    nodes = (gateway, harness)
    try:
        ready_deadline = time.monotonic() + 2.0
        while time.monotonic() < ready_deadline:
            if gateway._peer_state is not None:
                break
            time.sleep(0.02)
        assert gateway._peer_state is not None

        mock.stop()
        stale_deadline = time.monotonic() + 2.0
        while time.monotonic() < stale_deadline:
            if any(item.message == GatewayState.STALE.name for item in diagnostics):
                break
            time.sleep(0.02)
        assert any(item.message == GatewayState.STALE.name for item in diagnostics)
    finally:
        _stop_stack(executor, thread, mock, nodes)


def test_offline_mode_rejects_non_loopback_configuration():
    rclpy.init()
    try:
        with pytest.raises(ValueError, match='127.0.0.1'):
            _gateway_node(
                39181,
                39182,
                peer_ip='192.0.2.10',
                offline_test_mode=True,
            )
    finally:
        if rclpy.ok():
            rclpy.shutdown()



def test_sender_wall_clock_skew_does_not_invalidate_fresh_state():
    rclpy.init()
    j6_port = _free_loopback_port()
    mock_port = _free_loopback_port()
    while mock_port == j6_port:
        mock_port = _free_loopback_port()

    mock = MockAutowareGateway(
        bind_ip='127.0.0.1',
        bind_port=mock_port,
        peer_ip='127.0.0.1',
        peer_port=j6_port,
        faults=MockFaults(timestamp_offset_ms=-86_400_000),
    )
    gateway = _gateway_node(j6_port, mock_port)
    harness = rclpy.create_node('vehicle_gateway_skewed_clock_harness')
    received_speed: list[float] = []
    harness.create_subscription(
        Float64,
        '/cleannav/vehicle/speed',
        lambda msg: received_speed.append(float(msg.data)),
        10,
    )
    mock.start()
    executor, thread = _start_executor(gateway, harness)
    nodes = (gateway, harness)
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if gateway._peer_state is not None and received_speed:
                break
            time.sleep(0.02)
        assert gateway._peer_state is not None
        assert gateway._counters['stale_packets'] == 0
        assert received_speed
    finally:
        _stop_stack(executor, thread, mock, nodes)
