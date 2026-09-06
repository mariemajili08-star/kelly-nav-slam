from setuptools import setup
import os
from glob import glob

package_name = 'kelly_nav'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='etudiant',
    maintainer_email='etudiant@example.com',
    description='Adaptation du critere de Kelly pour la navigation adaptative au risque (SLAM + Nav2)',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'kelly_monitor_node = kelly_nav.kelly_monitor_node:main',
        ],
    },
)
