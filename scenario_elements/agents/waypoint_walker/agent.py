import os
import ray
import time
import copy
import math
import numpy as np

from loguru import logger
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from collections import deque
from shapely.ops import unary_union
from shapely.geometry import Point, LineString, Polygon

from tools.logger_tools import get_instance_logger

from scenario_elements.agents.base import AgentBase
from scenario_elements.config import Waypoint

class WaypointWalkerConfig(BaseModel):
    
    id: str = Field(..., description="Unique identifier of the waypoint walker")
    model: str = Field(..., description="Walker model name")
    rolename: str = Field(..., description="Role name, e.g., 'ego' or 'npc'")
    
    category: Optional[str] = Field("car", description="Actor category, e.g., 'car'")
    trigger_time: float = Field(..., ge=0, description="Time to start moving (seconds)")
    route: List[Waypoint] = Field(
        ..., description="List of waypoints describing the route"
    )
    
    def get_initial_waypoint(self) -> Waypoint:
        return self.route[0]

def get_basic_config():
    return {
        "max_speed": 3.0,
        "max_speed_junction": 3.0,
        "max_acceleration": 2.0,
        "max_deceleration": -2.0,
        "collision_threshold": 5.0,
        "ignore_vehicle": True,
        "ignore_walker": True,
        "ignore_static_obstacle": True,
        "ignore_traffic_light": True,
        "min_distance": 1.0, # to filter next waypoint
        "collision_distance_threshold": 5.0,
        "remove_after_finish" : False
    }
    
def get_polygon(location_x, location_y, length, width, back_edge_to_center, heading, buffer: float = 0.0) -> Polygon:
    half_w = width / 2.0

    front_l = length - back_edge_to_center
    back_l = -1 * back_edge_to_center
    front_l += buffer

    sin_h = math.sin(heading)
    cos_h = math.cos(heading)
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
        points.append([location_x + x, location_y + y])
    return Polygon(points)

