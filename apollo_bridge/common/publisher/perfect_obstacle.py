from apollo_modules.modules.common.proto.header_pb2 import Header

from apollo_modules.modules.common.proto.geometry_pb2 import Point3D, PointENU
from apollo_modules.modules.perception.proto.perception_obstacle_pb2 import PerceptionObstacle, PerceptionObstacles

from apollo_bridge.common.format import PerfectObstacleMessage
from .base import Publisher
from registry import PUBLISHER_REGISTRY

from loguru import logger

@PUBLISHER_REGISTRY.register('publisher.perfect_obstacle')
class PerfectObstaclePublisher(Publisher):

    channel: str = '/apollo/perception/obstacles'
    msg_type: str = 'apollo.perception.PerceptionObstacles'
    msg_cls: any = PerceptionObstacles
    frequency: float = 20.0

    def __init__(self, idx, bridge):
        super(PerfectObstaclePublisher, self).__init__(idx, bridge)

    def _process_data(self, message: PerfectObstacleMessage):
        # obstacle
        timestamp = message.timestamp
        apollo_perception = list()
        # logger.debug(f"[PerfectObstaclePublisher] Processing PerfectObstacleMessage at timestamp {timestamp}, frame {self.frame_count}, number of obstacles: {len(message.obstacles)}")
        for obs_actor in message.obstacles:
            if obs_actor.id == self.idx:
                continue
            loc = PointENU(x=obs_actor.location.x, y=obs_actor.location.y, z=obs_actor.location.z)
            position = Point3D(x=loc.x, y=loc.y, z=loc.z)
            velocity = Point3D(
                x=obs_actor.velocity.x,
                y=obs_actor.velocity.y,
                z=obs_actor.velocity.z
            )

            apollo_points = []  # Apollo Points
            for x, y in obs_actor.bbox_points:
                p = Point3D()
                p.x = x
                p.y = y
                p.z = 0.0
                apollo_points.append(p)

            if obs_actor.category == 'vehicle':
                obs_type = PerceptionObstacle.VEHICLE
            elif obs_actor.category == 'bicycle':
                obs_type = PerceptionObstacle.BICYCLE
            elif obs_actor.category == 'walker':
                obs_type = PerceptionObstacle.PEDESTRIAN
            elif obs_actor.category == 'static':
                obs_type = PerceptionObstacle.UNKNOWN_UNMOVABLE
            else:
                obs_type = PerceptionObstacle.UNKNOWN

            obs = PerceptionObstacle(
                id=obs_actor.id,
                position=position,
                theta=obs_actor.location.yaw,
                velocity=velocity,
                acceleration=Point3D(x=0, y=0, z=0),
                length=obs_actor.length,
                width=obs_actor.width,
                height=obs_actor.height,
                type=obs_type,
                timestamp=timestamp,
                tracking_time=1.0,
                polygon_point=apollo_points
            )
            apollo_perception.append(obs)

        header = Header(
            timestamp_sec=message.timestamp,
            module_name='MAGGIE',
            sequence_num=self.frame_count
        )
        perception_obstacles_bag = PerceptionObstacles(
            header=header,
            perception_obstacle=apollo_perception,
        )

        return perception_obstacles_bag