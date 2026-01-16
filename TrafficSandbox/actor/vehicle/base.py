import copy
import math
import numpy as np

from loguru import logger
from typing import List, Tuple

from common.data_structure import Location, BoundingBox

from actor.base import Actor
from actor.misc import right_rotation, normalize_angle
from actor.control import VehicleControl, VehiclePerfectControl

class VehicleActor(Actor):

    _bbox: BoundingBox = BoundingBox(
        length=0.0,
        width=0.0,
        height=0.0
    )
    _location: Location = Location(
        x=0.0,
        y=0.0,
        z=0.0,
        pitch=0.0,
        yaw=0.0,
        roll=0.0,
    )
    _speed: float = 0.0
    _angular_speed: float = 0.0
    _acceleration: float = 0.0
    _control: VehicleControl = VehicleControl(
        throttle=0.0,
        brake=0.0,
        steer=0.0,
    )
    _last_location: Location = Location(
        x=0.0,
        y=0.0,
        z=0.0,
        pitch=0.0,
        yaw=0.0,
        roll=0.0,
    )

    # for vis or others
    _polygon: List = None

    # some other attributes
    _max_acceleration: float = 0.0
    _max_deceleration: float = 0.0
    _front_edge_to_center: float = 0.0
    _back_edge_to_center: float = 0.0
    _left_edge_to_center: float = 0.0
    _right_edge_to_center: float = 0.0
    _max_steer_angle: float = 0.0  # radians * 180 / math.pi
    _max_steer_angle_rate: float = 0.0
    _steer_ratio: float = 0.0
    _wheelbase: float = 0.0
    _max_abs_speed_when_stopped: float = 0.0

    _category: str = 'vehicle'
    _sub_category: str = 'vehicle'

    def __init__(self, id: int, location: Location):
        super(VehicleActor, self).__init__(id)
        self._location = copy.deepcopy(location)
        self._last_location = copy.deepcopy(location)
        self._last_steer = 0.0
        self._max_steer_delta = (self._max_steer_angle_rate * 180.0 / math.pi) * self._steer_ratio * math.pi / (180.0 * self._max_steer_angle)

        self._control = VehicleControl(
            throttle=0.0,
            brake=0.0,
            steer=0.0,
            reverse=False
        )

        self._steer_angle = 0.0

    # json data
    def json_data(self):
        return {
            'id': self.id,
            'category': self._category,
            'sub_category': self._sub_category,
            'location': self.location.json_data(),
            'speed': self.speed,
            'angular_speed': self.angular_speed,
            'acceleration': self.acceleration,
            'bbox': self.bbox.json_data(),
            'control': self.control.json_data(),
            'front_edge_to_center': self.front_edge_to_center,
            'back_edge_to_center': self.back_edge_to_center,
            'left_edge_to_center': self.left_edge_to_center,
            'right_edge_to_center': self.right_edge_to_center,
            'polygon': self.get_polygon_points(),
        }

    @classmethod
    def blueprint(cls):
        return {
            'category': cls._category,
            'sub_category': cls._sub_category,
            'bbox': cls._bbox.json_data(),
            'front_edge_to_center': float(cls._front_edge_to_center),
            'back_edge_to_center': float(cls._back_edge_to_center),
            'left_edge_to_center': float(cls._left_edge_to_center),
            'right_edge_to_center': float(cls._right_edge_to_center),
        }

    ###### public properties ######
    @property
    def location(self) -> Location:
        return self._location

    @property
    def speed(self) -> float:
        return float(self._speed)

    @property
    def angular_speed(self) -> float:
        return float(self._angular_speed)

    @property
    def acceleration(self) -> float:
        return float(self._acceleration)

    @property
    def bbox(self) -> BoundingBox:
        return self._bbox

    @property
    def control(self) -> VehicleControl or VehiclePerfectControl:
        return self._control

    ####### shape property #########
    @property
    def front_edge_to_center(self):
        return self._front_edge_to_center

    @property
    def back_edge_to_center(self):
        return self._back_edge_to_center

    @property
    def left_edge_to_center(self):
        return self._left_edge_to_center

    @property
    def right_edge_to_center(self):
        return self._right_edge_to_center

    def apply_control(self, control: VehicleControl or None):
        # write operation
        self._control = control

    def get_forward_vector(self) -> List:
        heading = -self.location.yaw
        init_vector = [1, 0]
        forward_vector = right_rotation(init_vector, heading)
        return forward_vector

    def get_polygon_points(self) -> Tuple[Tuple[float]]:
        # this gets current polygon
        half_w = self._bbox.width / 2.0

        front_l = self._bbox.length - self._back_edge_to_center
        back_l = -1 * self._back_edge_to_center

        curr_location = self.location
        sin_h = math.sin(curr_location.yaw)
        cos_h = math.cos(curr_location.yaw)
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
            points.append([curr_location.x + x, curr_location.y + y])

        return points

    def _tick(self, delta_time: float):
        """
        This will change most variables, so it should be thread safe
        All in range of [0, 1]
        NOW WE ONLY support linear model for each object
        """
        # with self._thread_lock:
        throttle = self.control.throttle
        brake = self.control.brake
        steer = self.control.steer

        assert 0 <= throttle <= 1
        assert 0 <= brake <= 1
        assert -1 <= steer <= 1

        self._last_steer = steer
        self._last_location = self.location

        # Compute longitudinal acceleration
        self._acceleration = throttle * self._max_acceleration + brake * self._max_deceleration
        self._acceleration = min(max(self._acceleration, self._max_deceleration), self._max_acceleration)

        # update speed
        next_speed = self.speed + self._acceleration * delta_time
        next_speed = max(0.0, next_speed)
        avg_speed = (self.speed + next_speed) / 2.0

        # compute steer
        # https://github.com/ApolloAuto/apollo/blob/c48541b4c6b1b0acf432c7ccde92525c7bdb781d/modules/tools/record_play/rtk_recorder.py#L136
        curr_steer_angle = (steer * (self._max_steer_angle * 180.0 / math.pi) / self._steer_ratio) * math.pi / 180.0 # degree -> radius

        # delta_steer_angle = float(
        #     np.clip(curr_steer_angle - self._steer_angle, - self._max_steer_angle_rate * 1.7 / self._steer_ratio,
        #             self._max_steer_angle_rate * 1.7 / self._steer_ratio))
        # curr_steer_angle = normalize_angle(self._steer_angle + delta_steer_angle)

        # if abs(curr_steer_angle) < 1e-4:
        #     curr_angular_speed = 0.0
        # else:
        curr_angular_speed = avg_speed * math.tan(curr_steer_angle) / self._wheelbase

        # logger.debug(f"Apollosim previous location: {self._location} control: {self.control.json_data()}")
        self._location.yaw = normalize_angle(self._location.yaw + curr_angular_speed * delta_time)
        self._location.x = self._location.x + avg_speed * math.cos(self._location.yaw) * delta_time
        self._location.y = self._location.y + avg_speed * math.sin(self._location.yaw) * delta_time
        # logger.debug(f"Apollosim current location: {self._location}")

        # Store updated state
        self._speed = next_speed
        self._angular_speed = curr_angular_speed
        self._steer_angle = curr_steer_angle

        # logger.debug(f"acceleartion: {self._acceleration}, speed: {self._speed}, angular_speed: {self._angular_speed}, steer: {self._steer_angle}")


