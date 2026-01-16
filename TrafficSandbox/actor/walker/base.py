import copy
import math
import numpy as np

from typing import List, Tuple

from common.data_structure import Location, BoundingBox

from actor.base import Actor
from actor.control import WalkerControl
from actor.misc import right_rotation, normalize_angle

class WalkerActor(Actor):

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
    _control: WalkerControl = WalkerControl(
        acceleration=0.0,
        heading=0.0
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

    _category: str = 'walker'
    _sub_category: str = 'walker'

    def __init__(self, id: int, location: Location):
        super(WalkerActor, self).__init__(id)
        self._location = copy.deepcopy(location)
        self._control = WalkerControl(
            acceleration=0.0,
            heading=0.0
        )

    def json_data(self):
        return {
            "id": self.id,
            "category": self._category,
            "sub_category": self._sub_category,
            "location": self._location.json_data(),
            "speed": self._speed,
            "angular_speed": self._angular_speed,
            "acceleration": self._acceleration,
            "bbox": self._bbox.json_data(),
            "control": self._control.json_data(),
            "polygon": self.get_polygon_points(),
        }

    @classmethod
    def blueprint(cls):
        return {
            'category': cls._category,
            'sub_category': cls._sub_category,
            'bbox': cls._bbox.json_data()
        }

    ###### public properties ######
    @property
    def location(self) -> Location:
        return self._location

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def angular_speed(self) -> float:
        return self._angular_speed

    @property
    def acceleration(self) -> float:
        return self._acceleration

    @property
    def bbox(self) -> BoundingBox:
        return self._bbox

    @property
    def control(self) -> WalkerControl:
        return self._control

    def apply_control(self, control: WalkerControl or None):
        self._control = control

    def get_forward_vector(self) -> List:
        init_vector = [1, 0]
        forward_vector = right_rotation(init_vector, -self._location.yaw)
        return forward_vector

    def get_polygon_points(self) -> Tuple[Tuple[float]]:
        half_w = self._bbox.width / 2.0

        front_l = self._bbox.length / 2.0
        back_l = -1 * self._bbox.length / 2.0

        sin_h = math.sin(self._location.yaw)
        cos_h = math.cos(self._location.yaw)
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
            points.append([self._location.x + x, self._location.y + y])

        return points

    def _tick(self, delta_time: float):
        acceleration = self._control.acceleration
        heading = self._control.heading

        self._last_location = copy.deepcopy(self._location)
        curr_acceleration = float(np.clip(acceleration, -abs(self._max_deceleration), abs(self._max_acceleration)))
        curr_speed = self._speed
        next_speed = curr_speed + curr_acceleration * delta_time  # according to the frequency
        next_speed = max(0.0, next_speed)  # Ensure speed is non-negative

        next_heading = normalize_angle(heading)

        next_x = self._location.x + next_speed * math.cos(next_heading) * delta_time
        next_y = self._location.y + next_speed * math.sin(next_heading) * delta_time

        # 6. Create the next state
        self._location.x = next_x
        self._location.y = next_y
        self._location.yaw = next_heading
        self._speed = next_speed
        self._acceleration = curr_acceleration
        self._angular_speed = next_speed
