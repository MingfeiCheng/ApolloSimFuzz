import math
import numpy as np

from scipy.spatial.transform import Rotation

from apollo_modules.modules.common.proto.header_pb2 import Header
from apollo_modules.modules.common.proto.geometry_pb2 import Point3D, PointENU, Quaternion
from apollo_modules.modules.localization.proto.localization_pb2 import LocalizationEstimate
from apollo_modules.modules.localization.proto.pose_pb2 import Pose

from apollo_bridge.common.format import LocalizationMessage
from .base import Publisher

from registry import PUBLISHER_REGISTRY

def inverse_quaternion_rotate(orientation: Quaternion, vector: np.ndarray) -> np.ndarray:
    # Create a quaternion from the given orientation (w, x, y, z)
    quaternion = Rotation.from_quat([orientation.qx, orientation.qy, orientation.qz, orientation.qw])

    # Get the inverse of the rotation matrix
    rotation_matrix_inv = quaternion.inv().as_matrix()

    # Apply the inverse rotation to the vector
    transformed_vector = rotation_matrix_inv.dot(vector)

    return transformed_vector


def transform_to_vrf(point_mrf: Point3D, orientation: Quaternion) -> Point3D:
    v_mrf = np.array([point_mrf.x, point_mrf.y, point_mrf.z])
    # Rotate the vector using the inverse of the quaternion
    v_vrf = inverse_quaternion_rotate(orientation, v_mrf)
    # Set the transformed coordinates in point_vrf
    return Point3D(
        x=v_vrf[0],
        y=v_vrf[1],
        z=v_vrf[2],
    )

@PUBLISHER_REGISTRY.register('publisher.perfect_localization')
class PerfectLocalizationPublisher(Publisher):

    channel: str = '/apollo/localization/pose'
    msg_type: str = 'apollo.localization.LocalizationEstimate'
    msg_cls: any = LocalizationEstimate

    def __init__(self, idx, bridge):
        super(PerfectLocalizationPublisher, self).__init__(idx, bridge)

    def _process_data(self, message: LocalizationMessage):
        # convert state to apollo format
        # 1. position
        position = PointENU(
            x=message.location.x,
            y=message.location.y,
            z=message.location.z
        )
        # 2. heading
        heading = message.heading  # TODO: make sure the heading is in radian
        # 3. orientation
        # Adjust the heading as needed
        adjusted_heading = heading - (np.pi / 2)
        adjusted_heading = (adjusted_heading + math.pi) % (2 * math.pi) - math.pi
        # Create a rotation object from the adjusted heading
        rotation = Rotation.from_euler('z', adjusted_heading, degrees=False)
        # Extract quaternion components (x, y, z, w format)
        x, y, z, w = rotation.as_quat()
        orientation = Quaternion(
            qx=x, qy=y, qz=z, qw=w
        )
        # 4. linear_velocity
        linear_velocity = Point3D(
            x=message.velocity.x,
            y=message.velocity.y,
            z=message.velocity.z
        )
        # 5. linear_acceleration
        linear_acceleration = Point3D(
            x=message.acceleration.x,
            y=message.acceleration.y,
            z=message.acceleration.z
        )
        # 6. angular_velocity
        angular_velocity = Point3D(
            x=message.angular_velocity.x,
            y=message.angular_velocity.y,
            z=message.angular_velocity.z
        )

        # 7. linear_acceleration_vrf
        linear_acceleration_vrf = transform_to_vrf(linear_acceleration, orientation)

        # 8. angular_acceleration_vrf
        angular_velocity_vrf = transform_to_vrf(angular_velocity, orientation)

        loc = LocalizationEstimate(
            header=Header(
                timestamp_sec=message.timestamp,
                module_name="MAGGIE",
                sequence_num=self.frame_count
            ),
            pose=Pose(
                # 1. position
                position=position,
                # 2. heading
                heading=heading,
                # 3. orientation
                orientation=orientation,
                # 4. linear_velocity
                linear_velocity=linear_velocity,
                # 5. linear_acceleration
                linear_acceleration=linear_acceleration,
                # 6. angular_velocity
                angular_velocity=angular_velocity,
                # 7. linear_acceleration_vrf
                linear_acceleration_vrf=linear_acceleration_vrf,
                # 8. angular_acceleration_vrf
                angular_velocity_vrf=angular_velocity_vrf
            )
        )

        return loc