class PerfectVehicleActor(VehicleActor):

    def __init__(self, id: int, location: Location):
        super(PerfectVehicleActor, self).__init__(id, location)
        self._control = VehiclePerfectControl(
            acceleration=0.0,
            heading=location.heading
        )

    def _tick(self, delta_time: float):
        acceleration = self.control.acceleration
        target_heading = self.control.heading

        self._last_location = copy.deepcopy(self._location)
        curr_acceleration = float(np.clip(acceleration, -abs(self._max_deceleration), abs(self._max_acceleration)))
        curr_speed = self._speed
        next_speed = curr_speed + curr_acceleration * delta_time
        next_speed = max(0.0, next_speed)
        avg_speed = (curr_speed + next_speed) / 2.0

        # Normalize heading
        delta_heading = normalize_angle(target_heading - self._location.yaw) # limit a max value
        if abs(delta_heading) < 1e-4:
            curr_angular_speed = 0.0
        else:
            # Compute angular speed from change in heading
            curr_angular_speed = delta_heading / delta_time

        # Update position
        self._location.yaw = normalize_angle(self._location.yaw + curr_angular_speed * delta_time)
        self._location.x = self._location.x + avg_speed * math.cos(self._location.yaw) * delta_time
        self._location.y = self._location.y + avg_speed * math.sin(self._location.yaw) * delta_time


        # Store updated state
        self._speed = next_speed
        self._angular_speed = curr_angular_speed
