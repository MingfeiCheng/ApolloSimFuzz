import math
import random
import numpy as np

from tqdm import tqdm
from collections import deque
from typing import List, Dict, Tuple
from shapely.geometry import Polygon, LineString

from scenario_runner.sandbox_operator import SandboxOperator

def extract_details(sandbox_api: SandboxOperator, region_points: List[List[float]]):
    
    coarse_region_points = region_points
    coarse_region = Polygon(coarse_region_points)
    
    map_lanes = sandbox_api.map.lane.get_all()

    refine_region_lanes = []
    # iteration selection
    for lane_id in tqdm(map_lanes):
        lane_center_curve_points = sandbox_api.map.lane.get_central_curve(lane_id)
        lane_center_curve = LineString(lane_center_curve_points)
        if lane_center_curve.intersects(coarse_region):
            refine_region_lanes.append(lane_id)
    refine_region_lanes = list(set(refine_region_lanes))

    # obtain crosswalks
    refined_crosswalks = []
    map_crosswalks = sandbox_api.map.crosswalk.get_all()
    for crosswalk_id in tqdm(map_crosswalks):
        crosswalk_polygon = sandbox_api.map.crosswalk.get_polygon(crosswalk_id)
        if crosswalk_polygon.intersects(coarse_region):
            refined_crosswalks.append(crosswalk_id)
    refined_crosswalks = list(set(refined_crosswalks))
    return refine_region_lanes, refined_crosswalks


def get_polygon_points(
    location: dict,
    bbox: dict,
    back_edge_to_center: float
) -> Tuple[Tuple[float]]:
    # this gets current polygon
    half_w = bbox['width'] / 2.0

    front_l = bbox['length'] - back_edge_to_center
    back_l = -1 * back_edge_to_center

    sin_h = math.sin(location['yaw'])
    cos_h = math.cos(location['yaw'])
    vectors = [(front_l * cos_h - half_w * sin_h,
                front_l * sin_h + half_w * cos_h),
                (back_l * cos_h - half_w * sin_h,
                back_l * sin_h + half_w * cos_h),
                (back_l * cos_h + half_w * sin_h,
                back_l * sin_h - half_w * cos_h),
                (front_l * cos_h + half_w * sin_h,
                front_l * sin_h - half_w * cos_h)]

    points = []
    for x, y in vectors:
        points.append([location['x'] + x, location['y'] + y])
    return points


def has_route_lane_conflict(
    route1: List[str],
    route2: List[str]
) -> bool:
    return bool(set(route1) & set(route2))  # Check if intersection is non-empty
    
    
def find_potential_routes_lanes(
    sandbox_api: SandboxOperator,
    lanes: List[str]
):
    # TODO: optimize with more advanced path searcher
    
    # 1. build adjacency list
    successors: Dict[str, List[str]] = {}

    lanes_set = set(lanes)  # O(1) lookup

    for lane_id in lanes:
        succ = sandbox_api.map.lane.get_successor_id(lane_id, depth=1)
        successors[lane_id] = [s for s in succ if s in lanes_set]

    # 2. BFS to find all possible routes
    all_routes = []
    for start_lane_id in successors:
        queue = deque([[start_lane_id]])
        while queue:
            path = queue.popleft()
            all_routes.append(path)

            last = path[-1]
            for nxt in successors.get(last, []):
                if nxt not in path:  # avoid cycles
                    queue.append(path + [nxt])

    return all_routes

def sample_lane_waypoints(
    sandbox_api: SandboxOperator,
    lane_id: str,
    sample_interval: float = 2.0,
) -> List[dict]:
    """
    Fetches waypoints sampled at fixed intervals along the lane.

    :param lane_id: The ID of the lane.
    :param sample_interval: Distance interval for sampling waypoints (default: 2 meters).
    :return: A list of Waypoint objects representing the lane path.
    """
    waypoints = []
    lane_length = sandbox_api.map.lane.get_length(lane_id)
    s = 0.0

    while s < lane_length:
        x, y, heading = sandbox_api.map.lane.get_coordinate(lane_id, s, 0.0)
        waypoints.append({
            'lane': {
                'id': lane_id,
                's': s,
                'l': 0.0
            },
            'location': {
                'x': x,
                'y': y,
                'z': 0.0,
                'pitch': 0.0,
                'yaw': heading,
                'roll': 0.0
            },
            'speed': 0.0
        })
        s += sample_interval

    # Ensure the final waypoint at lane_length is included
    if waypoints and waypoints[-1]['lane']['s'] < lane_length:
        x, y, heading = sandbox_api.map.lane.get_coordinate(lane_id, lane_length, 0.0)
        waypoints.append({
            'lane': {
                'id': lane_id,
                's': lane_length,
                'l': 0.0
            },
            'location': {
                'x': x,
                'y': y,
                'z': 0.0,
                'pitch': 0.0,
                'yaw': heading,
                'roll': 0.0
            },
            'speed': 0.0
        })
    return waypoints


