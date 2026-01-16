import copy

from typing import List, Optional, Dict
from shapely.geometry import Polygon
from apollo_modules.modules.map.proto.map_junction_pb2 import Junction

from common.rpc_utils import sandbox_api


class JunctionManager(object):

    def __init__(
        self,
        junction: Optional[Dict[str, Junction]] = None,
        junction_lanes: Optional[Dict[str, str]] = None,
        junction_traffic_light: Optional[Dict[str, str]] = None
    ):
        self.junction = junction
        self.junction_lanes = junction_lanes
        self.junction_traffic_light = junction_traffic_light

    def setup(
        self,
        junction: Dict[str, Junction],
        junction_lanes: Dict[str, str],
        junction_traffic_light: Dict[str, str]
    ):
        self.junction = junction
        self.junction_lanes = junction_lanes
        self.junction_traffic_light = junction_traffic_light

    def export(self):
        save_data = {
            'junction': copy.deepcopy(self.junction),
            'junction_lanes': copy.deepcopy(self.junction_lanes),
            'junction_traffic_light': copy.deepcopy(self.junction_traffic_light)
        }
        for k, y in save_data['junction'].items():
            save_data['junction'][k] = y.SerializeToString()
        return save_data

    def load(self, data: Dict):
        self.junction = {}
        for k, y in data['junction'].items():
            junc = Junction()
            junc.ParseFromString(y)
            self.junction[k] = junc
        self.junction_lanes = data['junction_lanes']
        self.junction_traffic_light = data['junction_traffic_light']

    @sandbox_api("get_all")
    def get_all(self) -> List[str]:
        return list(self.junction.keys())

    @sandbox_api("get_polygon")
    def get_polygon(self, junc_id: str) -> List[List[float]]:
        junc = self.junction[junc_id]
        junc_polygon_points = junc.polygon.point
        polygon_coords = []
        for point in junc_polygon_points:
            polygon_coords.append([point.x, point.y])
        start_point = polygon_coords[0]
        polygon_coords.append(start_point)
        return polygon_coords

    @sandbox_api("get_traffic_light")
    def get_traffic_light(self, junc_id: str) -> str:
        return self.junction_traffic_light[junc_id]

    @sandbox_api("get_lane_ids")
    def get_lane_ids(self, junc_id: str) -> List[str]:
        if junc_id not in self.junction_lanes:
            return []
        return self.junction_lanes[junc_id]

    @sandbox_api("get_by_lane_id")
    def get_by_lane_id(self, lane_id):
        """
        Return the junction id where the lane in the junction
        """
        for k, v in self.junction_lanes.items():
            if lane_id in v:
                return k
        return None
    
    def get(self, junc_id: str) -> Junction:
        """
        Get a specific junction object based on ID

        :param str junc_id: ID of the junction interested in

        :returns: junction object
        :rtype: Junction
        """
        return self.junction[junc_id]