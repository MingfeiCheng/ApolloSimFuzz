from apollo_modules.modules.perception.proto.traffic_light_detection_pb2 import TrafficLight, TrafficLightDetection

from apollo_bridge.common.format import PerfectTrafficLightMessage
from .base import Publisher
from registry import PUBLISHER_REGISTRY

@PUBLISHER_REGISTRY.register('publisher.perfect_traffic_light')
class PerfectTrafficLightPublisher(Publisher):

    channel: str = '/apollo/perception/traffic_light'
    msg_type: str = 'apollo.perception.TrafficLightDetection'
    msg_cls: any = TrafficLightDetection
    frequency: float = 20.0

    def __init__(self, idx, bridge):
        super(PerfectTrafficLightPublisher, self).__init__(idx, bridge)

    def _process_data(self, message: PerfectTrafficLightMessage):
        # traffic light
        # TODO: Why not stable publish to the apollo?
        tld = TrafficLightDetection()
        tld.header.timestamp_sec = message.timestamp
        tld.header.module_name = "MAGGIE"  # "MAGGIE"
        tld.header.sequence_num = self.frame_count
        for tl_state in message.traffic_lights:
            tl = tld.traffic_light.add()
            tl.id = tl_state.id
            tl.confidence = 1
            if tl_state.state == "green":
                tl.color = TrafficLight.Color.GREEN
            elif tl_state.state == "yellow":
                tl.color = TrafficLight.Color.YELLOW
            elif tl_state.state == "red":
                tl.color = TrafficLight.Color.RED
            elif tl_state.state == "unknown":
                tl.color = TrafficLight.Color.BLACK
            else:
                tl.color = TrafficLight.Color.UNKNOWN

        return tld