def sample_route_waypoints(
    sandbox_api: SandboxOperator,
    route: List[str],
    sample_interval: float = 2.0,
) -> List[dict]:
    """
    Samples waypoints along a given route at fixed intervals.

    :param route: List of lane IDs in the route
    :return: A list of sampled Waypoint objects
    """
    sampled_waypoints = []

    for lane_index, lane_id in enumerate(route):
        waypoints = sample_lane_waypoints(sandbox_api, lane_id, sample_interval=sample_interval)
        if not waypoints:
            continue  # Skip lanes with no valid data

        # ** Always add the first waypoint of the first lane **
        if lane_index == 0:
            sampled_waypoints.extend(waypoints)  # Temporarily add all waypoints, will check order in the next step
            continue

        # Process waypoints and sample at 2-meter intervals
        prev_waypoint = sampled_waypoints[-1]
        for i in range(1, len(waypoints)):
            curr_waypoint = waypoints[i]

            prev_location = np.array([prev_waypoint['location']['x'], prev_waypoint['location']['y']])
            curr_location = np.array([curr_waypoint['location']['x'], curr_waypoint['location']['y']])

            segment_length = np.linalg.norm(curr_location - prev_location)
            if segment_length >= sample_interval:
                sampled_waypoints.append(curr_waypoint)

    return sampled_waypoints

def sample_lane_boundary_waypoiints(
    sandbox_api: SandboxOperator,
    lane_id: str,
    sample_interval: float = 2.0,
):
    def distance(p1: List[float], p2: List[float]) -> float:
            return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

    def interpolate(p1: List[float], p2: List[float], ratio: float) -> List[float]:
        return [
            p1[0] + (p2[0] - p1[0]) * ratio,
            p1[1] + (p2[1] - p1[1]) * ratio
        ]

    def compute_heading(p1: List[float], p2: List[float]) -> float:
        return math.atan2(p2[1] - p1[1], p2[0] - p1[0])

    def sample_boundary(coords: List[List[float]], interval: float) -> List[dict]:
        if not coords or len(coords) < 2:
            return []

        sampled = []
        accumulated = 0.0
        next_sample_at = 0.0
        prev = coords[0]

        for i in range(1, len(coords)):
            curr = coords[i]
            seg_len = distance(prev, curr)

            while accumulated + seg_len >= next_sample_at:
                ratio = (next_sample_at - accumulated) / seg_len
                point = interpolate(prev, curr, ratio)
                heading = compute_heading(prev, curr)

                sampled.append({
                    "lane": {
                        "id": lane_id,
                        "s": next_sample_at,
                        "l": 0.0
                    },
                    "location": {
                        "x": point[0],
                        "y": point[1],
                        "z": 0.0,
                        "pitch": 0.0,
                        "yaw": heading,
                        "roll": 0.0
                    },
                    "speed": 0.0
                })

                next_sample_at += interval

            accumulated += seg_len
            prev = curr

        return sampled

    left_coords = sandbox_api.map.lane.get_left_boundary_curve(lane_id)
    right_coords = sandbox_api.map.lane.get_right_boundary_curve(lane_id)

    left_sampled = sample_boundary(left_coords, sample_interval)
    right_sampled = sample_boundary(right_coords, sample_interval)

    return left_sampled, right_sampled

def sample_crosswalk_waypoints(
    sandbox_api: SandboxOperator,
    crosswalk_id: str,
    sample_interval: float = 2.0,
) -> List[dict]:
    """
    Samples waypoints along the boundary of a given crosswalk at fixed intervals.

    :param crosswalk_id: ID of the crosswalk
    :return: A list of sampled Waypoint objects
    """
    points = sandbox_api.map.crosswalk.get_polygon_points(crosswalk_id)

    if not points or len(points) < 2:
        return []

    # Remove duplicated endpoint for closed polygons
    if points[0] == points[-1]:
        points = points[:-1]

    if len(points) < 2:
        return []

    # Random circular shift
    shift = random.randint(0, len(points) - 1)
    shifted = points[shift:] + points[:shift]
    shifted.append(shifted[0])  # close polygon

    sampled = []

    for i in range(len(shifted) - 1):
        x0, y0 = shifted[i]
        x1, y1 = shifted[i + 1]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        heading = math.atan2(dy, dx)

        if length == 0:
            continue

        num_steps = max(1, int(length // sample_interval))
        for step in range(num_steps):
            ratio = (step * sample_interval) / length
            x = x0 + dx * ratio
            y = y0 + dy * ratio

            sampled.append({
                "lane": {
                    "id": crosswalk_id,
                    "s": 0.0,
                    "l": 0.0
                },
                "location": {
                    "x": x,
                    "y": y,
                    "z": 0.0,
                    "pitch": 0.0,
                    "yaw": heading,
                    "roll": 0.0
                },
                "speed": 0.0
            })

    return sampled