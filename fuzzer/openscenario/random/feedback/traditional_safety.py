import numpy as np

from loguru import logger
from tqdm import tqdm
from typing import List
from shapely.geometry import Polygon

from scenario_corpus.openscenario.config import ScenarioConfig

class  TraditionalSafetyFeedback(object):
    
    def __init__(self, config):
        self.config = config
        
        self.skip_start_frame = config.get("skip_start_frame", 0) # skip first 10 frames as initialization

        self.default_collision_feedback = 50.0
        self.default_dist2center_feedback = 0.0
        self.default_stuck_feedback = 0.0
        self.default_destination_feedback = 0.0
    
    def get_default_feedback(self) -> dict:        
        return {
            'collision_feedback': self.default_collision_feedback,
            'dist2center_feedback': self.default_dist2center_feedback,
            # we do not need the following two, no meaningful for traditional safety feedback
            'stuck_feedback': self.default_stuck_feedback,
            'destination_feedback': self.default_destination_feedback,
        }
        
    def get_single_feedback(self, feedback_dict: dict):
        # here we use collision score only
        # minimum is better
        return feedback_dict['collision_feedback']
    
    def get_multiple_feedback(self, feedback_dict: dict):
        # here we use all feedbacks
        return [
            feedback_dict['collision_feedback'], # min
            feedback_dict['dist2center_feedback'] # max
        ]
    
    def save_checkpoint(self, save_dir: str):
        pass
    
    def load_checkpoint(self, save_dir: str):
        pass
    
    
    def _calculate_scene_collision_dist2center_feedback(
        self, 
        scene_observation: dict,
        ego_ids: List[str]
    ) -> dict:
        current_scene = scene_observation
        actors = current_scene['snapshot']['actors']
        all_actor_ids = list(actors.keys())

        # feedback metrics
        min_distance = float('inf') # lower is better
        min_relative_speed = float('inf') # high is better, but need normalization
        min_collision_angle = 180.0  # 0° = head-on, 180° = opposite direction -> high is better

        for ego_id in ego_ids:
            
            ego_obs = actors[ego_id]
            
            # Ego states
            ego_loc = np.array([ego_obs['location']['x'], ego_obs['location']['y']])
            ego_yaw = ego_obs['location']['yaw'] # radius
            ego_speed = ego_obs['speed']

            # ego heading unit vector
            ego_dir = np.array([np.cos(ego_yaw),
                                np.sin(ego_yaw)])

            # polygon
            ego_poly = Polygon(ego_obs['polygon'])
            # others
            for other_id in all_actor_ids:
                if other_id == ego_id:
                    continue
                
                npc_obs = actors[other_id]
                npc_loc = np.array([npc_obs['location']['x'], npc_obs['location']['y']])
                npc_speed = npc_obs['speed']

                # polygon
                npc_poly = Polygon(npc_obs['polygon'])

                # ---------------------------
                # ① min polygon distance
                # ---------------------------
                d = ego_poly.distance(npc_poly)
                if d < min_distance:
                    min_distance = d

                # ---------------------------
                # ② relative speed
                # ---------------------------
                rel_speed = abs(ego_speed - npc_speed)
                if rel_speed < min_relative_speed:
                    min_relative_speed = rel_speed

                # ---------------------------
                # ③ collision angle
                # angle between ego heading and vector to NPC
                # ---------------------------
                vec_to_npc = npc_loc - ego_loc
                if np.linalg.norm(vec_to_npc) > 1e-6:
                    vec_to_npc_norm = vec_to_npc / np.linalg.norm(vec_to_npc)
                    dot = np.clip(np.dot(ego_dir, vec_to_npc_norm), -1, 1)
                    angle_deg = np.rad2deg(np.arccos(dot))  # 0° = head-on
                    if angle_deg < min_collision_angle:
                        min_collision_angle = angle_deg

        return {
            "min_distance": float(min_distance),
            "relative_speed": float(min_relative_speed),
            "collision_angle_deg": float(min_collision_angle),  # lower = more dangerous
            "dist2center": 0.0, # TODO: update this later
        }
    
    def _calculate_naive_stuck_dest_feedback(self, oracle_result: dict) -> dict:
        # NOTE: this is directly from oracle result
        runtime_results = oracle_result.get("runtime_results", {})
        max_distance_to_destination = 0.0
        max_stuck_time = 0.0
        for crietria_name, crietria_result in runtime_results.items():
            if "group_criteria" in crietria_name:
                for actor_id, actor_result in crietria_result.items():
                    distance_to_destination = actor_result["reach_destination"]["details"].get("distance_to_destination", 0.0)
                    if distance_to_destination > max_distance_to_destination:
                        max_distance_to_destination = distance_to_destination
                        
                    stuck_time = actor_result["stuck"]["details"].get("max_blocked_duration", 0.0)
                    if stuck_time > max_stuck_time:
                        max_stuck_time = stuck_time
            else:
                # single ads NOTE: actually, we only support single ADS now
                actor_result = crietria_result
                distance_to_destination = actor_result["reach_destination"]["details"].get("distance_to_destination", 0.0)
                if distance_to_destination > max_distance_to_destination:
                    max_distance_to_destination = distance_to_destination
                    
                stuck_time = actor_result["stuck"]["details"].get("max_blocked_duration", 0.0)
                if stuck_time > max_stuck_time:
                    max_stuck_time = stuck_time
        
        return {
            "stuck_feedback": max_stuck_time,
            "destination_feedback": max_distance_to_destination
        }
        
    def evaluate(
        self, 
        scenario_observation: List[dict], 
        oracle_result: dict,
        scenario_config: ScenarioConfig
    ):
        current_feedback = self.get_default_feedback()
        
        observation_length = len(scenario_observation)
        if observation_length <= self.skip_start_frame:
            logger.warning(f"Scenario observation length {observation_length} is less than or equal to skip_start_frame {self.skip_start_frame}. Returning zero feedbacks.")
            return current_feedback
        
        ego_ids = []
        for ego_cfg in scenario_config.ego_vehicles:
            ego_ids.append(ego_cfg.id)
        
        scenario_feedback = {}
        for i in tqdm(range(observation_length), desc="Evaluating scenario feedback"):
            
            if i < self.skip_start_frame:
                # skip beginning frames
                continue
            
            scene = scenario_observation[i]
            
            # naive collision feedback - min distance - first calculate collisions
            scene_col_dist = self._calculate_scene_collision_dist2center_feedback(
                scene_observation=scene,
                ego_ids=ego_ids
            )
            
            for k, v in scene_col_dist.items():
                if k not in scenario_feedback:
                    scenario_feedback[k] = []
                scenario_feedback[k].append(v)
            
        navie_stuck_dest_feedback = self._calculate_naive_stuck_dest_feedback(
            oracle_result=oracle_result
        )
        
        # improve
        for k, v in scenario_feedback.items():
            scenario_feedback[k] = np.array(v)
            
        if 'min_distance' in scenario_feedback and len(scenario_feedback['min_distance']) > 0:
            current_feedback['collision_feedback'] = np.min(scenario_feedback['min_distance'])
            
        if 'dist2center' in scenario_feedback and len(scenario_feedback['dist2center']) > 0:
            current_feedback['dist2center'] = np.mean(scenario_feedback['dist2center'])
        
        current_feedback['stuck_feedback'] = navie_stuck_dest_feedback["stuck_feedback"]
        current_feedback['destination_feedback'] = navie_stuck_dest_feedback["destination_feedback"]
        
        single_score = self.get_single_feedback(current_feedback)
        current_feedback['single_score'] = single_score
        
        mutliple_scores = self.get_multiple_feedback(current_feedback)
        current_feedback['mutliple_scores'] = mutliple_scores
        
        return current_feedback