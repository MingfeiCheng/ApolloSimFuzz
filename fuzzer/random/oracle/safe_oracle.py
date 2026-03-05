import copy

from typing import List
from loguru import logger

from .collision import filter_collision

# Should skip begging frames..

class SafeOracle:
    
    def __init__(self, config):
        
        self.config = config
        
        self.skip_start_frame = self.config.get("skip_start_frame", 0) # skip first 20 frames as initialization
        self.collision_speed_threshold_ego = self.config.get("collision_speed_threshold_ego", 0.01)
        self.collision_speed_threshold_npc = self.config.get("collision_speed_threshold_npc", 1.0)
        self.collision_degree = self.config.get("collision_degree", 90.0)
        
    def evaluate(self, scenario_observation: List[dict], runtime_results: dict):

        oracle_result = {
            "ignored": False, # we ignore some scenarios due to no need checking or some errors
            "expected": False,
            # "unsafe": False,
            'violation_labels': [], # NOTE: we need multiple-label -> if it is empty -> safe
            "runtime_results": copy.deepcopy(runtime_results),
            "offline_results": {} 
        }
        
        scenario_length = len(scenario_observation)            
        if scenario_length <= self.skip_start_frame:
            # no need checker
            oracle_result['ignored'] = True
            oracle_result['expected'] = False
            return oracle_result
        
        # check collisions
        if runtime_results['runtime_criteria']['collision']['occurred']:
            oracle_details = runtime_results['runtime_criteria']['collision']['details']
            collision_res = filter_collision(
                ego_obs=oracle_details['actor'],
                npc_actor=oracle_details['other_actor'],
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
        
        # check stuck
        # expected_keys = ['stuck', 'reach_destination']
        expected_keys = ['stuck']
        for key in expected_keys:
            if runtime_results['runtime_criteria'][key]['occurred']:
                oracle_result['violation_labels'].append(key)
                        
        return oracle_result