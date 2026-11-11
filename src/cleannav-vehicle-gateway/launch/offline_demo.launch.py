"""Run Safety, the J6M gateway and an Autoware mock using localhost only."""

from launch import LaunchDescription
from launch.actions import ExecuteProcess, SetEnvironmentVariable
from launch_ros.actions import Node


def generate_launch_description():
    safety = Node(
        package='cleannav_safety_supervisor',
        executable='safety_supervisor_node',
        name='cleannav_safety_supervisor',
        output='screen',
        parameters=[{
            'use_sim_time': False,
            'block_all': False,
            'publish_frequency': 10.0,
            'candidate_timeout_sec': 0.5,
            'autonomous_timeout_sec': 5.0,
        }],
    )
    gateway = Node(
        package='cleannav_vehicle_gateway',
        executable='j6m_vehicle_gateway',
        name='j6m_vehicle_gateway',
        output='screen',
        parameters=[{
            'use_sim_time': False,
            'offline_test_mode': True,
            'bind_ip': '127.0.0.1',
            'bind_port': 39181,
            'peer_ip': '127.0.0.1',
            'peer_port': 39182,
        }],
    )
    mock = ExecuteProcess(
        cmd=[
            'python3', '-m',
            'cleannav_vehicle_gateway.mock_autoware_gateway',
            '--bind-ip', '127.0.0.1',
            '--bind-port', '39182',
            '--peer-ip', '127.0.0.1',
            '--peer-port', '39181',
        ],
        output='screen',
    )
    return LaunchDescription([
        SetEnvironmentVariable('ROS_LOCALHOST_ONLY', '1'),
        safety,
        gateway,
        mock,
    ])

