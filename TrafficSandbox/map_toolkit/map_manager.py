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
from .waypoint import Waypoint

from common.rpc_utils import sandbox_api

class MapManager(object):

    def __init__(self):
        self.map_name = None
        self.render_data = None
        self.junction = JunctionManager()
        self.crosswalk = CrosswalkManager()
        self.lane = RoadLaneManager()
        self.stop_sign = StopSignManager()
        self.traffic_light = TrafficLightManager()
        
    def reset(self):
        self.map_name = None
        self.render_data = None
        self.junction = JunctionManager()
        self.crosswalk = CrosswalkManager()
        self.lane = RoadLaneManager()
        self.stop_sign = StopSignManager()
        self.traffic_light = TrafficLightManager()
    
    def load_map(self, map_name: str):
        self.reset()
        
        if map_name == self.map_name and self.map_name is not None:
            logger.info(f"Map {map_name} already loaded, skip.")
            return
        
        self.map_name = map_name
        map_root_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        map_dir = os.path.join(map_root_dir, f"{map_name}")
        # load from file
        back_file = os.path.join(map_dir, 'map.pickle')
        with open(back_file, "rb") as f:
            backend_dict = pickle.load(f)

        for k, v in backend_dict.items():
            getattr(self, k).load(v)

        self.render_data = self.get_render_data()
        logger.info(f"Load map from {back_file}")
        
    @sandbox_api("get_current_map")
    def get_current_map(self) -> str:
        return self.map_name
    
    @sandbox_api("get_render_data")
    def get_render_data(self) -> Dict:
        render_data = {
            "map_name": self.map_name,
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
    
    ###### basic operators
    @sandbox_api("get_waypoint")
    def get_waypoint(self, lane_id: str, s: float, l: float) -> Dict:
        """
        Get a waypoint object based on lane id, s and l

        :param str lane_id: lane id
        :param float s: longitudinal distance along the lane
        :param float l: lateral distance to the lane center

        :returns: waypoint object
        :rtype: Waypoint
        """
        point = self.lane.get_coordinate(lane_id, s, l) # x, y, heading
        is_junction = self.lane.is_junction_lane(lane_id)
        speed_limit = self.lane.get_speed_limit(lane_id)
        
        waypoint = Waypoint(
            lane_id=lane_id,
            is_junction=is_junction,
            s=s,
            l=l,
            x=point[0],
            y=point[1],
            heading=point[2],
            speed_limit=speed_limit
        )
        
        return waypoint.to_dict()
    
    @sandbox_api("get_next_waypoint")
    def get_next_waypoint(self, lane_id: str, s: float, l: float, distance: float) -> List[Dict]:
        """
        Get next waypoint objects based on lane id, s and l, considering lane direction.

        :param str lane_id: lane id
        :param float s: longitudinal distance along the lane
        :param float l: lateral distance to the lane center
        :param float distance: distance to next waypoint

        :returns: list of waypoint objects
        :rtype: List[Dict]
        """
        waypoints = []
        lane_length = self.lane.get_length(lane_id)
        direction = self.lane.get_direction(lane_id)

        # Direction-aware longitudinal update
        if direction == "FORWARD":
            next_s = s + distance
        elif direction == "BACKWARD":
            next_s = s - distance
        else:
            # BIDIRECTION or UNKNOWN
            next_s = s + distance

        # Case 1: still within lane boundary
        if 0.0 <= next_s <= lane_length:
            x, y, heading = self.lane.get_coordinate(lane_id, next_s, l)
            waypoint = Waypoint(
                lane_id=lane_id,
                is_junction=self.lane.is_junction_lane(lane_id),
                s=next_s,
                l=l,
                x=x,
                y=y,
                heading=heading,
                speed_limit=self.lane.get_speed_limit(lane_id)
            )
            waypoints.append(waypoint.to_dict())
            return waypoints

        # Case 2: go beyond lane boundary → find next lane(s)
        if direction == "BACKWARD":
            # traveling backward → use predecessor
            next_lanes = self.lane.get_predecessor_ids(lane_id)
            remaining = abs(next_s)
        else:
            # traveling forward → use successor
            next_lanes = self.lane.get_successor_ids(lane_id)
            remaining = next_s - lane_length

        if not next_lanes:
            return []  # dead-end

        for nxt in next_lanes:
            nxt_len = self.lane.get_length(nxt)
            # clamp remaining distance
            nxt_s = min(max(remaining, 0.0), nxt_len - 0.01)
            x, y, heading = self.lane.get_coordinate(nxt, nxt_s, l)

            waypoint = Waypoint(
                lane_id=nxt,
                is_junction=self.lane.is_junction_lane(nxt),
                s=nxt_s,
                l=l,
                x=x,
                y=y,
                heading=heading,
                speed_limit=self.lane.get_speed_limit(nxt)
            )
            waypoints.append(waypoint.to_dict())

        return waypoints

    @sandbox_api("get_previous_waypoint")
    def get_previous_waypoint(self, lane_id: str, s: float, l: float, distance: float) -> List[Dict]:
        """
        Get previous waypoint objects based on lane id, s, and l, considering lane direction.

        :param str lane_id: lane id
        :param float s: longitudinal distance along the lane
        :param float l: lateral distance to the lane center
        :param float distance: distance to previous waypoint

        :returns: list of waypoint objects
        :rtype: List[Dict]
        """
        waypoints = []
        lane_length = self.lane.get_length(lane_id)
        direction = self.lane.get_direction(lane_id)

        # Direction-aware longitudinal update
        if direction == "FORWARD":
            prev_s = s - distance
        elif direction == "BACKWARD":
            prev_s = s + distance
        else:  # BIDIRECTION or UNKNOWN
            prev_s = s - distance

        # Case 1: still within lane boundary
        if 0.0 <= prev_s <= lane_length:
            x, y, heading = self.lane.get_coordinate(lane_id, prev_s, l)
            waypoint = Waypoint(
                lane_id=lane_id,
                is_junction=self.lane.is_junction_lane(lane_id),
                s=prev_s,
                l=l,
                x=x,
                y=y,
                heading=heading,
                speed_limit=self.lane.get_speed_limit(lane_id)
            )
            waypoints.append(waypoint.to_dict())
            return waypoints

        # Case 2: go beyond lane boundary → find previous lane(s)
        if direction == "BACKWARD":
            # traveling backward → connect to successor (反向行驶时 successor 是“前方”)
            next_lanes = self.lane.get_successor_ids(lane_id)
            remaining = abs(prev_s - lane_length)
        else:
            # traveling forward → connect to predecessor
            next_lanes = self.lane.get_predecessor_ids(lane_id)
            remaining = abs(prev_s)

        if not next_lanes:
            return []  # no connected lane

        for nxt in next_lanes:
            nxt_len = self.lane.get_length(nxt)
            nxt_s = max(nxt_len - remaining, 0.01)
            x, y, heading = self.lane.get_coordinate(nxt, nxt_s, l)
            waypoint = Waypoint(
                lane_id=nxt,
                is_junction=self.lane.is_junction_lane(nxt),
                s=nxt_s,
                l=l,
                x=x,
                y=y,
                heading=heading,
                speed_limit=self.lane.get_speed_limit(nxt)
            )
            waypoints.append(waypoint.to_dict())

        return waypoints
