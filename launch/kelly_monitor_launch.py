from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    apply_to_nav2 = DeclareLaunchArgument(
        'apply_to_nav2', default_value='true',
        description='Si true, modifie en direct les parametres Nav2 (vitesse max, inflation). '
                    'Si false, calcule et publie seulement (utile pour un premier test / comparaison).'
    )
    v_nominal_max = DeclareLaunchArgument('v_nominal_max', default_value='0.5')
    kelly_b = DeclareLaunchArgument('kelly_b', default_value='1.5')

    node = Node(
        package='kelly_nav',
        executable='kelly_monitor_node',
        name='kelly_monitor_node',
        output='screen',
        parameters=[{
            'apply_to_nav2': LaunchConfiguration('apply_to_nav2'),
            'v_nominal_max': LaunchConfiguration('v_nominal_max'),
            'kelly_b': LaunchConfiguration('kelly_b'),
        }]
    )

    return LaunchDescription([apply_to_nav2, v_nominal_max, kelly_b, node])
