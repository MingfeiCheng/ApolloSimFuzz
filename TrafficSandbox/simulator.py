import time
import copy
import threading

from typing import Optional, Tuple, Dict
from loguru import logger

from registry import ACTOR_REGISTRY
from common.timer import Timer
from common.data_structure import Location
from common.rpc_utils import sandbox_api

from actor.control import VehicleControl, WalkerControl

class Simulator:
    """Main simulation loop for controlling all actors and signals."""

    def __init__(self, fps: float = 100.0):
        
        Timer.fps = fps
        self.actors: Dict[str, object] = {}
        self.signals: Dict[str, object] = {}
        self.lock = threading.Lock()

        self.scenario_running = False
        self.actor_ready = False

        # lifecycle controls
        self._tick_thread = None
        self._stop_event = threading.Event()
        self._started = False

    # ---------------------- Lifecycle ----------------------
    def start(self, blocking: bool = True):
        """Start the simulation loop."""
        if self._started:
            logger.warning("Simulator already running.")
            return

        logger.info(f"Simulator starting at {Timer.fps} FPS...")
        self._stop_event.clear()
        self._started = True

        if blocking:
            self._loop()
        else:
            self._tick_thread = threading.Thread(target=self._loop, daemon=True)
            self._tick_thread.start()

    def _loop(self):
        """Main loop that maintains tick frequency."""
        last_time = time.perf_counter()
        try:
            while not self._stop_event.is_set():
                start_time = time.perf_counter()
                try:
                    self.tick()
                except Exception as e:
                    logger.exception(f"Tick error: {e}")

                elapsed = time.perf_counter() - start_time
                sleep_time = max(0.0, (1.0 / Timer.fps) - elapsed)
                time.sleep(sleep_time)
        except Exception as e:
            logger.exception(f"Simulator loop error: {e}")
        finally:
            logger.info("Simulator loop exited.")

    def shutdown(self):
        """Gracefully stop the simulator loop without deadlock."""
        if not self._started:
            logger.info("Simulator not running.")
            return

        logger.info("Shutting down simulator...")
        self._stop_event.set()

        if self._tick_thread and self._tick_thread.is_alive():
            self._tick_thread.join(timeout=2.0)
            if self._tick_thread.is_alive():
                logger.warning("Tick thread did not exit cleanly (timeout). Forcing stop.")
        else:
            logger.debug("No active tick thread found.")

        if self.lock.locked():
            logger.warning("Simulator lock still held by tick thread — skipping reset to avoid deadlock.")
        else:
            self.reset()

        self._started = False
        
        if self._tick_thread and self._tick_thread.is_alive():
            logger.warning("Tick thread still alive after shutdown request — forcibly resetting state.")
            self._tick_thread = None
            
        logger.info("Simulator stopped successfully.")

    # ---------------------- Scenario control ----------------------
    @sandbox_api("reset")
    def reset(self):
        with self.lock:
            self.actors.clear()
            self.signals.clear()
            self.scenario_running = False
            self.actor_ready = False
            Timer.reset()

    @sandbox_api("start_scenario")
    def start_scenario(self):
        self.scenario_running = True
        logger.info("Scenario started.")

    @sandbox_api("stop_scenario")
    def stop_scenario(self):
        self.scenario_running = False
        logger.info("Scenario stopped.")

    # ---------------------- Main tick ----------------------
    def tick(self):
        """Advance simulation by one frame."""
        try:
            if not self.actor_ready:
                self.actor_ready = self.check_actor_ready()

            if self.scenario_running and self.actor_ready:
                delta_time = 1.0 / Timer.fps
                with self.lock:
                    for actor in self.actors.values():
                        actor.tick(delta_time)
                    for signal in self.signals.values():
                        signal.tick(delta_time)
            Timer.tick()
        except Exception as e:
            logger.exception(f"Tick error: {e}")

    # ---------------------- Utilities ----------------------
    def check_actor_ready(self) -> bool:
        if not self.actors:
            return False
        return all(actor.status == "ready" for actor in self.actors.values())

    @sandbox_api(name="get_time")
    def get_time(self) -> dict:
        with self.lock:
            return Timer.json_data()

    @sandbox_api(name="get_snapshot")
    def get_snapshot(self) -> dict:
        with self.lock:  # Thread-safe update
            world_snapshot = {
                'time': Timer.json_data(),
                'scenario_running': self.scenario_running and self.actor_ready,
                'actors': {k: copy.deepcopy(v.json_data()) for k, v in self.actors.items()},
                'signals': {k: copy.deepcopy(v.json_data()) for k, v in self.signals.items()},
            }
            return world_snapshot
    
    @sandbox_api(name="get_actor")
    def get_actor(
        self,
        actor_id: str
    ) -> Optional[dict]:
        with self.lock:
            if actor_id not in self.actors.keys():
                return None
            actor_instance = self.actors[actor_id]
            return copy.deepcopy(actor_instance.json_data())

    @sandbox_api(name="get_signal")
    def get_signal(self, signal_id) -> Optional[dict]:
        with self.lock:
            if signal_id not in self.signals.keys():
                return None
            signal_instance = self.signals[signal_id]
            return copy.deepcopy(signal_instance.json_data())

    @sandbox_api(name="get_actor_blueprint")
    def get_actor_blueprint(self, actor_type) -> Optional[dict]:
        with self.lock:
            actor_class = ACTOR_REGISTRY.get(actor_type)
            if actor_class is None:
                return None
            
            return actor_class.blueprint()
    
    @sandbox_api(name="get_scenario_status")
    def get_scenario_status(self) -> str:
        scenario_status = self.scenario_running and self.actor_ready
        with self.lock:
            if scenario_status:
                return 'running'
            else:
                return 'waiting'

    ############
    # creates
    ############
    @sandbox_api(name="create_actor")
    def create_actor(
        self,
        config: dict
    ) -> Tuple[bool, str]:
        """
        actor_id: str,
        actor_type: str,
        x: float,
        y: float,
        z: float,
        heading: float,
        :param config:
        :return:
        """
        with self.lock:
            actor_id = config['actor_id']
            actor_category = config['actor_type']
            x = config['x']
            y = config['y']
            z = config['z']
            heading = config['heading']

            actor_class = ACTOR_REGISTRY.get(actor_category)
            if actor_class is None:
                return False, f"Actor category: {actor_category} not exists."
            

            if actor_id in self.actors.keys():
                return False, "Vehicle already exists."

            try:
                actor_location = Location(x=x, y=y, z=z, pitch=0.0, yaw=heading, roll=0.0)
                actor_instance = actor_class(actor_id, actor_location)
                self.actors[actor_id] = actor_instance
            except Exception as e:
                return False, f"Invalid vehicle {actor_id} config: {str(e)}"
            
            return True, f"Vehicle {actor_id} registered."

    @sandbox_api(name="create_signal")
    def create_signal(
        self,
        config: dict
    ) -> Tuple[bool, str]:
        with self.lock:
            signal_id = config['signal_id']
            signal_type = config['signal_type']
            signal_state = config['signal_state']

            actor_class = ACTOR_REGISTRY.get(signal_type)
            if actor_class is None:
                return False, f"Signal category: {signal_type} not exists."

            if signal_id in self.signals.keys():
                return False, f"Signal {signal_id} already exists."

            try:
                signal_instance = actor_class(signal_id, signal_state)
                self.signals[signal_id] = signal_instance
            except Exception as e:
                return False, f"Invalid signal {signal_id} config: {str(e)}" 
            
            return True, f"Signal {signal_id} registered."

    ############
    # removes
    ############
    @sandbox_api(name="remove_actor")
    def remove_actor(
        self,
        actor_id: str
    ) -> Tuple[bool, str]:
        with self.lock:
            if actor_id not in self.actors.keys():
                return False, f"Actor {actor_id} not exists."

            del self.actors[actor_id]
            return True, f"Actor {actor_id} removed."

    @sandbox_api(name="remove_signal")
    def remove_signal(
        self,
        signal_id: str
    ) -> Tuple[bool, str]:
        with self.lock:
            if signal_id not in self.signals.keys():
                return False, f"Signal {signal_id} not exists."

            del self.signals[signal_id]
            return True, f"Signal {signal_id} removed." 

    ############
    # sets
    ############
    @sandbox_api(name="set_actor_status")
    def set_actor_status(
        self,
        actor_id: str,
        status: str
    ) -> Tuple[bool, str]:
        with self.lock:
            if actor_id not in self.actors.keys():
                return False, f"Actor {actor_id} not exists."

            self.actors[actor_id].set_status(status)
            return True, f"Actor {actor_id} status set."

    @sandbox_api(name="set_static_location")
    def set_static_location(
        self,
        actor_id: str,
        location: dict
    ) -> Tuple[bool, str]:
        with self.lock:
            if actor_id not in self.actors.keys():
                return False, f"Actor {actor_id} not exists."

            try:
                actor_location = Location(
                    x=location['x'],
                    y=location['y'],
                    z=location['z'],
                    pitch=location['pitch'],
                    yaw=location['yaw'],
                    roll=location['roll'],
                )
                self.actors[actor_id].update_location(actor_location)
            except Exception as e:
                return False, f"Invalid location: {str(e)}"

            return True, f"Actor {actor_id} location set."

    @sandbox_api(name="set_signal_state")
    def set_signal_state(
        self,
        actor_id: str,
        state: str
    ) -> Tuple[bool, str]:
        with self.lock:
            if actor_id not in self.signals.keys():
                return False, f"Signal {actor_id} not exists."

            self.signals[actor_id].update_state(state)
            return True, f"Signal {actor_id} state set."

    ############
    # apply controls
    ############
    @sandbox_api(name="apply_vehicle_control")
    def apply_vehicle_control(
        self,
        actor_id: str,
        control: dict
    ) -> Tuple[bool, str]:
        with self.lock:

            if actor_id not in self.actors.keys():
                return False, f"Actor {actor_id} not exists."

            actor_instance = self.actors[actor_id]
            try:
                control_command = VehicleControl(
                    throttle=float(control['throttle']),
                    steer=float(control['steer']),
                    brake=float(control['brake']),
                    reverse=control['reverse'] if 'reverse' in control.keys() else False,
                )
                actor_instance.apply_control(control_command)
            except Exception as e:
                return False, f"Invalid control command: {str(e)}"

            return True, f"Control applied to vehicle {actor_id}."

    @sandbox_api(name="apply_walker_action")
    def apply_walker_action(
        self,
        actor_id: str,
        control: dict
    ) -> Tuple[bool, str]:
        with self.lock:
            if actor_id not in self.actors.keys():
                return False, f"Actor {actor_id} not exists."

            actor_instance = self.actors[actor_id]
            try:
                control_command = WalkerControl(
                    acceleration=float(control['acceleration']),
                    heading=float(control['heading']),
                )
                actor_instance.apply_control(control_command)
            except Exception as e:
                return False, f"Invalid control command: {str(e)}"

            return True, f"Control applied to walker {actor_id}."