from typing import List
from tqdm import tqdm
from loguru import logger

from .collision import filter_collision

# Should skip begging frames..

class ScenarioOracle:
    
    def __init__(self, config):
        
        self.config = config
        
        self.collision_speed_threshold_ego = self.config.get("collision_speed_threshold_ego", 0.01)
        self.collision_speed_threshold_npc = self.config.get("collision_speed_threshold_npc", 1.0)
        self.collision_degree = self.config.get("collision_degree", 90.0)
        
        self.skip_start_frame = self.config.get("skip_start_frame", 0) # skip first 20 frames as initialization

    def evaluate(self, scenario_observation: List[dict], runtime_results: dict):

        oracle_result = {
            "ignored": False, # we ignore some scenarios due to no need checking or some errors
            "expected": False,
            # "unsafe": False,
            'violation_labels': [], # NOTE: we need multiple-label -> if it is empty -> safe
            "runtime_results": runtime_results,
            "offline_results": {} 
        }
        
        expected_keys = [
            "stuck",
        ]
        
        # obtain collision info
        for criteria_name, criteria_result in runtime_results.items():

            # ===== group ads =====
            if "group_criteria" in criteria_name:
                for actor_id, actor_result in criteria_result.items():

                    if actor_result['collision']['occurred']:
                        collision_res = filter_collision(
                            ego_obs=actor_result["collision"]['details']['actor'],
                            npc_actor=actor_result["collision"]['details']['other_actor'],
                            speed_threshold_ego=self.collision_speed_threshold_ego,
                            speed_threshold_npc=self.collision_speed_threshold_npc,
                            collision_degree=self.collision_degree,
                            sensor_detected_collision=True
                        )
                        if collision_res is not None:
                            # None means NPC caused
                            # collision happened
                            oracle_result["expected"] = True
                            oracle_result['violation_labels'].append('collision')
                            # oracle_result['unsafe'] = True # it is also unsafe if any actor collides
                            if "collision" not in oracle_result["offline_results"]:
                                oracle_result["offline_results"]["collision"] = []
                            oracle_result["offline_results"]["collision"].append(collision_res)

                    # combine repeated checks
                    for key in expected_keys:
                        if actor_result[key]['occurred']:
                            oracle_result['expected'] = True
                            oracle_result['violation_labels'].append(key)

            # ===== single ads =====
            else:
                actor_result = criteria_result

                if actor_result['collision']['occurred']:
                    collision_res = filter_collision(
                        ego_obs=actor_result["collision"]['details']['actor'],
                        npc_actor=actor_result["collision"]['details']['other_actor'],
                        speed_threshold_ego=self.collision_speed_threshold_ego,
                        speed_threshold_npc=self.collision_speed_threshold_npc,
                        collision_degree=self.collision_degree,
                        sensor_detected_collision=True
                    )
                    if collision_res is not None:
                        # None means NPC caused
                        # collision happened
                        oracle_result["expected"] = True
                        oracle_result['violation_labels'].append('collision')
                        # oracle_result['unsafe'] = True # it is also unsafe if any actor collides
                        if "collision" not in oracle_result["offline_results"]:
                            oracle_result["offline_results"]["collision"] = []
                        oracle_result["offline_results"]["collision"].append(collision_res)

                for key in expected_keys:
                    if actor_result[key]['occurred']:
                        oracle_result['expected'] = True
                        oracle_result['violation_labels'].append(key)
                        
        scenario_length = len(scenario_observation)            
        if scenario_length <= self.skip_start_frame:
            # no need checker
            oracle_result['ignored'] = True
            oracle_result['expected'] = False
            return oracle_result
        
        return oracle_result            