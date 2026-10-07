from glob import glob

from setuptools import find_packages, setup


package_name = 'cleannav_vehicle_gateway'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='CleanNav Team',
    maintainer_email='d1zzy@example.com',
    description='Offline-first J6M to Autoware vehicle gateway',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'j6m_vehicle_gateway = '
            'cleannav_vehicle_gateway.j6m_gateway_node:main',
            'mock_autoware_gateway = '
            'cleannav_vehicle_gateway.mock_autoware_gateway:main',
        ],
    },
)
