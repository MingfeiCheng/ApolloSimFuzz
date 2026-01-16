import rtree
import copy
import math
import networkx as nx

from loguru import logger
from typing import List, Optional, Dict, Tuple
from shapely.geometry import Polygon, LineString, Point

from apollo_modules.modules.map.proto.map_lane_pb2 import Lane

from common.rpc_utils import sandbox_api

class RoadLaneManager(object):

    # LANE_TYPE = ['NONE', 'CITY_DRIVING', 'BIKING', 'SIDEWALK', 'PARKING', 'SHOULDER']
    LANE_TYPE_MAP = {
        1: "NONE",
        2: "CITY_DRIVING",
        3: "BIKING",
        4: "SIDEWALK",
        5: "PARKING",
        6: "SHOULDER",
    }
    BOUNDARY_TYPE = {
        0: "UNKNOWN",
        1: "DOTTED_YELLOW",
        2: "DOTTED_WHITE",
        3: "SOLID_YELLOW",
        4: "SOLID_WHITE",
        5: "DOUBLE_YELLOW",
        6: "CURB",
    }

    def __init__(
        self,
        lanes: Optional[Dict[str, Lane]] = None,
        lanes_stop_sign: Optional[Dict[str, str]] = None,
        lanes_traffic_light: Optional[Dict[str, str]] = None,
        lanes_junction_flags: Optional[Dict[str, bool]] = None
    ):
        self.lanes = lanes
        self.lanes_stop_sign = lanes_stop_sign
        self.lanes_traffic_light = lanes_traffic_light
        self.lanes_junction_flags = lanes_junction_flags

        self.lanes_index = None
        self.lanes_index_map = None
        self.lanes_graph = None

        # keep available path pairs
        self._path_pairs: List[Tuple[str, str]] = []
        
        self._initialize()

    def _initialize(self):
        if self.lanes is None:
            return

        # lane index
        self.lane_index = rtree.index.Index()
        self.lanes_index_map = {}
        l_index_int = 0
        for l_index, l in self.lanes.items():
            lane = l
            points = lane.left_boundary.curve.segment[0].line_segment
            left_line = [[x.x, x.y] for x in points.point]
            points = lane.right_boundary.curve.segment[0].line_segment
            right_line = [[x.x, x.y] for x in points.point]
            right_line = right_line[::-1]
            lane_boundary = left_line + right_line
            lane_polygon = Polygon(lane_boundary)
            minx, miny, maxx, maxy = lane_polygon.bounds
            self.lane_index.insert(l_index_int, (float(minx), float(miny), float(maxx), float(maxy)))
            self.lanes_index_map[l_index_int] = l_index
            l_index_int += 1

        # lane graph
        self.lanes_graph = nx.DiGraph()
        for lane_id in self.lanes: # key
            self.lanes_graph.add_node(lane_id)
            # neighbor forward lanes - todo: consider traffic laws
            lane_neighbors = self.get_right_neighbor_forward_lane_ids(lane_id) + self.get_left_neighbor_forward_lane_ids(lane_id)
            for neighbor in lane_neighbors:
                self.lanes_graph.add_edge(lane_id, neighbor, length=5.0, type='neighbor') # estimated length

            # next lanes
            lane_successors = self.get_successor_ids(lane_id)
            for successor in lane_successors:
                self.lanes_graph.add_edge(lane_id, successor, length=self.get_length(lane_id), type='successor')

    def setup(
        self,
        lanes: Dict[str, Lane],
        lanes_stop_sign: Dict[str, str],
        lanes_traffic_light: Dict[str, str],
        lanes_junction_flags: Dict[str, bool]
    ):
        self.lanes = lanes
        self.lanes_stop_sign = lanes_stop_sign
        self.lanes_traffic_light = lanes_traffic_light
        self.lanes_junction_flags = lanes_junction_flags
        self._initialize()

    def export(self):
        save_data = {
            'lanes': copy.deepcopy(self.lanes),
            'lanes_stop_sign': copy.deepcopy(self.lanes_stop_sign),
            'lanes_traffic_light': copy.deepcopy(self.lanes_traffic_light),
            'lanes_junction_flags': copy.deepcopy(self.lanes_junction_flags)
        }
        for k, y in save_data['lanes'].items():
            save_data['lanes'][k] = y.SerializeToString()
        return save_data

    def load(self, data: Dict):
        self.lanes = {}
        for k, y in data['lanes'].items():
            lane = Lane()
            lane.ParseFromString(y)
            self.lanes[k] = lane
        self.lanes_stop_sign = data['lanes_stop_sign']
        self.lanes_traffic_light = data['lanes_traffic_light']
        self.lanes_junction_flags = data['lanes_junction_flags']

        self._initialize()

    @sandbox_api("is_junction_lane")
    def is_junction_lane(self, lane_id: str) -> bool:
        return self.lanes_junction_flags[lane_id]

    @sandbox_api("is_driving_lane")
    def is_driving_lane(self, lane_id: str) -> bool:
        lane = self.get(lane_id)
        if lane.type == lane.LaneType.CITY_DRIVING:
            return True
        else:
            return False

    @sandbox_api("get_all")
    def get_all(self, contain_junction: bool = True, lane_type: str = None) -> List[str]:
        normalized_type = lane_type.upper() if lane_type else None
        filtered_lanes = []

        for lane_id, lane in self.lanes.items():
            # Junction filter
            if not contain_junction and self.is_junction_lane(lane_id):
                continue

            # Type filter
            if normalized_type:
                lane_type_str = None
                if hasattr(lane, "type"):
                    # handle int or enum
                    if isinstance(lane.type, int):
                        lane_type_str = self.LANE_TYPE_MAP.get(lane.type, "UNKNOWN")
                    elif isinstance(lane.type, str):
                        lane_type_str = lane.type.upper()
                    elif hasattr(lane.type, "name"):
                        lane_type_str = lane.type.name.upper()

                if lane_type_str != normalized_type:
                    continue

            filtered_lanes.append(lane_id)

        return filtered_lanes

    # Not visible in RPC
    def get(self, lane_id: str) -> Lane:
        """
        Get a specific lane object based on ID

        :param str lane_id: ID of the lane interested in

        :returns: lane object
        :rtype: Lane
        """
        return self.lanes[lane_id]

    @sandbox_api("get_central_curve")
    def get_central_curve(self, lane_id: str) -> List[List[float]]:
        lane = self.lanes[lane_id]
        central_curve_points = lane.central_curve.segment[0].line_segment
        curve_coords = []
        for point in central_curve_points.point:
            curve_coords.append([point.x, point.y])
        return curve_coords

    @sandbox_api("get_left_boundary_curve")
    def get_left_boundary_curve(self, lane_id: str) -> List[List[float]]:
        lane = self.lanes[lane_id]
        left_boundary_points = lane.left_boundary.curve.segment[0].line_segment
        boundary_coords = []
        for point in left_boundary_points.point:
            boundary_coords.append([point.x, point.y])
        return boundary_coords

    @sandbox_api("get_right_boundary_curve")
    def get_right_boundary_curve(self, lane_id: str) -> List[List[float]]:
        lane = self.lanes[lane_id]
        right_boundary_points = lane.right_boundary.curve.segment[0].line_segment
        boundary_coords = []
        for point in right_boundary_points.point:
            boundary_coords.append([point.x, point.y])
        return boundary_coords

    @sandbox_api("get_left_boundary_type")
    def get_left_boundary_type(self, lane_id: str) -> str:
        lane = self.lanes[lane_id]
        boundary_type = lane.left_boundary.boundary_type[0].types[0]
        boundary_type = self.BOUNDARY_TYPE[boundary_type]
        return boundary_type

    @sandbox_api("get_right_boundary_type")
    def get_right_boundary_type(self, lane_id: str) -> str:
        lane = self.lanes[lane_id]
        boundary_type = lane.right_boundary.boundary_type[0].types[0]
        boundary_type = self.BOUNDARY_TYPE[boundary_type]
        return boundary_type

    @sandbox_api("get_type")
    def get_type(self, lane_id: str) -> str:
        lane = self.lanes[lane_id]
        return lane.type

    @sandbox_api("get_turn")
    def get_turn(self, lane_id: str) -> str:
        lane = self.lanes[lane_id]
        return lane.turn

    @sandbox_api("get_length")
    def get_length(self, lane_id: str) -> float:
        lane = self.lanes[lane_id]
        return lane.length

    @sandbox_api("get_speed_limit")
    def get_speed_limit(self, lane_id: str) -> float:
        lane = self.lanes[lane_id]
        return lane.speed_limit

    @sandbox_api("get_overlap_ids")
    def get_overlap_ids(self, lane_id: str) -> List[str]:
        lane = self.lanes[lane_id]
        return lane.overlap_id

    @sandbox_api("get_predecessor_ids")
    def get_predecessor_ids(self, lane_id: str, depth: int = 1) -> List[str]:
        if lane_id not in self.lanes:
            raise ValueError(f"Lane ID '{lane_id}' not found in lanes.")

        pending_lanes_id = [lane_id]
        predecessors = set()  # Use a set to avoid duplicates

        for _ in range(depth):
            next_pending_lanes = []
            for l_id in pending_lanes_id:
                l = self.lanes[l_id]
                next_pending_lanes = [x.id for x in l.predecessor_id]
                predecessors.update(next_pending_lanes)
            pending_lanes_id = next_pending_lanes

        return list(predecessors)

    @sandbox_api("get_successor_ids")
    def get_successor_ids(self, lane_id: str, depth: int = 1) -> List[str]:
        if lane_id not in self.lanes:
            raise ValueError(f"Lane ID '{lane_id}' not found in lanes.")

        pending_lanes_id = [lane_id]
        successors = set()  # Use a set to avoid duplicates

        for _ in range(depth):
            next_pending_lanes = []
            for l_id in pending_lanes_id:
                l = self.lanes[l_id]
                next_pending_lanes = [x.id for x in l.successor_id]
                successors.update(next_pending_lanes)
            pending_lanes_id = next_pending_lanes

        return list(successors)

    @sandbox_api("get_left_neighbor_forward_lane_ids")
    def get_left_neighbor_forward_lane_ids(self, lane_id: str, depth: int = 1) -> List[str]:
        """
        Retrieve all left neighbor forward lane IDs up to a specified depth.

        Args:
            lane_id (str): The ID of the starting lane.
            depth (int): The maximum depth to traverse for left neighbor forward lanes.

        Returns:
            List[str]: A list of lane IDs for all left neighbor forward lanes up to the specified depth.
        """
        if lane_id not in self.lanes:
            raise ValueError(f"Lane ID '{lane_id}' not found in lanes.")

        pending_lane_ids = [lane_id]
        neighbors = set()  # Use a set to avoid duplicate IDs

        for _ in range(depth):
            next_pending_lanes = []
            for l_id in pending_lane_ids:
                l = self.lanes[l_id]
                next_pending_lanes = [x.id for x in l.left_neighbor_forward_lane_id]
                # Add the IDs of left neighbors
                neighbors.update(next_pending_lanes)
            pending_lane_ids = next_pending_lanes

        return list(neighbors)

    @sandbox_api("get_right_neighbor_forward_lane_ids")
    def get_right_neighbor_forward_lane_ids(self, lane_id: str, depth: int = 1) -> List[str]:
        """
        Retrieve all right neighbor forward lane IDs up to a specified depth.

        Args:
            lane_id (str): The ID of the starting lane.
            depth (int): The maximum depth to traverse for right neighbor forward lanes.

        Returns:
            List[str]: A list of lane IDs for all right neighbor forward lanes up to the specified depth.
        """
        if lane_id not in self.lanes:
            raise ValueError(f"Lane ID '{lane_id}' not found in lanes.")

        pending_lane_ids = [lane_id]
        neighbors = set()  # Use a set to avoid duplicate IDs

        for _ in range(depth):
            next_pending_lanes = []
            for l_id in pending_lane_ids:
                l = self.lanes[l_id]
                next_pending_lanes = [x.id for x in l.right_neighbor_forward_lane_id]
                neighbors.update(next_pending_lanes)
            pending_lane_ids = next_pending_lanes

        return list(neighbors)

    @sandbox_api("get_neighbor_forward_lane_ids")
    def get_neighbor_forward_lane_ids(self, lane_id: str, depth: int = 1) -> List[str]:
        """
        Retrieve all neighbor forward lane IDs up to a specified depth.

        Args:
            lane_id (str): The ID of the starting lane.
            depth (int): The maximum depth to traverse for neighbor forward lanes.

        Returns:
            List[str]: A list of lane IDs for all neighbor forward lanes up to the specified depth.
        """
        if lane_id not in self.lanes:
            raise ValueError(f"Lane ID '{lane_id}' not found in lanes.")

        left_forward_lane_ids = self.get_left_neighbor_forward_lane_ids(lane_id, depth)
        right_forward_lane_ids = self.get_right_neighbor_forward_lane_ids(lane_id, depth)
        return left_forward_lane_ids + right_forward_lane_ids

    @sandbox_api("get_left_neighbor_reverse_lane_ids")
    def get_left_neighbor_reverse_lane_ids(self, lane_id: str, depth: int = 1) -> List[str]:
        """
        Retrieve all left neighbor reverse lane IDs up to a specified depth.

        Args:
            lane_id (str): The ID of the starting lane.
            depth (int): The maximum depth to traverse for left neighbor reverse lanes.

        Returns:
            List[str]: A list of lane IDs for all left neighbor reverse lanes up to the specified depth.
        """
        if lane_id not in self.lanes:
            raise ValueError(f"Lane ID '{lane_id}' not found in lanes.")

        pending_lane_ids = [lane_id]
        neighbors = set()

        for _ in range(depth):
            next_pending_lanes = []
            for l_id in pending_lane_ids:
                l = self.lanes[l_id]
                next_pending_lanes = [x.id for x in l.left_neighbor_reverse_lane_id]
                neighbors.update(next_pending_lanes)
            pending_lane_ids = next_pending_lanes

        return list(neighbors)

    @sandbox_api("get_right_neighbor_reverse_lane_ids")
    def get_right_neighbor_reverse_lane_ids(self, lane_id: str, depth: int = 1) -> List[str]:
        """
        Retrieve all right neighbor reverse lane IDs up to a specified depth.

        Args:
            lane_id (str): The ID of the starting lane.
            depth (int): The maximum depth to traverse for right neighbor reverse lanes.

        Returns:
            List[str]: A list of lane IDs for all right neighbor reverse lanes up to the specified depth.
        """
        if lane_id not in self.lanes:
            raise ValueError(f"Lane ID '{lane_id}' not found in lanes.")

        pending_lane_ids = [lane_id]
        neighbors = set()

        for _ in range(depth):
            next_pending_lanes = []
            for l_id in pending_lane_ids:
                l = self.lanes[l_id]
                next_pending_lanes = [x.id for x in l.right_neighbor_reverse_lane_id]
                neighbors.update(next_pending_lanes)
            pending_lane_ids = next_pending_lanes

        return list(neighbors)

    @sandbox_api("get_neighbor_reverse_lane_ids")
    def get_neighbor_reverse_lane_ids(self, lane_id: str, depth: int = 1) -> List[str]:
        """
        Retrieve all neighbor reverse lane IDs up to a specified depth.

        Args:
            lane_id (str): The ID of the starting lane.
            depth (int): The maximum depth to traverse for neighbor reverse lanes.

        Returns:
            List[str]: A list of lane IDs for all neighbor reverse lanes up to the specified depth.
        """
        if lane_id not in self.lanes:
            raise ValueError(f"Lane ID '{lane_id}' not found in lanes.")

        left_reverse_lane_ids = self.get_left_neighbor_reverse_lane_ids(lane_id, depth)
        right_reverse_lane_ids = self.get_right_neighbor_reverse_lane_ids(lane_id, depth)
        return left_reverse_lane_ids + right_reverse_lane_ids

    @sandbox_api("get_direction")
    def get_direction(self, lane_id: str) -> str:
        lane = self.lanes[lane_id]
        return lane.direction

    @sandbox_api("get_polygon")
    def get_polygon(self, lane_id: str) -> List[List[float]]:
        lane = self.lanes[lane_id]
        points = lane.left_boundary.curve.segment[0].line_segment
        left_line = [[x.x, x.y] for x in points.point]
        points = lane.right_boundary.curve.segment[0].line_segment
        right_line = [[x.x, x.y] for x in points.point]

        right_line = right_line[::-1]
        lane_boundary = left_line + right_line
        return lane_boundary #Polygon(lane_boundary)

    @sandbox_api("get_coordinate")
    def get_coordinate(self, lane_id: str, s: float, l: float) -> Tuple[float, float, float]:
        """
        Given a lane_id and a point on the lane, get the actual coordinate and the heading
        at that point.
        """
        def right_rotation(coord, theta):
            """
            theta : degree
            """
            # theta = math.radians(theta)
            x_o = coord[1]
            y_o = coord[0]
            x_r = x_o * math.cos(theta) - y_o * math.sin(theta)
            y_r = x_o * math.sin(theta) + y_o * math.cos(theta)
            return [y_r, x_r]

        lst = self.get_central_curve(lane_id)  # line string
        lst = LineString(lst)
        # logger.debug('s: {}', s)
        ip = lst.interpolate(s)  # a point

        segments = list(map(LineString, zip(lst.coords[:-1], lst.coords[1:])))
        # logger.debug('ip: type {} {}', type(ip), ip)
        segments.sort(key=lambda t: ip.distance(t))
        line = segments[0]
        x1, x2 = line.xy[0]
        y1, y2 = line.xy[1]

        heading = math.atan2(y2 - y1, x2 - x1)

        init_vector = [1, 0]
        right_vector = right_rotation(init_vector, -(heading - math.radians(90.0)))
        x = ip.x + right_vector[0] * l
        y = ip.y + right_vector[1] * l
        return x, y, heading

    @sandbox_api("find_path")
    def find_path(self, start_lane: str, end_lane: str):
        def heuristic(current_lane, target_lane):
            return 1.0

        try:
            path = nx.astar_path(
                self.lanes_graph,
                start_lane,
                end_lane,
                heuristic=heuristic,
                weight="length"
            )
            return path
        except nx.NetworkXNoPath:
            logger.warning(f"No path found between {start_lane} and {end_lane}")
            return []
        
    @sandbox_api("find_lane_id")
    def find_lane_id(self, x, y):
        """
        Find the lane ID that contains the given position (x, y).

        Parameters:
        - x (float): X-coordinate of the position.
        - y (float): Y-coordinate of the position.

        Returns:
        - str: The lane ID if found, otherwise None.
        """
        # Create a point from the given position
        position = Point(x, y)

        # Query the R-tree for possible matches (bounding box intersection)
        possible_matches = list(self.lane_index.intersection((x, y, x, y)))

        # Iterate through possible matches to find the exact lane
        for lane_index_int in possible_matches:
            lane_id = self.lanes_index_map[lane_index_int]
            lane = self.lanes[lane_id]

            # Reconstruct the lane polygon
            left_points = [[p.x, p.y] for p in lane.left_boundary.curve.segment[0].line_segment.point]
            right_points = [[p.x, p.y] for p in lane.right_boundary.curve.segment[0].line_segment.point]
            lane_boundary = left_points + right_points[::-1]
            lane_polygon = Polygon(lane_boundary)

            # Check if the position is inside the polygon
            if lane_polygon.contains(position):
                return lane_id  # Found the lane ID

        # If no lane contains the position, return None
        return None
    
    def route_planner(self, waypoints: List[Tuple[float, float]]):
        """
        Plan a continuous route passing through multiple waypoints.
        Each waypoint is a (x, y) coordinate in world coordinates.
        Returns a list of lane_ids representing the full route.
        """
        if len(waypoints) < 2:
            return None

        full_lane_path = []
        full_geometry = []

        for i in range(len(waypoints) - 1):
            start_xy = waypoints[i]
            end_xy = waypoints[i + 1]

            start_point = Point(start_xy)
            end_point = Point(end_xy)

            start_lane = self.get_nearest_lane(start_point)
            end_lane = self.get_nearest_lane(end_point)

            if start_lane is None or end_lane is None:
                raise RuntimeError(f"Cannot find nearest lanes for segment {i}: {start_xy} → {end_xy}")

            try:
                lane_path = nx.shortest_path(
                    self.lanes_graph,
                    source=start_lane,
                    target=end_lane,
                    weight="length"
                )
            except nx.NetworkXNoPath:
                raise RuntimeError(f"No valid path between {start_lane} and {end_lane}")

            # concatenate results, avoiding duplicate lane junctions
            if full_lane_path and lane_path[0] == full_lane_path[-1]:
                lane_path = lane_path[1:]

            full_lane_path.extend(lane_path)

            # collect geometry for visualization
            for lane_id in lane_path:
                lane = self.lanes[lane_id]
                points = [(p.x, p.y) for p in lane.central_curve.segment[0].line_segment.point]
                full_geometry.extend(points)

        return {
            "lane_path": full_lane_path,
            "geometry": full_geometry
        }
