import os
from glob import glob

from setuptools import find_packages, setup

package_name = "mobile_sensor_logger"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages",
         [os.path.join("resource", package_name)]),
        (os.path.join("share", package_name), ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Abhiram B",
    maintainer_email="rakshithadevaraja28@gmail.com",
    description="ROS 2 publisher nodes wrapping the mobile multi-sensor logger drivers.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "gps_node = mobile_sensor_logger.gps_node:main",
            "imu_node = mobile_sensor_logger.imu_node:main",
            "camera_node = mobile_sensor_logger.camera_node:main",
        ],
    },
)
