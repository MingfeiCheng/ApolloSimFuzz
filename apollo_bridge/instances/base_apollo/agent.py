import os
import time
import copy
import shutil
import traceback
import numpy as np

from loguru import logger
from threading import Thread
from typing import Optional, Dict, Any

from apollo_bridge.common.format import (
    Vector, Waypoint, Lane, Location, Obstacle, TrafficLightState,
    RouteMessage, ChassisMessage, PerfectObstacleMessage,
    PerfectTrafficLightMessage, LocalizationMessage, ControlPadMessage
)
from apollo_bridge.common.messenger import ApolloMessenger
from scenario_elements.agents.base import AgentBase
from tools.logger_tools import get_instance_logger

from .config import ApolloConfig

class ApolloAgent(AgentBase):
    
    prefix = 'apollo'
    container_record_folder = '/apollo/drivora/records'
    sleep_interval = 0.001
    
    def __init__(
        self,
        id: str,
        sim_ctn_name: str,
        actor_config: Dict[str, Any],
        other_config: Dict[str, Any] = {},
        start_event = None,
        stop_event = None
    ):
        super(ApolloAgent, self).__init__(
            id=id,
            sim_ctn_name=sim_ctn_name,
            actor_config=actor_config,
            other_config=other_config,
            start_event=start_event,
            stop_event=stop_event
        )
        
    def _initialize(self):

        # --- Configuration ---
        # other configs
        self.scenario_idx = self.other_config['scenario_id']
        self.output_folder = self.other_config.get('save_root', None) # in container path
        self.apollo_ctn_name = self.other_config.get('apollo_container_name', None)
        if self.apollo_ctn_name is None:
            raise ValueError("Apollo container name must be provided in other_config with key 'apollo_container_name'")
        self.gpu = self.other_config.get('gpu', 0)
        self.cpu = self.other_config.get('cpu', 24.0)
        self.apollo_root = self.other_config.get('apollo_root', '/apollo')
        self.map_name = self.other_config.get('map_name', 'san_francisco')
        self.dreamview_port = self.other_config.get('dreamview_port', 8888)
        self.bridge_port = self.other_config.get('bridge_port', 9090)
        self.map_dreamview = self.other_config.get('map_dreamview', False)
        self.debug = self.other_config.get('debug', False)
        
        logger.debug(f"[{self.id}] Apollo Agent Configs: apollo_ctn_name={self.apollo_ctn_name}, gpu={self.gpu}, cpu={self.cpu}, apollo_root={self.apollo_root}, map_name={self.map_name}, dreamview_port={self.dreamview_port}, bridge_port={self.bridge_port}, map_dreamview={self.map_dreamview}, debug={self.debug}, saving_root={self.output_folder}")
        
        # actor config
        self.actor_config_py: ApolloConfig = ApolloConfig.model_validate(self.actor_config)
        self.route = [wp.model_dump() for wp in self.actor_config_py.route] # convert to dict
        # self.route = self.actor_config_py.route
        self.trigger_time = self.actor_config_py.trigger_time
        
        # other settings
        if self.output_folder is not None:
            self.debug_folder = os.path.join(self.output_folder, f"debug/{self.prefix}")
            self.logger = self._init_logger()

        self.messenger = ApolloMessenger(
            idx=f"{self.prefix}_{self.id}",
            apollo_modules=self._modules(),
            publishers=self._publishers(),
            subscribers=self._subscribers(),
            container_name=self.apollo_ctn_name,
            gpu=self.gpu,
            cpu=self.cpu,
            apollo_root=self.apollo_root,
            map_name=self.map_name,
            dreamview_port=self.dreamview_port,
            bridge_port=self.bridge_port,
            map_dreamview=self.map_dreamview
        )

        # --- Internal State ---
        self.route_send = False
        self.route_response = False
        self.route_send_time = 0.0
        self.running = False
        self.ready = False
        self.threads: list[Thread] = []

        self.actor_info = None
        self.last_snapshot_time = 0.0
        self.last_ego_update_time = 0.0
        self.last_env_update_time = 0.0
        self.last_sequence_num = 0
        self.last_planning_update_time = time.time()

    def _init_logger(self):
        if self.debug:
            os.makedirs(self.debug_folder, exist_ok=True)
            logger_file = os.path.join(self.debug_folder, f"{self.id}.log")
            return get_instance_logger(f"{self.prefix}_{self.id}", logger_file)
        return None

    def _publishers(self):
        return [
            'publisher.chassis',
            'publisher.perfect_localization',
            'publisher.perfect_obstacle',
            'publisher.perfect_traffic_light',
            'publisher.routing_request',
            'publisher.control_pad',
        ]

    def _subscribers(self):
        return ['subscriber.control']

    def _modules(self):
        return ['Routing', 'Prediction', 'Planning', 'Control']

    def _request_snapshot(self) -> Optional[dict]:
        snapshot = self.sandbox_operator.sim.get_snapshot()
        if snapshot is None:
            return None

        time_stamp = snapshot['time']['game_time']
        if time_stamp <= self.last_snapshot_time:
            return None
        
        self.last_snapshot_time = time_stamp
        actors = snapshot['actors']
        ego_info = actors[self.id]
        self.actor_info = copy.deepcopy(ego_info)

        return {
            'time': time_stamp,
            'route': self._build_route_message(time_stamp),
            'chassis': self._build_chassis_message(ego_info, time_stamp),
            'localization': self._build_localization_message(ego_info, time_stamp),
            'perfect_obstacle': self._build_obstacle_message(actors, time_stamp),
            'perfect_traffic_light': self._build_traffic_light_message(snapshot['signals'], time_stamp),
            'speed': ego_info['speed']
        }

    def _build_route_message(self, time_stamp):
        waypoints = [
            Waypoint(
                location=Location(
                    x=wp['location']['x'],
                    y=wp['location']['y'],
                    z=wp['location']['z'],
                    pitch=wp['rotation']['pitch'],
                    roll=wp['rotation']['roll'],
                    yaw=wp['rotation']['yaw']
                ), 
                lane=Lane(
                    id=wp['lane']['id'],
                    s=wp['lane']['s'],
                    l=wp['lane']['l']
                )
            )
            for wp in self.route
        ]
        return RouteMessage(time_stamp, waypoints)

    def _build_chassis_message(self, info, time_stamp):
        ctrl = info['control']
        return ChassisMessage(
            time_stamp,
            speed_mps=info['speed'],
            throttle_percentage=ctrl['throttle'] * 100,
            brake_percentage=ctrl['brake'] * 100,
            steering_percentage=ctrl['steer'] * 100,
            reverse=ctrl['reverse']
        )

    def _build_localization_message(self, info, time_stamp):
        loc = info['location']
        acc = info['acceleration']
        speed = info['speed']
        heading = loc['yaw']
        return LocalizationMessage(
            timestamp=time_stamp,
            location=Location(**loc),
            heading=heading,
            velocity=Vector(x=speed * np.cos(heading), y=speed * np.sin(heading), z=0),
            acceleration=Vector(x=acc * np.cos(heading), y=acc * np.sin(heading), z=0),
            angular_velocity=Vector(x=0, y=0, z=info['angular_speed'])
        )

    def _build_obstacle_message(self, actors, time_stamp):
        obs = []
        for k, v in actors.items():
            if k == self.id:
                continue
            category = v['category']
            sub_category = v.get('sub_category', '')
            obs_category = sub_category if category == 'vehicle' and sub_category == 'bicycle' else category
            obs.append(Obstacle(
                id=int(k),
                category=obs_category,
                length=v['bbox']['length'],
                width=v['bbox']['width'],
                height=v['bbox']['height'],
                location=Location(**v['location']),
                velocity=Vector(
                    x=np.cos(v['location']['yaw']) * v['speed'],
                    y=np.sin(v['location']['yaw']) * v['speed'],
                    z=0.0
                ),
                bbox_points=v['polygon']
            ))
        return PerfectObstacleMessage(time_stamp, obs)

    def _build_traffic_light_message(self, signals, time_stamp):
        lights = [
            TrafficLightState(id=k, state=v['state'])
            for k, v in signals.items() if k != self.id
        ]
        return PerfectTrafficLightMessage(time_stamp, lights)

    def _publish_pad_message(self, timestamp: float, action: int = 0):
        msg = ControlPadMessage(timestamp=timestamp, action=action)
        self.messenger.publish_message('publisher.control_pad', msg)

    def _publish_sensor(self):
        """
        Periodically publish ego & environment sensor messages.
        Includes routing warm-up and ready-state transition.
        """
        self._publish_pad_message(0.0, action=0)

        while self.running:
            try:
                snapshot = self._request_snapshot()
                if snapshot is None:
                    time.sleep(self.sleep_interval)
                    continue

                now = snapshot["time"]
                ego_speed = snapshot["speed"]
                now_wall = time.time()

                # --------------------------------
                # 1. PAD / action message
                # --------------------------------
                if now < self.trigger_time:
                    self._publish_pad_message(now, action=0)
                elif now < self.trigger_time + 0.5:
                    self._publish_pad_message(now, action=2)

                # --------------------------------
                # 2. Ego (chassis + localization)
                # --------------------------------
                self.last_ego_update_time = now

                self.messenger.publish_message(
                    "publisher.chassis", snapshot["chassis"]
                )
                self.messenger.publish_message(
                    "publisher.perfect_localization",
                    snapshot["localization"],
                )

                # -------- routing / ready FSM --------
                if not self.ready:

                    # send routing once
                    if not self.route_send:
                        self.route_send_time = now_wall
                        self._publish_pad_message(now, action=0)
                        self.messenger.publish_message(
                            "publisher.routing_request",
                            snapshot["route"],
                        )
                        self.route_send = True
                        self._publish_pad_message(now, action=2)

                    # wait for routing response (ego moves)
                    elif not self.route_response:
                        if now_wall - self.route_send_time < 5.0:
                            if ego_speed > 0.05:
                                self.route_response = True

                    # resend routing & reset control to stabilize
                    else:
                        if now_wall - self.route_send_time > 5.0:
                            self._publish_pad_message(now, action=0)
                            self.route_send_time = now_wall
                            self.messenger.publish_message(
                                "publisher.routing_request",
                                snapshot["route"],
                            )
                            self._publish_pad_message(now, action=2)

                        self.ready = True
                        self.sandbox_operator.sim.set_actor_status(
                            self.id, "ready"
                        )

                # --------------------------------
                # 3. Environment perception
                # --------------------------------
                self.last_env_update_time = now

                self.messenger.publish_message(
                    "publisher.perfect_obstacle",
                    snapshot["perfect_obstacle"],
                )
                self.messenger.publish_message(
                    "publisher.perfect_traffic_light",
                    snapshot["perfect_traffic_light"],
                )

            except Exception:
                if self.logger:
                    self.logger.exception(f"[{self.id}] Error in _publish_sensor")
                else:
                    logger.exception(f"[{self.id}] Error in _publish_sensor")

            time.sleep(self.sleep_interval)


    def _receive_control(self):
        while self.running:
            throttle, brake, steer, reverse = self.messenger.subscriber_pool['subscriber.control'].get_data()
            self.sandbox_operator.sim.apply_vehicle_control(self.id, {
                'throttle': throttle, 'brake': brake, 'steer': steer, 'reverse': reverse
            })
            # time.sleep(1 / self.control_frequency)
            time.sleep(self.sleep_interval)

    def run(self):
        while not self.start_event.is_set():
            time.sleep(0.01)
            if self.stop_event.is_set():
                self.sandbox_operator.close()
                return

        self.start_record()
        self.running = True
        self.route_response = False

        self.threads = [
            Thread(target=func, daemon=True) for func in [self._receive_control, self._publish_sensor]
        ]
        for t in self.threads:
            t.start()

        # keep running until stop signal
        while not self.stop_event.is_set():
            time.sleep(0.01)

        self.stop()
        
    def _tick(self, snapshot):
        return super()._tick(snapshot)

    def stop(self):
        # stop all
        self.running = False
        for thread in self.threads:
            if thread:
                thread.join()
        self.stop_record()
        self.messenger.shutdown()
        self.sandbox_operator.close()

    def start_record(self):
        self.recorder_operator('start', self.container_record_folder, f"{self.scenario_idx}_{self.id}")

    def stop_record(self):
        self.recorder_operator('stop')
        
        if self.output_folder is None:
            # skip saving as no output folder is provided
            return
        
        local_dir = os.path.join(self.output_folder, f"records_apollo/{self.id}")
        os.makedirs(local_dir, exist_ok=True)
        self.move_recording(local_dir, self.container_record_folder, f"{self.scenario_idx}_{self.id}", delete_flag=True)

    def recorder_operator(self, operation, record_folder=None, scenario_id=None):
        self.messenger.recorder_operator(operation, record_folder, scenario_id)

    def move_recording(self, local_path: str, apollo_path: str, scenario_id: str, delete_flag: bool = True):
        if os.path.exists(local_path):
            shutil.rmtree(local_path)
        self.messenger.move_recording(apollo_path, scenario_id, local_path, delete_flag)
        if self.logger:
            self.logger.info(f"[ApolloAgent] Move Apollo Recording for {self.id} to {local_path}")
