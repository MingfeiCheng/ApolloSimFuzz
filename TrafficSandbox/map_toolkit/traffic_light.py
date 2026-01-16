import copy

import networkx as nx

from typing import Optional, Dict, List, Tuple

from apollo_modules.modules.map.proto.map_signal_pb2 import Signal

from common.rpc_utils import sandbox_api

class TrafficLightManager(object):

    def __init__(
        self,
        traffic_light: Optional[Dict[str, Signal]] = None,
        traffic_light_relations: Optional[nx.Graph] = None,
        traffic_light_lanes: Optional[Dict[str, str]] = None
    ):
        self.traffic_light = traffic_light
        self.traffic_light_relations = traffic_light_relations
        self.traffic_light_lanes = traffic_light_lanes

    def setup(
        self,
        traffic_light: Dict[str, Signal],
        traffic_light_relations: nx.Graph,
        traffic_light_lanes: Dict[str, str]
    ):
        self.traffic_light = traffic_light
        self.traffic_light_relations = traffic_light_relations
        self.traffic_light_lanes = traffic_light_lanes

    def export(self):
        save_data = {
            'traffic_light': copy.deepcopy(self.traffic_light),
            'traffic_light_relations': copy.deepcopy(self.traffic_light_relations),
            'traffic_light_lanes': copy.deepcopy(self.traffic_light_lanes)
        }
        for k, y in save_data['traffic_light'].items():
            # print(save_data['traffic_light'][k].stop_line[0].segment[0].line_segment)
            save_data['traffic_light'][k] = y.SerializeToString()
        return save_data

    def load(self, data: Dict):
        self.traffic_light = {}
        for k, y in data['traffic_light'].items():
            tl = Signal()
            tl.ParseFromString(y)
            self.traffic_light[k] = tl
        self.traffic_light_relations = data['traffic_light_relations']
        self.traffic_light_lanes = data['traffic_light_lanes']

    @sandbox_api("get_all")
    def get_all(self) -> List[str]:
        return list(self.traffic_light.keys())

    @sandbox_api("get_stop_line")
    def get_stop_line(self, ss_id: str) -> List[List[float]]:
        """
        Get the lane id associated with the stop sign

        :param str ss_id: ID of the stop sign interested in

        :returns: lane id
        :rtype: str
        """
        stop_line = self.traffic_light[ss_id].stop_line[0].segment[0].line_segment
        curve_coords = []
        for point in stop_line.point:
            curve_coords.append([point.x, point.y])
        return curve_coords

    @sandbox_api("get_related_lights")
    def get_related_lights(self, ss_id: str) -> Tuple[List[str], List[str]]:
        """
        Get the lane id associated with the stop sign.

        :param ss_id: ID of the stop sign interested in
        :returns: A tuple with two lists: conflicted lights and equal lights
        """
        conflicted_lights, equal_lights = [], []

        if ss_id not in self.traffic_light_relations:
            # TODO: check this on sunnyvale_loop map -> has different algorithms
            return conflicted_lights, equal_lights

        for neighbor, attributes in self.traffic_light_relations[ss_id].items():
            relation = attributes.get('v')
            if relation == 'NE':
                conflicted_lights.append(neighbor)
            elif relation == 'EQ':
                equal_lights.append(neighbor)

        return conflicted_lights, equal_lights
    
    def get(self, ss_id: str) -> Signal:
        """
        Get a specific stop sign object based on ID

        :param str ss_id: ID of the stop sign interested in

        :returns: stop sign object
        :rtype: StopSign
        """
        return self.traffic_light[ss_id]