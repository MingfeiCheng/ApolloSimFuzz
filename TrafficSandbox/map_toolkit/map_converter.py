import copy
import json
import os.path

import pickle
import networkx as nx

from loguru import logger
from typing import List, Dict
from collections import defaultdict
from shapely.geometry import LineString

from .junction import JunctionManager
from .crosswalk import CrosswalkManager
from .road_lane import RoadLaneManager
from .stop_sign import StopSignManager
from .traffic_light import TrafficLightManager

class MapLoader(object):

    def __init__(self):
        self.junction = JunctionManager()
        self.crosswalk = CrosswalkManager()
        self.lane = RoadLaneManager()
        self.stop_sign = StopSignManager()
        self.traffic_light = TrafficLightManager()
        
    def reset(self):
        self.junction = JunctionManager()
        self.crosswalk = CrosswalkManager()
        self.lane = RoadLaneManager()
        self.stop_sign = StopSignManager()
        self.traffic_light = TrafficLightManager()

    def parse_from_source(self, source_file: str):

        def __is_overlap(obj1, obj2):
            """
            Check if 2 objects (e.g., lanes, junctions) have overlap

            :param any obj1: left hand side
            :param any obj2: right hand side
            """
            oid1 = set([x.id for x in obj1.overlap_id])
            oid2 = set([x.id for x in obj2.overlap_id])
            return oid1 & oid2 != set()

        def __is_conflict_lanes(lane_id1: List[str], lane_id2: List[str]) -> bool:
            """
            Check if 2 groups of lanes intersect with each other

            :param List[str] lane_id1: list of lane ids
            :param List[str] lane_id2: another list of lane ids

            :returns: True if at least 1 lane from lhs intersects with another from rhs,
                False otherwise.
            :rtype: bool
            """
            for lid1 in lane_id1:
                for lid2 in lane_id2:
                    if lid1 == lid2:
                        continue
                    lane1 = LineString(self.lane.get_central_curve(lid1))
                    lane2 = LineString(self.lane.get_central_curve(lid2))
                    if lane1.intersects(lane2):
                        return True
            return False

        from apollo_modules.modules.map.proto.map_pb2 import Map

        logger.info(f"Load map from source: {source_file}")

        __map = Map()
        f = open(source_file, 'rb')
        __map.ParseFromString(f.read())
        f.close()

        # 1. load crosswalk
        crosswalk = dict()
        for cw in __map.crosswalk:
            crosswalk[cw.id.id] = cw
        self.crosswalk.setup(crosswalk)
        logger.info("-> Load crosswalks")

        # 2. load junctions
        junctions = dict()
        for junc in __map.junction:
            junctions[junc.id.id] = junc

        # 3. load lanes
        lanes = dict()
        lanes_junction_flags = dict()
        for l_index, l in enumerate(__map.lane):
            lanes[l.id.id] = l
            lanes_junction_flags[l.id.id] = False

        # 4. stop signs
        stop_signs = dict()
        for ss in __map.stop_sign:
            stop_signs[ss.id.id] = ss
        self.stop_sign.setup(stop_signs)
        logger.info("-> Load stop sign")

        # 5. traffic light
        traffic_lights = dict()
        for sig in __map.signal:
            traffic_lights[sig.id.id] = sig

        # 6. junction parse
        # 7.1 junc -> lanes
        junction_lanes = defaultdict(list)  # key: junction_id value: lane
        for lank, lanv in lanes.items():
            for junk, junv in junctions.items():
                if __is_overlap(lanv, junv):
                    junction_lanes[junk].append(lank)
                    if lank in lanes_junction_flags:
                        lanes_junction_flags[lank] = True
                    else:
                        logger.warning(f"lane {lank} not found in lanes_junction_flags, please confirm")

        # 7.2 junc -> traffic lights
        junction_traffic_light = defaultdict(list)
        for sigk, sigv in traffic_lights.items():
            for junk, junv in junctions.items():
                if __is_overlap(sigv, junv):
                    junction_traffic_light[junk].append(sigk)
        self.junction.setup(junctions, junction_lanes, junction_traffic_light)
        logger.info("-> Load junctions")

        # 7. lane parse
        # 7.1 lane stop sign
        lanes_stop_sign = defaultdict(list) # key: lane_id value: stop sign
        for lank, lanv in lanes.items():
            for ss, ssv in stop_signs.items():
                if __is_overlap(lanv, ssv):
                    lanes_stop_sign[lank].append(ss)
        # 6.2 lane traffic light
        lanes_traffic_light = defaultdict(list)
        for lank, lanv in lanes.items():
            for sigk, sigv in traffic_lights.items():
                if __is_overlap(lanv, sigv):
                    lanes_traffic_light[lank].append(sigk)
        self.lane.setup(lanes, lanes_stop_sign, lanes_traffic_light, lanes_junction_flags)
        logger.info("-> Load lanes")

        # 8. traffic light
        # 8.1 traffic controlled by signals
        traffic_light_lanes = defaultdict(list)
        for junk, junv in junctions.items():
            signal_ids = junction_traffic_light[junk]
            lane_ids = junction_lanes[junk]
            for sid in signal_ids:
                for lid in lane_ids:
                    if __is_overlap(traffic_lights[sid], lanes[lid]):
                        traffic_light_lanes[sid].append(lid)

        # 8.2 traffic light relation
        traffic_light_relation = nx.Graph()
        for junk, junv in junctions.items():
            signal_ids = junction_traffic_light[junk] # why empty?
            for sid1 in signal_ids:

                traffic_light_relation.add_node(sid1)
                for sid2 in signal_ids:
                    if sid1 == sid2:
                        continue
                    lg1 = traffic_light_lanes[sid1]
                    lg2 = traffic_light_lanes[sid2]
                    if lg1 == lg2:
                        traffic_light_relation.add_edge(sid1, sid2, v='EQ')
                    elif __is_conflict_lanes(lg1, lg2):
                        traffic_light_relation.add_edge(sid1, sid2, v='NE')
                    else:
                        traffic_light_relation.add_edge(sid1, sid2, v='UNKNOWN')

        self.traffic_light.setup(traffic_lights, traffic_light_relation, traffic_light_lanes)
        logger.info("-> Load traffic light")


    def get_render_data(self) -> Dict:
        render_data = {
            "lanes": [],
            "stop_signs": []
        }

        lanes = []
        for lane_id in self.lane.get_all():
            lane_info = {
                'id': lane_id,
                'type': self.lane.get_type(lane_id),
                'central': self.lane.get_central_curve(lane_id),
                'left_boundary': self.lane.get_left_boundary_curve(lane_id),
                'right_boundary': self.lane.get_right_boundary_curve(lane_id),
                'left_boundary_type': self.lane.get_left_boundary_type(lane_id),
                'right_boundary_type': self.lane.get_right_boundary_type(lane_id),
                'polygon': self.lane.get_polygon(lane_id)
            }
            lanes.append(lane_info)
        render_data["lanes"] = lanes

        # 3. Stop signs
        for ss_id in self.stop_sign.get_all():
            render_data["stop_signs"].append({
                "id": ss_id,
                "stop_line": self.stop_sign.get_line(ss_id)
            })

        return render_data

    def export(self, file_folder: str):
        render_data = self.get_render_data()

        # 1. first one is for backend
        backend_dict = copy.deepcopy(self.__dict__)
        for k, v in backend_dict.items():
            backend_dict[k] = v.export()
        back_file = os.path.join(file_folder, 'map.pickle')
        with open(back_file, "wb") as f:
            pickle.dump(backend_dict, f)

        # 2. second one is for front
        vis_file_path = os.path.join(file_folder, 'map.json')
        with open(vis_file_path, 'w') as f:
            json.dump(render_data, f, indent=4)

        logger.info(f"Render data saved to {vis_file_path}")