class WaypointWalkerAgent(AgentBase):
    
    prefix = 'waypoint_walker'
    MIN_DISTANCE_PERCENTAGE = 0.9
    running_frequency = 25.0

    def __init__(
        self,
        id: str,
        sim_ctn_name: str,
        actor_config: Dict[str, Any],
        other_config: Dict[str, Any] = {},
        start_event = None,
        stop_event = None,
        remove_after_finished: bool = False
    ):
        super(WaypointWalkerAgent, self).__init__(
            id=id,
            sim_ctn_name=sim_ctn_name,
            actor_config=actor_config,
            other_config=other_config,
            start_event=start_event,
            stop_event=stop_event,
            remove_after_finished=remove_after_finished
        )
    
    def _initialize(self):
        # other configs
        self.output_folder = self.other_config['output_folder']
        self.debug = self.other_config.get('debug', False)
        self.user_parameters = self.other_config.get('parameters', {})
        
        # actor configs
        self.actor_config_py: WaypointWalkerConfig = WaypointWalkerConfig.model_validate(self.actor_config)
        self.route = [wp.model_dump() for wp in self.actor_config_py.route] # convert to dict

        self._init_paths_and_logger()
        self._init_parameters()
        self._init_runtime_state()
        self.run()

    def _init_paths_and_logger(self):
        self.debug_folder = os.path.join(self.output_folder, f"debug/{self.prefix}")

        if self.debug:
            os.makedirs(self.debug_folder, exist_ok=True)
            log_file = os.path.join(self.debug_folder, f"{self.prefix}_{self.id}.log")
            if os.path.exists(log_file):
                os.remove(log_file)
            self.logger = get_instance_logger(f"{self.prefix}_{self.id}", log_file)
            self.logger.info(f"Logger initialized for {self.prefix}_{self.id}")
        else:
            self.logger = None

    def _init_parameters(self):
        
        parameters = get_basic_config()
        parameters.update(self.user_parameters)

        self._ignore_vehicle = parameters.get('ignore_vehicle', False)
        self._ignore_walker = parameters.get('ignore_walker', False)
        self._ignore_static_obstacle = parameters.get('ignore_static_obstacle', False)
        self._ignore_traffic_light = parameters.get('ignore_traffic_light', False)

        self._max_speed = parameters.get('max_speed', 12.0)
        self._max_speed_junction = parameters.get('max_speed_junction', 10.0)
        self._min_distance = parameters.get('min_distance', 1.0) * self.MIN_DISTANCE_PERCENTAGE
        self._max_acceleration = parameters.get('max_acceleration', 3.0)
        self._max_deceleration = parameters.get('max_deceleration', -3.0)
        self._max_steering = parameters.get('max_steering', 0.8)
        self._collision_threshold = parameters.get('collision_threshold', 5.0)
        self._collision_distance_threshold = parameters.get('collision_distance_threshold', 5.0)
        self._remove_after_finish = parameters.get('remove_after_finish', False)

        self._initial_waypoint = self.route[0]
        self._waypoints_queue = deque(self.route[1:], maxlen=5000)
        self._waypoint_buffer = deque(maxlen=5)

    def _init_runtime_state(self):
        self._finish_time = 0.0
        self.step = 0
        self.running = False
        self.thread_run = None
            
    def _tick(self, snapshot: Dict):
        self.step += 1
        time_start = time.time()

        # Stop if finished
        if len(self._waypoints_queue) == 0 and len(self._waypoint_buffer) == 0:
            actor = self.sandbox_operator.sim.get_actor(self.id)
            control = {'acceleration': -abs(self._max_deceleration), 'heading': actor['location']['yaw']}
            self.sandbox_operator.sim.apply_walker_action(self.id, control)
            
            self.task_finished = True
            return

        # Fill buffer
        while len(self._waypoint_buffer) < self._waypoint_buffer.maxlen and self._waypoints_queue:
            self._waypoint_buffer.append(self._waypoints_queue.popleft())

        target_wp = copy.deepcopy(self._waypoint_buffer[0])
        target_speed = min(target_wp['speed'], self._max_speed)
        target_location = target_wp['location']

        obstacles = snapshot['actors']
        curr_actor = obstacles[self.id]
        curr_location = curr_actor['location']
        curr_speed = curr_actor['speed']

        hazard = self._obstacle_detected(curr_actor, obstacles, 1 / self.running_frequency)
        if hazard:
            target_speed = 0.0

        acc, heading = self._run_control(
            curr_location, curr_speed, target_location, target_speed, 1 / self.running_frequency
        )
        self.sandbox_operator.sim.apply_walker_action(self.id, {'acceleration': acc, 'heading': heading})

        # Update buffer
        curr_pos = Point(curr_location['x'], curr_location['y'])
        min_dist = max(curr_speed * 1.0 * self.MIN_DISTANCE_PERCENTAGE, self._min_distance)
        self._purge_obsolete_waypoints(curr_pos, min_dist)

        # Logging
        if self.debug and self.step % 10 == 0:
            self._log_debug_step(curr_location, curr_speed, acc, heading, hazard, target_wp, target_speed)

    def _purge_obsolete_waypoints(self, curr_pos: Point, min_dist: float):
        purge_count = 0
        for wp in self._waypoint_buffer:
            wp_pos = Point(wp['location']['x'], wp['location']['y'])
            if wp_pos.distance(curr_pos) < min_dist:
                purge_count += 1
            else:
                break
        for _ in range(purge_count):
            self._waypoint_buffer.popleft()

    def _run_control(self, curr_loc, curr_speed, target_loc, target_speed, dt):
        acc = (target_speed - curr_speed) / dt
        acc = float(np.clip(acc, -abs(self._max_deceleration), abs(self._max_acceleration)))
        heading = math.atan2(target_loc['y'] - curr_loc['y'], target_loc['x'] - curr_loc['x'])

        if self.debug:
            self.logger.info(f"target heading (calculated): {heading:.2f}")
        return acc, heading

    def _obstacle_detected(self, actor_info, actor_dict, delta_t):
        curr_loc = actor_info['location']
        curr_speed = actor_info['speed']
        curr_acc = actor_info['acceleration']
        curr_polygon = Polygon(actor_info['polygon'])
        curr_bbox = actor_info['bbox']
        back_edge = actor_info['back_edge_to_center']
        heading = curr_loc['yaw']

        travel_dist = curr_speed * delta_t + 0.5 * curr_acc * delta_t**2
        brake_dist = self._collision_distance_threshold + travel_dist * 1.5

        curr_pt = Point(curr_loc['x'], curr_loc['y'])
        planning_pts = [curr_pt]
        polygons = [curr_polygon]
        dist_travelled = 0.0

        for wp in self._waypoint_buffer:
            next_pt = Point(wp['location']['x'], wp['location']['y'])
            poly = get_polygon(
                wp['location']['x'], wp['location']['y'],
                curr_bbox['length'], curr_bbox['width'],
                back_edge, heading, buffer=1.0
            )
            planning_pts.append(next_pt)
            polygons.append(poly)
            dist_travelled += curr_pt.distance(next_pt)
            if dist_travelled > brake_dist:
                break
            curr_pt = next_pt

        path_line = LineString(planning_pts)
        union_poly = unary_union(polygons)

        for actor_id, actor in actor_dict.items():
            if actor_id == self.id or actor['category'].lower() in {'walker', 'static'}:
                continue
            if self._ignore_vehicle and actor['category'].lower() == 'vehicle' and int(actor_id) > 1000:
                continue

            poly = get_polygon(
                actor['location']['x'], actor['location']['y'],
                actor['bbox']['length'], actor['bbox']['width'],
                actor['bbox']['length'] / 2.0,
                actor['location']['yaw'], buffer=1.0
            )
            if union_poly.intersects(poly) or path_line.intersects(poly):
                return True
        return False

    def _log_debug_step(self, curr_loc, curr_speed, acc, heading, hazard, target_wp, target_speed):
        self.logger.info(f"=== Step {self.step} ===")
        self.logger.info(f"Acceleration: {acc:.2f}, Heading: {heading:.2f}")
        self.logger.info(f"Target Waypoint: {target_wp['lane']['id']} ({target_wp['location']['x']}, {target_wp['location']['y']})")
        self.logger.info(f"Current Location: ({curr_loc['x']}, {curr_loc['y']})")
        self.logger.info(f"Distance to Waypoint: {Point(curr_loc['x'], curr_loc['y']).distance(Point(target_wp['location']['x'], target_wp['location']['y'])):.2f}")
        self.logger.info(f"Hazard Detected: {hazard}")
        self.logger.info(f"Target Speed: {target_speed:.2f}, Current Speed: {curr_speed:.2f}")
        self.logger.info(f"Waypoint Queue: {len(self._waypoints_queue)}, Buffer: {len(self._waypoint_buffer)}")
