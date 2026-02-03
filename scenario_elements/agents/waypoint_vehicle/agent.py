import os
import time
import copy
import math
import numpy as np

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import unary_union
from collections import deque

from scenario_elements.agents.base import AgentBase
from scenario_elements.config import Waypoint

from tools.logger_tools import get_instance_logger

from loguru import logger

from .pid import PIDController

class WaypointVehicleConfig(BaseModel):
    
    id: str = Field(..., description="Unique identifier of the NPC vehicle")
    model: str = Field(..., description="Vehicle model name")
    rolename: str = Field(..., description="Role name, e.g., 'ego' or 'npc'")
    
    category: Optional[str] = Field("car", description="Vehicle category, e.g., 'car'")
    trigger_time: float = Field(..., ge=0, description="Time to start moving (seconds)")
    route: List[Waypoint] = Field(
        ..., description="List of waypoints describing the route"
    )
    
    def get_initial_waypoint(self) -> Waypoint:
        return self.route[0]
    
def get_basic_config():
    return {
        "max_speed": 15.0,
        "max_speed_junction": 10.0,
        "max_acceleration": 6.0,
        "max_deceleration": -6.0,
        "max_steering": 0.8,
        "collision_threshold": 5.0,
        "ignore_vehicle": True,
        "ignore_walker": True,
        "ignore_static_obstacle": True,
        "ignore_traffic_light": True,
        "min_distance": 6.0, # to filter next waypoint
        "collision_distance_threshold": 5.0,
        "pid_lateral_cfg": {
            'K_P': 1.3,
            'K_D': 0.05,
            'K_I': 0.01,
        },
        "pid_longitudinal_cfg": {
            'K_P': 1.0,
            'K_D': 0.02,
            'K_I': 0.1,
        },
        "remove_after_finish" : False
    }

def get_polygon(location_x, location_y, length, width, back_edge_to_center, heading, buffer: float = 0.0) -> Polygon:
    half_w = width / 2.0
    front_l = length - back_edge_to_center + buffer
    back_l = -1 * back_edge_to_center
    sin_h, cos_h = math.sin(heading), math.cos(heading)
    vectors = [
        (front_l * cos_h - half_w * sin_h, front_l * sin_h + half_w * cos_h),
        (back_l * cos_h - half_w * sin_h, back_l * sin_h + half_w * cos_h),
        (back_l * cos_h + half_w * sin_h, back_l * sin_h - half_w * cos_h),
        (front_l * cos_h + half_w * sin_h, front_l * sin_h - half_w * cos_h)
    ]
    return Polygon([[location_x + x, location_y + y] for x, y in vectors])

