import time
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
    RuleLightConfig,
    MapConfig,
    LightConfig,
    RuleLightConfig,
    Waypoint, 
    Location, 
    Rotation, 
    LaneItem
)

from .scenario_space import ScenarioODDSpace

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
    
    def reset(self, sandbox_container_name: str):
        # reset
        self.sandbox_api = SandboxOperator(
            container_name=sandbox_container_name
        )
        self.sandbox_api.sim.reset()
        
        # load map
        self.sandbox_api.load_map(
            self.map_region_space.map_name
        )
        # load cache if possible
        self._load_route_cache()
        
    def close(self):
        if self.sandbox_api is not None:
            self.sandbox_api.close()
            self.sandbox_api = None
        
    ##### Map related utils ########    
    def extract_map_lanes(
        self,
        region_points: List[List[float]],
        forbidden_region_points: Optional[List[List[float]]] = None,
        coarse_buffer: float = 20.0,
        forbidden_ratio: float = 0.8,
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        coarse_ratio:
            lane centerline 至少有 coarse_ratio 比例落在 coarse_region 内，才算 valid
        forbidden_ratio:
            lane centerline 至少有 forbidden_ratio 比例落在 forbidden_region 内，才算 forbidden
        """

        # 1. build regions
        coarse_region = Polygon(region_points)

        forbidden_region = None
        if forbidden_region_points is not None and len(forbidden_region_points) >= 3:
            forbidden_region = Polygon(forbidden_region_points)

        # 2. get all lanes)
        logger.debug(f"Sandbox API: {self.sandbox_api}")
        
        driving_lanes = self.sandbox_api.map.lane.get_all(True, "CITY_DRIVING")
        logger.debug(f"Total driving lanes in map: {len(driving_lanes)}")
        biking_lanes = self.sandbox_api.map.lane.get_all(True, "BIKING")
        all_lanes = set(driving_lanes + biking_lanes)

        valid_lanes = set()
        forbidden_lanes = set()

        for lane_id in tqdm(all_lanes):
            pts = self.sandbox_api.map.lane.get_central_curve(lane_id)
            if len(pts) < 2:
                continue

            lane_curve = LineString(pts)
            lane_len = lane_curve.length
            if lane_len == 0:
                continue

            # ---------- coarse region check ----------
            dist_to_coarse = lane_curve.distance(coarse_region)
            if dist_to_coarse > coarse_buffer:
                continue

            valid_lanes.add(lane_id)

            # ---------- forbidden region check ----------
            if forbidden_region is not None:
                forbidden_len = lane_curve.intersection(forbidden_region).length
                if forbidden_len / lane_len >= forbidden_ratio:
                    forbidden_lanes.add(lane_id)

        # 3. crosswalks
        map_crosswalks = self.sandbox_api.map.crosswalk.get_all()
        valid_crosswalks = set()

        for crosswalk_id in tqdm(map_crosswalks):
            polygon_pts = self.sandbox_api.map.crosswalk.get_polygon(crosswalk_id)
            if len(polygon_pts) < 3:
                continue

            crosswalk_polygon = Polygon(polygon_pts)
            if crosswalk_polygon.intersects(coarse_region):
                valid_crosswalks.add(crosswalk_id)

        return list(valid_lanes), list(forbidden_lanes), list(valid_crosswalks)
    
    # ------- load route cache -------
    def _load_route_cache(self):
        # load cache if possible
        if len(self.map_region_space.potential_route_lanes) == 0:
            if len(self.map_region_space.valid_lanes) == 0:
                valid_lanes, forbidden_lanes, valid_crosswalks = self.extract_map_lanes(
                    region_points=self.map_region_space.region_points,
                    forbidden_region_points=self.map_region_space.forbidden_region_points,
                    coarse_buffer=self.map_region_space.coarse_buffer,
                    forbidden_ratio=self.map_region_space.forbidden_ratio
                )
                self.map_region_space.valid_lanes = valid_lanes
                self.map_region_space.forbidden_lanes = forbidden_lanes
                self.map_region_space.crosswalks = valid_crosswalks
            
            potential_routes = self.find_potential_route_lanes(
                lanes=self.map_region_space.valid_lanes,
                forbidden_lanes=self.map_region_space.forbidden_lanes,
                max_depth=10,
                include_prefix=True
            )
            self.map_region_space.potential_route_lanes = potential_routes
            
            logger.debug(f"Total driving lanes in map region: {len(self.map_region_space.valid_lanes)}, details: {self.map_region_space.valid_lanes}")
            logger.debug(f"Total forbidden driving lanes in map region: {len(self.map_region_space.forbidden_lanes)}, details: {self.map_region_space.forbidden_lanes}")
            logger.debug(f"Total crosswalks in map region: {len(self.map_region_space.crosswalks)}")
            logger.debug(f"Total potential routes in map region: {len(potential_routes)}")
        
    ######## Polygon Related Utils ########    
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
    
    def update_occupation_cache(
        self, 
        actor_type: str,
        target_waypoints: List[Waypoint],
        occupation_cache: List[Dict]
    ) -> List[Dict]:
        new_occupation_cache = copy.deepcopy(occupation_cache)
        
        actor_bp = self.sandbox_api.sim.get_actor_blueprint(actor_type)
        for target_waypoint in target_waypoints:
            actor_polygon_points = self.get_polygon_points(
                location=target_waypoint.location.model_dump(),
                rotation=target_waypoint.rotation.model_dump(),
                bbox=actor_bp['bbox'],
                back_edge_to_center=actor_bp['back_edge_to_center'] if 'back_edge_to_center' in actor_bp else actor_bp['bbox']['length'] / 2.0
            )
            
            occupy_info = {
                'lane_id': target_waypoint.lane.id,
                's': target_waypoint.lane.s,
                'polygon_pts': copy.deepcopy(actor_polygon_points)
            }
            new_occupation_cache.append(occupy_info)
            
        return new_occupation_cache
    
    def is_waypoint_free(
        self,
        actor_type: str,
        target_waypoint: Waypoint,
        occupation_cache: List[Dict],
        same_lane_distance: float = 5.0,
        diff_lane_distance: float = 1.0
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
        
        # check conflicts
        for occupied_item in occupation_cache:
            conflict_lane_id = occupied_item['lane_id']
            # conflict_s = occupied_item['s']
            conflict_polygon_pts = occupied_item['polygon_pts']
            conflict_polygon = Polygon(conflict_polygon_pts)
            
            dist_poly = actor_polygon.distance(conflict_polygon)
            
            # same lane
            if conflict_lane_id == target_waypoint.lane.id:
                if dist_poly < same_lane_distance:
                    return False                
            else:
                # different lane
                if dist_poly < diff_lane_distance:
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
    
    def _make_waypoint(
        self,
        lane_id: str,
        s: float,
        l: float,
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
                l=l,
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
        sample_interval: float = 2.0
    ) -> List[Waypoint]:
        """
        Sample waypoints along a single lane using arc-length s.
        Heading (yaw) is in radians.
        l is default to 0.0 (centerline).
        """
        lane_length = self.sandbox_api.map.lane.get_length(lane_id)
        if lane_length <= 0:
            return []
        
        s_values = np.arange(0.0, lane_length, sample_interval)
        if s_values.size == 0 or s_values[-1] < lane_length:
            s_values = np.append(s_values, lane_length)

        waypoints = []
        for s in s_values:
            x, y, heading = self.sandbox_api.map.lane.get_coordinate(lane_id, s, 0.0)
            waypoints.append(
                self._make_waypoint(lane_id, s, 0.0, x, y, heading)
            )

        return waypoints

    def sample_route_waypoints(
        self,
        route: List[str],
        interval: float = 1.0
    ) -> Tuple[List[Waypoint], float]:
        """
        Sample waypoints along a route at fixed spatial intervals.
        Heading (yaw) is in radians.
        """
        sampled_waypoints: List[Waypoint] = []

        prev_xy = None
        acc_dist = 0.0
        route_length = 0.0

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
                route_length += step_dist

                if acc_dist >= interval:
                    sampled_waypoints.append(wp)
                    acc_dist = 0.0
                    prev_xy = curr_xy

        return sampled_waypoints, route_length

    ######## Ego vehicle generation ########    
    def generate_predefined_ego(
        self,
        ego_id: int,
        ego_route: List[List[float]]
    ) -> Optional[ApolloConfig]:
        """
        Generate a new ADS (Apollo) ego vehicle configuration.
        """
        
        if len(ego_route) < 2:
            logger.error("Predefined ego route must have at least start and end positions.")
            raise ValueError("Predefined ego route must have at least start and end positions.")
                
        start_position = ego_route[0]
        dest_position = ego_route[1]
        
        # 1. Sample ego model
        ego_model = random.choice(self.ego_space.model_range)
        
        # 2. find start point and end point
        start_lane_info = self.sandbox_api.map.lane.find_lane_id(
            start_position[0],
            start_position[1]
        )
        end_lane_info = self.sandbox_api.map.lane.find_lane_id(
            dest_position[0],
            dest_position[1]
        )
        
        # if start_lane_info is None or end_lane_info is None:
        #     raise ValueError("Cannot find lane for predefined ego start or end position.")

        start_lane_id, start_lane_s = start_lane_info['lane_id'], start_lane_info['s']
        end_lane_id, end_lane_s = end_lane_info['lane_id'], end_lane_info['s']
        
        if start_lane_id is None or end_lane_id is None:
            logger.error("Cannot find lane for predefined ego start or end position.")
            raise ValueError("Cannot find lane for predefined ego start or end position.")
        
        waypoints = []
        x, y, heading = self.sandbox_api.map.lane.get_coordinate(start_lane_id, start_lane_s, 0.0)
        waypoints.append(
            self._make_waypoint(start_lane_id, start_lane_s, 0.0, x, y, heading)
        )
        logger.debug(f"Ego start lane: {start_lane_id}, s: {start_lane_s}")
        logger.debug(f"Ego end lane: {end_lane_id}, s: {end_lane_s}")
        x, y, heading = self.sandbox_api.map.lane.get_coordinate(end_lane_id, end_lane_s, 0.0)
        waypoints.append(
            self._make_waypoint(end_lane_id, end_lane_s, 0.0, x, y, heading)
        )

        # 7. Construct ApolloConfig
        return ApolloConfig(
            id=str(ego_id),
            model=ego_model,
            rolename="ego",
            category="car",
            route=waypoints,
            trigger_time=0.0          
        )
        
    ############################################
    # NPC Vehicle
    ############################################     
    def sample_npc_vehicle(
        self,
        actor_id: int,
        map_routes: List[List[str]],
        occupation_cache: List[Dict]
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
        route_waypoints, route_length = self.sample_route_waypoints(npc_trace_lanes, interval=self.npc_vehicle_space.route_interval)
        if len(route_waypoints) < 2:
            return None
        
        if route_length < self.npc_vehicle_space.route_length_range[0] or route_length > self.npc_vehicle_space.route_length_range[1]:
            return None
        
        # 4. Filter occpuied waypoints
        free_waypoints = []
        for wp in route_waypoints:
            if self.is_waypoint_free(
                actor_type=npc_actor_type,
                target_waypoint=wp,
                occupation_cache=occupation_cache,
                same_lane_distance=self.scenario_space.ego_space.dist2vehicle_same_lane,
                diff_lane_distance=self.scenario_space.ego_space.dist2vehicle_other_lane
            ):
                free_waypoints.append(wp)
                
        if len(free_waypoints) < 2:
            return None
        
        # 5. sample valid route segment
        forbidden_region = (
            Polygon(self.map_region_space.forbidden_region_points)
            if self.map_region_space.forbidden_region_points
            and len(self.map_region_space.forbidden_region_points) >= 3
            else None
        )
        
        start_idx, end_idx = -1, -1
        for _ in range(self.MAX_ATTEMPTS):
            idx_i, idx_j = random.sample(range(len(free_waypoints)), 2)
            if idx_i > idx_j:
                idx_i, idx_j = idx_j, idx_i

            wpi = free_waypoints[idx_i]
            wpj = free_waypoints[idx_j]
            route_wps = free_waypoints[idx_i:idx_j + 1]
            
            pi = np.array([wpi.location.x, wpi.location.y])
            pj = np.array([wpj.location.x, wpj.location.y])
            route_path = [
                np.array([wp.location.x, wp.location.y])
                for wp in route_wps
            ]

            # Should (1) pass forbidden region check and (2) endpoints not in forbidden region
            if forbidden_region is not None:
                segment = LineString(route_path)
                inter = segment.intersection(forbidden_region)

                if inter.is_empty or inter.length == 0:
                    continue
                
                if (
                    forbidden_region.contains(Point(pi)) or
                    forbidden_region.contains(Point(pj))
                ):
                    # can not in the forbidden region
                    continue
                
                dist_i2f = Point(pi).distance(forbidden_region)
                if dist_i2f < self.npc_vehicle_space.endpoint_dist2forbidden_region:
                    continue
                
                dist_j2f = Point(pj).distance(forbidden_region)
                if dist_j2f < self.npc_vehicle_space.endpoint_dist2forbidden_region:
                    continue

            start_idx, end_idx = idx_i, idx_j
            break
        
        if start_idx == -1 or end_idx == -1:
            return None
        
        npc_valid_waypoints = free_waypoints[start_idx:end_idx + 1]
        if len(npc_valid_waypoints) < 2:
            return None
        
        # 5. Assign smooth speeds
        prev_speed = random.uniform(self.npc_vehicle_space.speed_range[0], self.npc_vehicle_space.speed_range[1])
        delta_speed = self.npc_vehicle_space.delta_speed # max change per waypoint

        for i, wp in enumerate(npc_valid_waypoints):
            if i > 0 and random.random() < 0.5:
                target_speed = prev_speed
            else:
                target_speed = prev_speed + random.uniform(-delta_speed, delta_speed)

            target_speed = float(np.clip(target_speed, *self.npc_vehicle_space.speed_range))
            wp.speed = target_speed
                        
            npc_valid_waypoints[i] = wp

            prev_speed = target_speed
            
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
            route=npc_valid_waypoints,
        )

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
        self
    ) -> ScenarioConfig:
        # call reset first
        
        # Determine actor counts
        num_npc_vehicle = random.randint(self.npc_vehicle_space.num_range[0], self.npc_vehicle_space.num_range[1])
        
        # common parameters
        occupation_cache = []
        
        # generate ego vehicle
        predefined_ego_route = self.scenario_space.ego_space.route
        
        ego_id = self.id_ego_init
        ego_config = self.generate_predefined_ego(
            ego_id,
            predefined_ego_route
        )
        
        if ego_config is None:
            logger.error("Failed to generate predefined ego vehicle.")
            raise ValueError("Failed to generate predefined ego vehicle.")
        
        occupation_cache = self.update_occupation_cache(
            actor_type=ego_config.model,
            target_waypoints=ego_config.route,
            occupation_cache=occupation_cache
        )
        
        
        # Generate NPC vehicles
        npc_vehicle_lst = []
        npc_vehicle_id = self.id_npc_vehicle_init
        for _ in range(self.MAX_ATTEMPTS * num_npc_vehicle):
            if len(npc_vehicle_lst) >= num_npc_vehicle:
                break
            
            config = self.sample_npc_vehicle(
                npc_vehicle_id,
                map_routes=self.map_region_space.potential_route_lanes,
                occupation_cache=occupation_cache
            )
            
            if config:
                npc_vehicle_lst.append(copy.deepcopy(config))
                occupation_cache = self.update_occupation_cache(
                    actor_type=config.model,
                    target_waypoints=[config.route[0], config.route[-1]],
                    occupation_cache=occupation_cache
                )
                npc_vehicle_id += 1
                
        # Generate NPC statics
        npc_static_lst = []
        
        # Generate NPC walkers
        npc_walker_lst = []

        # Generate traffic light config
        traffic_light_config = self.sample_traffic_light()

        # Build the new scenario based on previous config
        new_scenario = ScenarioConfig(
            id="sampled_scenario",
            scenario_type="openscenario_attxplore",
            ego_vehicles=[ego_config],
            npc_vehicles=npc_vehicle_lst,
            npc_walkers=npc_walker_lst,
            npc_statics=npc_static_lst,
            traffic_light=traffic_light_config,
            map_region=MapConfig(
                map_name=self.map_region_space.map_name,
                coarse_points=self.map_region_space.region_points,
                valid_lanes=self.map_region_space.valid_lanes,
                forbidden_lanes=self.map_region_space.forbidden_lanes,
                crosswalks=self.map_region_space.crosswalks
            )
        )

        # Log summary
        logger.debug(
            f"New scenario generated:\n"
            f"ID: {new_scenario.id}\n"
            f"NPC_VEHICLE_NUM: {len(npc_vehicle_lst)}"
        )
        
        # call close if needed
        return new_scenario