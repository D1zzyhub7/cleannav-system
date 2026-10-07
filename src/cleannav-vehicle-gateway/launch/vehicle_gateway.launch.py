"""Future vehicle launch skeleton; defaults remain loopback-only and fail closed."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    bind_ip = LaunchConfiguration('bind_ip')
    bind_port = LaunchConfiguration('bind_port')
    peer_ip = LaunchConfiguration('peer_ip')
    peer_port = LaunchConfiguration('peer_port')
    offline_test_mode = LaunchConfiguration('offline_test_mode')

    safety = Node(
        package='cleannav_safety_supervisor',
        executable='safety_supervisor_node',
        name='cleannav_safety_supervisor',
        output='screen',
        parameters=[{
            'use_sim_time': False,
            'block_all': True,
            'publish_frequency': 10.0,
            'candidate_timeout_sec': 0.5,
        }],
    )
    gateway = Node(
        package='cleannav_vehicle_gateway',
        executable='j6m_vehicle_gateway',
        name='j6m_vehicle_gateway',
        output='screen',
        parameters=[{
            'use_sim_time': False,
            'bind_ip': bind_ip,
            'bind_port': ParameterValue(bind_port, value_type=int),
            'peer_ip': peer_ip,
            'peer_port': ParameterValue(peer_port, value_type=int),
            'offline_test_mode': ParameterValue(
                offline_test_mode, value_type=bool
            ),
        }],
    )
    return LaunchDescription([
        SetEnvironmentVariable('ROS_LOCALHOST_ONLY', '1'),
        DeclareLaunchArgument(
            'bind_ip', default_value='127.0.0.1',
            description='OFFLINE_DEFAULT; replace only in a reviewed NET-1 profile',
        ),
        DeclareLaunchArgument(
            'bind_port', default_value='39181',
            description='OFFLINE_DEFAULT; not a hardware port allocation',
        ),
        DeclareLaunchArgument(
            'peer_ip', default_value='127.0.0.1',
            description='OFFLINE_DEFAULT; replace only in a reviewed NET-1 profile',
        ),
        DeclareLaunchArgument(
            'peer_port', default_value='39182',
            description='OFFLINE_DEFAULT; not a hardware port allocation',
        ),
        DeclareLaunchArgument(
            'offline_test_mode', default_value='true',
            description='Reject any non-loopback endpoint while true',
        ),
        safety,
        gateway,
    ])