class WaypointVehicleAgent(AgentBase):
    
    prefix = 'waypoint_vehicle'
    MIN_DISTANCE_PERCENTAGE = 0.95
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
        super(WaypointVehicleAgent, self).__init__(
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
        self.debug_folder = os.path.join(self.output_folder, f"debug/{self.prefix}")
        self.user_parameters = self.other_config.get('parameters', {})
        
        # actor configs
        self.actor_config_py: WaypointVehicleConfig = WaypointVehicleConfig.model_validate(self.actor_config)
        self.route = [wp.model_dump() for wp in self.actor_config_py.route] # convert to dict
        self.trigger_time = self.actor_config_py.trigger_time

        parameters = get_basic_config()
        parameters.update(self.user_parameters)
        self._configure_parameters(parameters)
        self._initialize_waypoints()

        self._controller = PIDController(self.pid_long_cfg, self.pid_lat_cfg)
        self._last_move_time = 0.0
        self._dt = 1.0 / self.running_frequency
        self.step = 0
        self.last_move_time = 0.0
        
        if self.debug:
            os.makedirs(self.debug_folder, exist_ok=True)
            log_file = os.path.join(self.debug_folder, f"{self.prefix}_{self.id}.log")
            if os.path.exists(log_file):
                os.remove(log_file)
            self.logger = get_instance_logger(f"{self.prefix}_{self.id}", log_file)
            self.logger.info(f"Logger initialized for {self.prefix}_{self.id}")
        else:
            self.logger = None

    def _configure_parameters(self, parameters):
        self._ignore_vehicle = parameters.get('ignore_vehicle', False)
        self._ignore_walker = parameters.get('ignore_walker', False)
        self._ignore_static_obstacle = parameters.get('ignore_static_obstacle', False)
        self._ignore_traffic_light = parameters.get('ignore_traffic_light', False)
        self._max_speed = parameters.get('max_speed', 25.0)
        self._max_speed_junction = parameters.get('max_speed_junction', 10.0)
        self._min_distance = parameters.get('min_distance', 2.0) * self.MIN_DISTANCE_PERCENTAGE
        self._max_acceleration = parameters.get('max_acceleration', 6.0)
        self._max_deceleration = parameters.get('max_deceleration', -6.0)
        self._max_steering = parameters.get('max_steering', 0.8)
        self._collision_threshold = parameters.get('collision_threshold', 5.0)
        self._remove_after_finish = parameters.get('remove_after_finish', False)
        self._collision_distance_threshold = parameters.get('collision_distance_threshold', 5.0)
        self._buffer_size = 5
        self.pid_lat_cfg = parameters.get('pid_lateral_cfg', {'K_P': 1.0, 'K_D': 0.01, 'K_I': 0.0})
        self.pid_long_cfg = parameters.get('pid_longitudinal_cfg', {'K_P': 1.0, 'K_D': 0.01, 'K_I': 0.0})

    def _initialize_waypoints(self):
        self._waypoints_queue = deque(self.route[1:], maxlen=5000)
        self._waypoint_buffer = deque(maxlen=self._buffer_size)
        self._initial_waypoint = self.route[0] if self.route else None

    def _tick(self, snapshot: Dict):
        self.step += 1
        start = time.time()
        
        if not self._waypoints_queue and not self._waypoint_buffer:
            self.task_finished = True
            self._apply_control(0.0, 1.0, 0.0)
            return

        while len(self._waypoint_buffer) < self._buffer_size and self._waypoints_queue:
            self._waypoint_buffer.append(self._waypoints_queue.popleft())

        target_wp = copy.deepcopy(self._waypoint_buffer[0])
                
        target_speed = min(target_wp['speed'], self._max_speed)
        target_loc = target_wp['location']

        actor_info = snapshot['actors'][self.id]
        curr_loc = actor_info['location']
        curr_heading = curr_loc['yaw']
        curr_speed = actor_info['speed']
        
        time_info = snapshot.get('time', {})
        current_game_time = time_info.get('game_time', 0.0)
        
        # not started yet
        if current_game_time < self.trigger_time:
            self._apply_control(0.0, 1.0, 0.0)
            self.task_finished = False
            self._last_move_time = current_game_time
            return
        
        if curr_speed <= 0.001:
            delta_time = current_game_time - self._last_move_time
            if delta_time > 30.0:
                self.task_finished = True
        else:
            self._last_move_time = current_game_time
            self.task_finished = False

        if self._obstacle_detected(actor_info, snapshot['actors'], self._dt):
            target_speed = 0.0

        throttle, brake, steer = self._controller.run_step(
            curr_loc, curr_speed, curr_heading,
            target_loc, target_speed, self._dt)

        self._apply_control(throttle, brake, steer)
        self._purge_waypoints(curr_speed)

        if self.debug and self.step % 10 == 0:
            self._log_debug_state(throttle, brake, steer, target_wp, actor_info, time.time() - start)

    def _apply_control(self, throttle, brake, steer):
        self.sandbox_operator.sim.apply_vehicle_control(self.id, {
            'throttle': throttle,
            'brake': brake,
            'steer': steer,
            'reverse': False
        })

    def _purge_waypoints(self, curr_speed):
        curr_actor_info = self.sandbox_operator.sim.get_actor(self.id) # query again?
        # logger.debug(f"Purging waypoints for actor {self.id} {type(self.id)}, {curr_actor_info}")
        curr_loc = curr_actor_info['location']
        curr_point = Point(curr_loc['x'], curr_loc['y'])
        min_dist = max(curr_speed * 2.0 * self.MIN_DISTANCE_PERCENTAGE, self._min_distance)

        while self._waypoint_buffer:
            wp = self._waypoint_buffer[0]
            wp_point = Point(wp['location']['x'], wp['location']['y'])
            if wp_point.distance(curr_point) < min_dist:
                self._waypoint_buffer.popleft()
            else:
                break

    def _log_debug_state(self, throttle, brake, steer, target_wp, actor_info, elapsed):
        loc = actor_info['location']
        self.logger.info(f"============= Start Step {self.step} =============")
        self.logger.info(f"Elapsed: {elapsed:.3f}s")
        self.logger.info(f"Throttle: {throttle}, Brake: {brake}, Steer: {steer}")
        self.logger.info(f"Waypoint queue: {len(self._waypoints_queue)} | Buffer: {len(self._waypoint_buffer)}")
        self.logger.info(f"Target WP: ({target_wp['location']['x']}, {target_wp['location']['y']})")
        self.logger.info(f"Current Pos: ({loc['x']}, {loc['y']}), Yaw: {loc['yaw']}, Speed: {actor_info['speed']}")
        self.logger.info(f"Hazard Detected: {target_wp['speed'] == 0.0}")
        self.logger.info(f"============= End =============")

    def _obstacle_detected(self, actor_info: Dict, actor_dict: Dict[str, Dict], delta_t: float) -> bool:
        loc = actor_info['location']
        speed = actor_info['speed']
        acc = actor_info['acceleration']
        poly_pts = actor_info['polygon']
        bbox = actor_info['bbox']
        heading = loc['yaw']
        back_center = actor_info['back_edge_to_center']

        distance = speed * delta_t + 0.5 * acc * delta_t ** 2
        brake_dist = self._collision_distance_threshold + 1.5 * float(np.clip(distance, 0.0, None))

        trace = [[loc['x'], loc['y']]]
        poly_seq = [Polygon(poly_pts)]
        curr_pt = Point(loc['x'], loc['y'])

        for wp in self._waypoint_buffer:
            next_pt = Point(wp['location']['x'], wp['location']['y'])
            poly_seq.append(get_polygon(
                wp['location']['x'], wp['location']['y'],
                bbox['length'], bbox['width'],
                back_center, heading, buffer=1.0))
            trace.append(next_pt)
            if curr_pt.distance(next_pt) > brake_dist:
                break
            curr_pt = next_pt

        future_poly = unary_union(poly_seq)
        path_line = LineString(trace)

        for aid, ainfo in actor_dict.items():
            if aid == self.id:
                continue
            if self._ignore_static_obstacle and ainfo['category'].lower() == 'static':
                continue
            if self._ignore_vehicle and ainfo['category'].lower() == 'vehicle' and int(aid) > 1000:
                continue
            if self._ignore_walker and ainfo['category'].lower() == 'walker':
                continue

            other_poly = get_polygon(
                ainfo['location']['x'], ainfo['location']['y'],
                ainfo['bbox']['length'], ainfo['bbox']['width'],
                ainfo['bbox']['length'] / 2.0, ainfo['location']['yaw'], buffer=1.0)

            if future_poly.intersects(other_poly) or path_line.intersects(other_poly):
                return True

        return False
