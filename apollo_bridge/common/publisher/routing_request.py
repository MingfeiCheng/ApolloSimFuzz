from apollo_modules.modules.common.proto.header_pb2 import Header
from apollo_modules.modules.common.proto.geometry_pb2 import PointENU
from apollo_modules.modules.routing.proto.routing_pb2 import LaneWaypoint, RoutingRequest

from apollo_bridge.common.format import RouteMessage
from .base import Publisher
from registry import PUBLISHER_REGISTRY

@PUBLISHER_REGISTRY.register('publisher.routing_request')
class RoutingRequestPublisher(Publisher):
    # this is old version, has been updated in the new version -> /apollo/external_command/lane_follow
    channel: str = '/apollo/routing_request'
    msg_type: str = 'apollo.routing.RoutingRequest'
    msg_cls: any = RoutingRequest

    def __init__(self, idx, bridge):
        super(RoutingRequestPublisher, self).__init__(idx, bridge)
        self.route = None

    def _process_data(self, message: RouteMessage):
        """
        Send the instance's routing request to cyberRT
        """
        self.route = message.waypoints

        # waypoints
        routeing_waypoints = [
            LaneWaypoint(
                pose=PointENU(
                    x=self.route[0].location.x,
                    y=self.route[0].location.y
                ),
                heading=self.route[0].location.yaw
            )
        ]
        for wp in self.route:
            routeing_waypoints.append(
                LaneWaypoint(
                    id=wp.lane.id,
                    s=wp.lane.s
                )
            )

        rr = RoutingRequest(
            header=Header(
                timestamp_sec=message.timestamp,
                module_name="MAGGIE",
                sequence_num=self.frame_count
            ),
            waypoint=routeing_waypoints,
        )

        return rr
