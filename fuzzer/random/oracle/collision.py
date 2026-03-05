# We need to filter out NPC induced collisions for any ADSs
import numpy as np
import math

from loguru import logger

from shapely.geometry import Polygon

def filter_collision(ego_obs: dict, npc_actor: dict, speed_threshold_ego=0.01, speed_threshold_npc=1.0, collision_degree=90, sensor_detected_collision=False):
    """
    Return: list of (ego_id, npc_id, is_npc_caused)
    """
    if 'polygon' not in npc_actor:
        return None
    
    ego_id = ego_obs['id']
    ego_loc = np.array([ego_obs['location']['x'], ego_obs['location']['y']])
    ego_yaw = ego_obs['location']['yaw'] # radius
    
    npc_loc = np.array([npc_actor['location']['x'], npc_actor['location']['y']])
    npc_yaw = npc_actor['location']['yaw']
    
    ego_bbox_polygon = Polygon(
        ego_obs['polygon']
    )
    
    npc_bbox_polygon = Polygon(
        npc_actor['polygon']
    )
    
    if sensor_detected_collision:
        contains_collisions = True
    else:
        contains_collisions = ego_bbox_polygon.intersects(npc_bbox_polygon)
    
    if not contains_collisions:
        return None  # No collision
    
    # -----------------------------
    # 🚗 Step 1: 判断碰撞点在Ego前后方
    # -----------------------------
    # Ego 朝向向量
    ego_yaw_rad = ego_yaw
    f_e = np.array([math.cos(ego_yaw_rad), math.sin(ego_yaw_rad)])

    # 从 Ego 指向 NPC
    r = npc_loc - ego_loc
    dist = np.linalg.norm(r)
    
    dot_fe_r = np.dot(f_e, r / dist)
    angle = math.degrees(math.acos(np.clip(dot_fe_r, -1, 1)))
    npc_is_behind_ego = angle > collision_degree

    # -----------------------------
    # 🏎️ Step 2: 根据速度判断
    # -----------------------------
    ego_speed = ego_obs['speed']
    npc_speed = npc_actor.get('speed', 0.0)
    
    # -----------------------------
    # 🧠 Step 3: 判定规则
    # -----------------------------
    #  if NPC is not vehicle, we directly return the collision info
    is_npc_caused = False
    
    if npc_actor['category'] != 'vehicle':
        res = {
            "ego_id": ego_id,
            "npc_id": npc_actor.get("id", None),
            "npc_category": npc_actor.get("category", "unknown"),
            "npc_sub_category": npc_actor.get("sub_category", "unknown"),
            "angle": angle,
            "npc_is_behind_ego": npc_is_behind_ego,
            "ego_speed": ego_speed,
            "npc_speed": npc_speed,
            "is_npc_caused": is_npc_caused,
        }
        
        return res
    
    if ego_speed < speed_threshold_ego and (npc_speed > speed_threshold_npc or npc_speed > ego_speed + 1e-3):
        is_npc_caused = True  # Ego 几乎静止，NPC 碰撞
    # 判定条件
    elif npc_is_behind_ego:
        is_npc_caused = True

    # logger.debug(f"Collision Filter: ego_speed={ego_speed:.2f}, npc_speed={npc_speed:.2f}, angle={angle:.2f}, npc_is_behind_ego={npc_is_behind_ego}, is_npc_caused={is_npc_caused}")
    if is_npc_caused:
        return None  # NPC caused collision

    res = {
        "ego_id": ego_id,
        "npc_id": npc_actor.get("id", None),
        "npc_actor_id": npc_actor.get("actor_id", None),
        "npc_category": npc_actor.get("category", "unknown"),
        "npc_sub_category": npc_actor.get("sub_category", "unknown"),
        "angle": angle,
        "npc_is_behind_ego": npc_is_behind_ego,
        "ego_speed": ego_speed,
        "npc_speed": npc_speed,
        "is_npc_caused": is_npc_caused,
    }
    
    return res
    

