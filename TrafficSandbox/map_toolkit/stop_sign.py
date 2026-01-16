import copy

from typing import Optional, Dict, List

from apollo_modules.modules.map.proto.map_stop_sign_pb2 import StopSign

from common.rpc_utils import sandbox_api


class StopSignManager(object):

    def __init__(self, stop_sign: Optional[Dict[str, StopSign]] = None):
        self.stop_sign = stop_sign

    def setup(self, stop_sign: Dict[str, StopSign]):
        self.stop_sign = stop_sign

    def export(self):
        save_data = {
            'stop_sign': copy.deepcopy(self.stop_sign)
        }
        for k, y in save_data['stop_sign'].items():
            save_data['stop_sign'][k] = y.SerializeToString()
        return save_data

    def load(self, data: Dict):
        self.stop_sign = {}
        for k, y in data['stop_sign'].items():
            ss = StopSign()
            ss.ParseFromString(y)
            self.stop_sign[k] = ss

    @sandbox_api("get_all")
    def get_all(self) -> List[str]:
        return list(self.stop_sign.keys())

    @sandbox_api("get_line")
    def get_line(self, ss_id: str) -> List[List[float]]:
        ss = self.stop_sign[ss_id]
        ss_line_points = ss.stop_line[0].segment[0].line_segment
        line_coords = []
        for point in ss_line_points.point:
            line_coords.append([point.x, point.y])
        return line_coords
    
    # not visible in RPC
    def get(self, ss_id: str) -> StopSign:
        """
        Get a specific stop sign object based on ID

        :param str ss_id: ID of the stop sign interested in

        :returns: stop sign object
        :rtype: StopSign
        """
        return self.stop_sign[ss_id]