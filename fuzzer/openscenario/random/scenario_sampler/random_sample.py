import os
import math
import copy
import random
import numpy as np

from tqdm import tqdm
from loguru import logger
from collections import deque
from omegaconf import DictConfig
from typing import Dict, Optional, Tuple, List
from shapely.geometry import Polygon, Point, LineString

from scenario_runner.sandbox_operator import SandboxOperator

from scenario_corpus.openscenario.config import (
    ScenarioConfig,
    ApolloConfig,
    WaypointVehicleConfig,
    WaypointWalkerConfig,
    StaticObstacleConfig,
    RuleLightConfig,
    MapConfig,
    LightConfig,
    RuleLightConfig,
    Waypoint, 
    Location, 
    Rotation, 
    LaneItem
)

from ..scenario_space import ScenarioODDSpace

class RandomSampler(object):
    
    MAX_ATTEMPTS = 20
    
    # NOTE: we need this, as the platform only supports int ids
    id_ego_init: int = 0  # start from 0
    id_npc_vehicle_init: int = 1000  # start from 1000
    id_npc_static_init: int = 2000
    id_npc_walker_init: int = 3000

    def __init__(
        self,
        scenario_space: ScenarioODDSpace,
        mutation_config: DictConfig, # this is the initial seed/scenario config
    ):
        self.scenario_space = scenario_space
        self.mutation_config = mutation_config # includes seed file & map file
        
        # apis
        self.sandbox_api = None 
        
        # sub attributes
        self.ego_space = self.scenario_space.ego_space
        self.npc_vehicle_space = self.scenario_space.npc_vehicle_space
        self.npc_walker_space = self.scenario_space.npc_pedestrian_space
        self.npc_static_space = self.scenario_space.npc_static_space
        self.traffic_light_space = self.scenario_space.traffic_light_space
        self.map_region_space = self.scenario_space.map_region_space
        
        # fixed parameters here
        self._waypoint_sample_interval = 2.0  # in meters
        
    ##### Map related utils ########    
    def extract_map_lanes(
        self,
        region_points: List[List[float]],
        forbidden_region_points: Optional[List[List[float]]] = None
    ) -> List[str]:
        
        # 1. get all lanes in the map region - driving lanes only
        coarse_region = Polygon(region_points)
        if forbidden_region_points is not None and len(forbidden_region_points) >= 3:
            forbidden_region = Polygon(forbidden_region_points)
        else:
            forbidden_region = None
        
        map_lanes = self.sandbox_api.map.lane.get_all(True, "CITY_DRIVING")
        valid_lanes = []
        forbidden_lanes = []
        for lane_id in tqdm(map_lanes):
            lane_center_curve_points = self.sandbox_api.map.lane.get_central_curve(lane_id)
            lane_center_curve = LineString(lane_center_curve_points)
            if lane_center_curve.intersects(coarse_region):
                valid_lanes.append(lane_id)
                if forbidden_region is not None:
                    if lane_center_curve.intersects(forbidden_region):
                        forbidden_lanes.append(lane_id)
                        
        valid_lanes = list(set(valid_lanes))
        forbidden_lanes = list(set(forbidden_lanes))
        
        # 2. get all crosswalks in the map region
        map_crosswalks = self.sandbox_api.map.crosswalk.get_all()
        valid_crosswalks = []
        for crosswalk_id in tqdm(map_crosswalks):
            crosswalk_polygon_points = self.sandbox_api.map.crosswalk.get_polygon(crosswalk_id)
            crosswalk_polygon = Polygon(crosswalk_polygon_points)
            if crosswalk_polygon.intersects(coarse_region):
                valid_crosswalks.append(crosswalk_id)
        valid_crosswalks = list(set(valid_crosswalks))
        
        return valid_lanes, forbidden_lanes, valid_crosswalks
    
    @staticmethod
    def get_polygon_points(
        location: dict,
        rotation: dict,
        bbox: dict,
        back_edge_to_center: float
    ) -> Tuple[Tuple[float]]:
        # this gets current polygon
        half_w = bbox['width'] / 2.0

        front_l = bbox['length'] - back_edge_to_center
        back_l = -1 * back_edge_to_center

        sin_h = math.sin(rotation['yaw'])
        cos_h = math.cos(rotation['yaw'])
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
    
    def update_occupied_polygons(
        self, 
        actor_type: str,
        target_waypoints: List[Waypoint],
        occupied_polygons: List[Polygon]
    ):
        actor_bp = self.sandbox_api.sim.get_actor_blueprint(actor_type)
        for target_waypoint in target_waypoints:
            actor_polygon_points = self.get_polygon_points(
                location=target_waypoint.location.model_dump(),
                rotation=target_waypoint.rotation.model_dump(),
                bbox=actor_bp['bbox'],
                back_edge_to_center=actor_bp['back_edge_to_center'] if 'back_edge_to_center' in actor_bp else actor_bp['bbox']['length'] / 2.0
            )
            actor_polygon = Polygon(actor_polygon_points)
            occupied_polygons.append(actor_polygon)
        return occupied_polygons
    
    def is_waypoint_free(
        self,
        actor_type: str,
        target_waypoint: Waypoint,
        occupied_polygons: List[Polygon],
        threshold: float = 0.1
    ) -> bool:
        """
        Return: True -> No conflict, can be created
        """
        actor_bp = self.sandbox_api.sim.get_actor_blueprint(actor_type)
        actor_polygon_points = self.get_polygon_points(
            location=target_waypoint.location.model_dump(),
            rotation=target_waypoint.rotation.model_dump(),
            bbox=actor_bp['bbox'],
            back_edge_to_center=actor_bp['back_edge_to_center'] if 'back_edge_to_center' in actor_bp else actor_bp['bbox']['length'] / 2.0
        )
        actor_polygon = Polygon(actor_polygon_points)

        for conflict_region in occupied_polygons:
            if actor_polygon.distance(conflict_region) < threshold:
                return False
        return True
    
    ######## Route Related Utils ########
    def find_potential_route_lanes(
        self,
        lanes: List[str],
        forbidden_lanes: List[str],
        max_depth: int = 10,
        include_prefix: bool = True,
    ):
        """
        Find potential lane routes within the given lane set.

        Rules:
        - Forbidden lanes are NOT used as start lanes
        - Forbidden lanes are NOT allowed as terminal (end) lanes
        - Forbidden lanes may appear in the middle of a route
        """

        lane_set = set(lanes)
        forbidden_set = set(forbidden_lanes)

        # 1. Build adjacency list: lane_id -> successors (in-region only)
        graph: Dict[str, List[str]] = {}
        for lane_id in lanes:
            successors = self.sandbox_api.map.lane.get_successor_ids(lane_id, 1)
            graph[lane_id] = [s for s in successors if s in lane_set]

        # 2. BFS to enumerate routes
        all_routes: List[List[str]] = []

        for start_lane in graph:
            # ❌ forbidden lane cannot be start
            if start_lane in forbidden_set:
                continue

            queue = deque([(start_lane, [start_lane])])

            while queue:
                current_lane, path = queue.popleft()

                # 是否还能继续扩展
                expandable = (
                    len(path) < max_depth
                    and any(nxt not in path for nxt in graph[current_lane])
                )

                # 只有在「终止状态」且终止 lane 不在 forbidden 中，才收集
                if not expandable:
                    if current_lane not in forbidden_set:
                        all_routes.append(path)
                    continue

                # include_prefix：只在 prefix 的最后一个 lane 不 forbidden 时才加
                if include_prefix and current_lane not in forbidden_set:
                    all_routes.append(path)

                # 扩展
                for nxt in graph[current_lane]:
                    if nxt not in path:  # avoid cycles
                        queue.append((nxt, path + [nxt]))

        return all_routes

    @classmethod
    def has_route_lanes_conflict(
        route1: List[str],
        route2: List[str]
    ) -> bool:
        return bool(set(route1) & set(route2))  # Check if intersection is non-empty
    
    def _make_waypoint(
        self,
        lane_id: str,
        s: float,
        x: float,
        y: float,
        yaw: float,
        speed: float = 0.0,
    ) -> Waypoint:
        """
        yaw is in radians.
        """
        wp = Waypoint(
            lane=LaneItem(
                id=lane_id,
                s=s,
                l=0.0,
            ),
            location=Location(
                x=x,
                y=y,
                z=0.0,
            ),
            rotation=Rotation(
                pitch=0.0,
                yaw=yaw,  # convert to degrees
                roll=0.0,
            ),
            speed=speed
        )
        return wp

    def sample_lane_waypoints(
        self,
        lane_id: str,
        sample_interval: float = 2.0,
    ) -> List[Waypoint]:
        """
        Sample waypoints along a single lane using arc-length s.
        Heading (yaw) is in radians.
        """
        lane_length = self.sandbox_api.map.lane.get_length(lane_id)
        if lane_length <= 0:
            return []

        # robust arc-length grid
        s_values = np.arange(0.0, lane_length, sample_interval)
        if s_values.size == 0 or s_values[-1] < lane_length:
            s_values = np.append(s_values, lane_length)

        waypoints = []
        for s in s_values:
            x, y, heading = self.sandbox_api.map.lane.get_coordinate(lane_id, s, 0.0)
            waypoints.append(
                self._make_waypoint(lane_id, s, x, y, heading)
            )

        return waypoints

    def sample_route_waypoints(
        self,
        route: List[str],
    ) -> List[Waypoint]:
        """
        Sample waypoints along a route at fixed spatial intervals.
        Heading (yaw) is in radians.
        """
        interval = self._waypoint_sample_interval
        sampled_waypoints: List[Waypoint] = []

        prev_xy = None
        acc_dist = 0.0

        for lane_id in route:
            lane_wps = self.sample_lane_waypoints(
                lane_id,
                sample_interval=interval,
            )
            if not lane_wps:
                continue

            for wp in lane_wps:
                curr_xy = np.array([
                    wp.location.x,
                    wp.location.y,
                ])

                # first point of the entire route
                if prev_xy is None:
                    sampled_waypoints.append(wp)
                    prev_xy = curr_xy
                    acc_dist = 0.0
                    continue

                step_dist = np.linalg.norm(curr_xy - prev_xy)
                acc_dist += step_dist

                if acc_dist >= interval:
                    sampled_waypoints.append(wp)
                    acc_dist = 0.0
                    prev_xy = curr_xy

        return sampled_waypoints

    def _select_route(
        self,
        map_routes: List[List[str]],
        occupied_routes: List[List[str]],
        require_conflict: bool,
    ) -> Optional[List[str]]:

        if not map_routes:
            return None

        if not require_conflict or not occupied_routes:
            return random.choice(map_routes)

        conflict_routes = [
            r for r in map_routes
            if any(self.has_route_lanes_conflict(r, ex) for ex in occupied_routes)
        ]

        return random.choice(conflict_routes) if conflict_routes else random.choice(map_routes)

    ######## Ego vehicle generation ########    
    def sample_ego_vehicle(
        self,
        ego_id: int,
        map_routes: List[List[str]],
        occupied_polygons: List[Polygon]
    ) -> Optional[ApolloConfig]:
        """
        Generate a new ADS (Apollo) ego vehicle configuration.
        """
        
        # 1. Sample ego model
        ego_model = random.choice(self.ego_space.model_range)

        # 2. Sample route-level waypoints (spatially uniform)
        trace_lanes = random.choice(map_routes)
        route_waypoints = self.sample_route_waypoints(trace_lanes)
        if len(route_waypoints) < 2:
            return None

        # 3. Filter free waypoints
        free_indices = [
            i for i, wp in enumerate(route_waypoints)
            if self.is_waypoint_free(ego_model, wp, occupied_polygons=occupied_polygons, threshold=0.1)
        ]
        if len(free_indices) < 2:
            return None

        # 4. Sample a valid (start, end) segment by spatial distance
        min_length = self.ego_space.route_length_range[0]

        points = [
            np.array([
                route_waypoints[i].location.x,
                route_waypoints[i].location.y,
            ])
            for i in free_indices
        ]

        valid_segments = []
        for i, si in enumerate(free_indices):
            pi = points[i]
            for j in range(i + 1, len(free_indices)):
                sj = free_indices[j]
                pj = points[j]
                if np.linalg.norm(pj - pi) >= min_length:
                    valid_segments.append((si, sj))

        if not valid_segments:
            return None

        start_idx, end_idx = random.choice(valid_segments)
        selected_route = [
            route_waypoints[start_idx],
            route_waypoints[end_idx],
        ]

        # 6. Trigger time
        trigger_time = random.uniform(
            self.ego_space.trigger_time_range[0],
            self.ego_space.trigger_time_range[1],
        )

        # 7. Construct ApolloConfig
        return ApolloConfig(
            id=str(ego_id),
            model=ego_model,
            rolename="ego",
            category="car",
            route=selected_route,
            trigger_time=trigger_time,
        )

    ############################################
    # NPC Vehicle
    ############################################ 
    def _sample_route_segment_by_distance(
        self,
        waypoints: List[Waypoint],
        actor_type: str,
        min_length: float,
        threshold: float,
        occupied_polygons: List[Polygon],
    ) -> Optional[List[Waypoint]]:
        free_indices = [
            i for i, wp in enumerate(waypoints)
            if self.is_waypoint_free(actor_type, wp, occupied_polygons=occupied_polygons, threshold=threshold)
        ]
        if len(free_indices) < 2:
            return None

        points = [
            np.array([waypoints[i].location.x, waypoints[i].location.y])
            for i in free_indices
        ]

        valid_segments = []
        for i, si in enumerate(free_indices):
            pi = points[i]
            for j in range(i + 1, len(free_indices)):
                sj = free_indices[j]
                pj = points[j]
                if np.linalg.norm(pj - pi) >= min_length:
                    valid_segments.append((si, sj))

        if not valid_segments:
            return None

        s_idx, e_idx = random.choice(valid_segments)
        return waypoints[s_idx:e_idx + 1]
    
    def _assign_smooth_speeds(
        self,
        waypoints: List[Waypoint],
        speed_range: tuple,
        delta_max: float,
        keep_prob: float = 0.7,
    ) -> List[Waypoint]:
        prev_speed = random.uniform(*speed_range)

        for i, wp in enumerate(waypoints):
            if i > 0 and random.random() < keep_prob:
                target_speed = prev_speed
            else:
                target_speed = prev_speed + random.uniform(-delta_max, delta_max)

            target_speed = float(np.clip(target_speed, *speed_range))
            wp.speed = target_speed
            prev_speed = target_speed
            
            waypoints[i] = wp
        return waypoints


    def sample_npc_vehicle(
        self,
        actor_id: int,
        map_routes: List[List[str]],
        occupied_polygons: List[Polygon]
    ) -> Optional[WaypointVehicleConfig]:
        """
        Generate a waypoint-follower NPC vehicle.
        """

        # 1. Select route
        npc_trace_lanes = random.choice(map_routes)
        if not npc_trace_lanes:
            return None

        # 2. Sample NPC model
        npc_actor_type = random.choice(self.npc_vehicle_space.model_range)

        # 3. Sample route-level waypoints (once)
        route_wps = self.sample_route_waypoints(npc_trace_lanes)
        if len(route_wps) < 2:
            return None

        # 4. Sample a valid route segment by spatial distance
        npc_valid_route = self._sample_route_segment_by_distance(
            waypoints=route_wps,
            actor_type=npc_actor_type,
            min_length=self.npc_vehicle_space.route_length_range[0],
            threshold=5.0,   # NPC safety margin
            occupied_polygons=occupied_polygons
        )
        if not npc_valid_route or len(npc_valid_route) < 2:
            return None

        # 5. Assign smooth speeds
        self._assign_smooth_speeds(
            waypoints=npc_valid_route,
            speed_range=self.npc_vehicle_space.speed_range,
            delta_max=float(self.npc_vehicle_space.delta_speed),
        )

        # 6. Trigger time
        npc_trigger_time = random.uniform(
            self.npc_vehicle_space.trigger_time_range[0],
            self.npc_vehicle_space.trigger_time_range[1],
        )

        return WaypointVehicleConfig(
            id=str(actor_id),
            model=npc_actor_type,
            rolename="npc_vehicle",
            category="car",
            trigger_time=npc_trigger_time,
            route=npc_valid_route,
        )

    ############################################
    # NPC Static
    ############################################
    def sample_npc_static_lane(
        self,
        map_lanes: Optional[List[str]] = None,
        mode: str = "random",
        existing_routes: Optional[List[List[str]]] = None,
    ) -> Optional[str]:
        if not map_lanes:
            return None

        existing_routes = existing_routes or []
        max_attempts = max(1, getattr(self, "MAX_ATTEMPTS", 1))

        if mode == "random":
            return random.choice(map_lanes)

        if mode == "conflict":
            for _ in range(max_attempts):
                lane = random.choice(map_lanes)
                if any(self.has_route_conflict([lane], route) for route in existing_routes):
                    return lane
            return random.choice(map_lanes)

        if mode == "non-conflict":
            for _ in range(max_attempts):
                lane = random.choice(map_lanes)
                if all(not self.has_route_conflict([lane], route) for route in existing_routes):
                    return lane
            return random.choice(map_lanes)

        raise ValueError(f"Invalid mode: {mode!r}. Expected 'random', 'conflict', or 'non-conflict'.")
        
    def generate_npc_static(
        self,
        actor_id: int,
        map_lanes: Optional[List[str]] = None,
        mode: str = "random",
        existing_routes: Optional[List[List[str]]] = None,
    ) -> Optional[StaticObstacleConfig]:
        if not map_lanes:
            return None

        existing_routes = existing_routes or []

        for _ in range(self.MAX_ATTEMPTS):
            selected_lane = self.sample_npc_static_lane(
                map_lanes=map_lanes,
                mode=mode,
                existing_routes=existing_routes
            )
            if not selected_lane:
                continue

            left_wps, right_wps = self.sample_boundary_waypoints(selected_lane)
            all_wps = left_wps + right_wps
            if len(all_wps) == 0:
                continue

            # Select only unoccupied waypoints
            unoccupied = [
                wp for wp in all_wps
                if self.is_waypoint_free(self._npc_static_actor_type, wp, threshold=5.0)[0]
            ]
            if not unoccupied:
                continue

            selected_wp = random.choice(unoccupied)

            return NPCStaticConfig(
                id=actor_id,
                category=self._npc_static_actor_type,
                waypoint=selected_wp,
            )

        return None

    ############################################
    # NPC Walker
    ############################################
    @staticmethod
    def sample_npc_walker_crosswalk(region_crosswalks) -> Optional[str]:
        if len(region_crosswalks) == 0:
            return None
        return random.choice(region_crosswalks)
    
    def generate_npc_walker(
        self,
        actor_id: int,
        region_crosswalks: List[str]
    ) -> Optional[WaypointWalkerConfig]:
        if not region_crosswalks:
            return None

        for _ in range(self.MAX_ATTEMPTS):
            crosswalk_id = self.sample_npc_walker_crosswalk(region_crosswalks)
            if not crosswalk_id:
                continue

            waypoints = self.sample_crosswalk_waypoints(crosswalk_id)
            if len(waypoints) < 2:
                continue  # Skip too-short or invalid crosswalks

            prev_speed = 0.0
            for i, wp in enumerate(waypoints):
                delta = np.clip(
                    self._npc_walker_delta_speed_max * random.gauss(0, 1),
                    -self._npc_walker_delta_speed_max,
                    self._npc_walker_delta_speed_max
                )
                speed = float(np.clip(
                    prev_speed + delta,
                    self._npc_walker_speed_min,
                    self._npc_walker_speed_max
                ))

                if i > 0 and random.random() < 0.7:
                    speed = prev_speed  # Smooth step

                wp["speed"] = speed
                prev_speed = speed

            trigger_time = random.uniform(
                self._npc_walker_trigger_time_min,
                self._npc_walker_trigger_time_max
            )

            return NPCWalkerConfig(
                id=actor_id,
                category=self._npc_walker_actor_type,
                route=waypoints,
                trigger_time=trigger_time
            )

        return None

    ############################################
    # Traffic Light
    ############################################
    def sample_traffic_light(
        self
    ) -> Optional[RuleLightConfig]:
        
        traffic_light_ids = self.sandbox_api.map.traffic_light.get_all()
        if not traffic_light_ids:
            return None

        light_configs = []
        for tl_id in traffic_light_ids:
            conflicts, equals = self.sandbox_api.map.traffic_light.get_related_lights(tl_id)
            light_configs.append(LightConfig(
                id=tl_id,
                category="traffic_light",
                conflicts=conflicts,
                equals=equals
            ))

        tl_pattern = random.choice(self.traffic_light_space.pattern_range)
        if tl_pattern == "force_green":
            force_green = True
        else:
            force_green = False
            
        force_green = True

        config = RuleLightConfig(
            id='traffic_light_agent',
            lights=light_configs,
            green_time=random.uniform(self.traffic_light_space.green_duration_range[0], self.traffic_light_space.green_duration_range[1]),
            yellow_time=random.uniform(self.traffic_light_space.yellow_duration_range[0], self.traffic_light_space.yellow_duration_range[1]),
            red_time=random.uniform(self.traffic_light_space.red_duration_range[0], self.traffic_light_space.red_duration_range[1]),
            initial_seed=random.randint(0, 10000),
            force_green=force_green
        )

        return config
    
    def sample(
        self,
        sandbox_container_name: str
    ) -> ScenarioConfig:
        # reset
        self.sandbox_api = SandboxOperator(
            container_name=sandbox_container_name
        )
        
        # load map
        self.sandbox_api.load_map(
            self.map_region_space.map_name
        )
        
        # load cache if possible
        if len(self.map_region_space.potential_route_lanes) == 0:
            if len(self.map_region_space.driving_lanes) == 0:
                valid_lanes, forbidden_lanes, valid_crosswalks = self.extract_map_lanes(
                    region_points=self.map_region_space.region_points,
                    forbidden_region_points=self.map_region_space.forbidden_region_points
                )
                self.map_region_space.driving_lanes = valid_lanes
                self.map_region_space.forbidden_lanes = forbidden_lanes
                self.map_region_space.crosswalks = valid_crosswalks
            
            potential_routes = self.find_potential_route_lanes(
                lanes=self.map_region_space.driving_lanes,
                forbidden_lanes=self.map_region_space.forbidden_lanes,
                max_depth=10,
                include_prefix=True
            )
            self.map_region_space.potential_route_lanes = potential_routes
            
            logger.debug(f"Total driving lanes in map region: {len(self.map_region_space.driving_lanes)}, details: {self.map_region_space.driving_lanes}")
            logger.debug(f"Total forbidden driving lanes in map region: {len(self.map_region_space.forbidden_lanes)}, details: {self.map_region_space.forbidden_lanes}")
            logger.debug(f"Total crosswalks in map region: {len(self.map_region_space.crosswalks)}")
            logger.debug(f"Total potential routes in map region: {len(potential_routes)}")
        
        # Determine actor counts
        num_ego = random.randint(self.ego_space.num_range[0], self.ego_space.num_range[1])
        num_npc_vehicle = random.randint(self.npc_vehicle_space.num_range[0], self.npc_vehicle_space.num_range[1])

        # common parameters
        occupied_polygons = []
        
        # Generate ego vehicles
        ego_lst = []
        ego_id = self.id_ego_init
        
        for _ in range(self.MAX_ATTEMPTS * num_ego):
            if len(ego_lst) >= num_ego:
                break
            
            ego_config = self.sample_ego_vehicle(
                ego_id,
                map_routes=self.map_region_space.potential_route_lanes,
                occupied_polygons=occupied_polygons
            )
            
            if ego_config:
                ego_lst.append(copy.deepcopy(ego_config))
                occupied_polygons = self.update_occupied_polygons(
                    actor_type=ego_config.model,
                    target_waypoints=[ego_config.route[0], ego_config.route[-1]],
                    occupied_polygons=occupied_polygons
                )
                ego_id += 1

        if len(ego_lst) < self.ego_space.num_range[0]:
            return None  # Not enough EGO vehicles, skip this scenario

        # Generate NPC vehicles
        npc_vehicle_lst = []
        npc_vehicle_id = self.id_npc_vehicle_init
        for _ in range(self.MAX_ATTEMPTS * num_npc_vehicle):
            if len(npc_vehicle_lst) >= num_npc_vehicle:
                break
            config = self.sample_npc_vehicle(
                npc_vehicle_id,
                map_routes=self.map_region_space.potential_route_lanes,
                occupied_polygons=occupied_polygons
            )
            if config:
                npc_vehicle_lst.append(copy.deepcopy(config))
                occupied_polygons = self.update_occupied_polygons(
                    actor_type=config.model,
                    target_waypoints=[config.route[0], config.route[-1]],
                    occupied_polygons=occupied_polygons
                )
                npc_vehicle_id += 1

        # Generate NPC static objects
        npc_static_lst = []
        
        # Generate NPC walkers
        npc_walker_lst = []

        # Generate traffic light config
        traffic_light_config = self.sample_traffic_light()

        # Build the new scenario based on previous config
        new_scenario = ScenarioConfig(
            id="sampled_scenario",
            scenario_type="openscenario",
            ego_vehicles=ego_lst,
            npc_vehicles=npc_vehicle_lst,
            npc_walkers=npc_walker_lst,
            npc_statics=npc_static_lst,
            traffic_light=traffic_light_config,
            map_region=MapConfig(
                map_name=self.map_region_space.map_name,
                coarse_points=self.map_region_space.region_points,
                lanes=self.map_region_space.driving_lanes,
                crosswalks=self.map_region_space.crosswalks
            )
        )

        # Log summary
        logger.debug(
            f"New scenario generated:\n"
            f"ID: {new_scenario.id}\n"
            f"EGO_NUM: {len(ego_lst)}\n"
            f"NPC_VEHICLE_NUM: {len(npc_vehicle_lst)}\n"
            f"NPC_WALKER_NUM: {len(npc_walker_lst)}\n"
            f"NPC_STATIC_NUM: {len(npc_static_lst)}"
        )
        
        # clost api
        self.sandbox_api.close()
        
        return new_scenario