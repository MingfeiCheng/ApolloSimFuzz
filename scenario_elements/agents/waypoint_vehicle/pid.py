import math
from collections import deque
from typing import Dict

import numpy as np
from shapely.geometry import Point


class PIDController:
    def __init__(self, long_cfg: Dict, lat_cfg: Dict):
        self.longitudinal_control = PIDLongitudinalController(**long_cfg)
        self.lateral_control = PIDLateralController(**lat_cfg)

    def run_step(
        self,
        curr_location: dict,
        curr_speed: float,
        curr_heading: float,
        target_location: dict,
        target_speed: float,
        dt: float
    ):
        curr_point = Point(curr_location['x'], curr_location['y'])
        next_point = Point(target_location['x'], target_location['y'])

        # Compute target heading
        target_heading = math.atan2(
            next_point.y - curr_point.y,
            next_point.x - curr_point.x
        )

        heading_error = (target_heading - curr_heading + math.pi) % (2 * math.pi) - math.pi
        if curr_speed < 0.01:
            heading_error = 0.0

        steer = self.lateral_control.run_step(heading_error, dt)
        steer = np.clip(steer, -1.0, 1.0)

        speed_error = target_speed - curr_speed
        throttle_brake = self.longitudinal_control.run_step(speed_error, dt)
        throttle_brake = np.clip(throttle_brake, -1.0, 1.0)

        if throttle_brake > 0.0:
            throttle, brake = throttle_brake, 0.0
        else:
            throttle, brake = 0.0, -throttle_brake

        return throttle, brake, steer


class PIDLongitudinalController:
    def __init__(self, K_P=1.0, K_I=0.0, K_D=0.0):
        self._k_p = K_P
        self._k_i = K_I
        self._k_d = K_D
        self._error_buffer = deque(maxlen=10)

    def run_step(self, error: float, dt: float) -> float:
        self._error_buffer.append(error)

        if len(self._error_buffer) >= 2:
            _de = (self._error_buffer[-1] - self._error_buffer[-2]) / dt
            _ie = sum(self._error_buffer) * dt
        else:
            _de = 0.0
            _ie = 0.0

        return np.clip(
            (self._k_p * error) + (self._k_d * _de) + (self._k_i * _ie),
            -1.0, 1.0
        )


class PIDLateralController:
    def __init__(self, K_P=1.0, K_I=0.0, K_D=0.0):
        self._k_p = K_P
        self._k_i = K_I
        self._k_d = K_D
        self._error_buffer = deque(maxlen=10)

    def run_step(self, error: float, dt: float) -> float:
        error = float(np.clip(error, -1.0, 1.0))
        self._error_buffer.append(error)

        if len(self._error_buffer) >= 2:
            _de = (self._error_buffer[-1] - self._error_buffer[-2]) / dt
            _ie = sum(self._error_buffer) * dt
        else:
            _de = 0.0
            _ie = 0.0

        return np.clip(
            (self._k_p * error) + (self._k_d * _de) + (self._k_i * _ie),
            -1.0, 1.0
        )
