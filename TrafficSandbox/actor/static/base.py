import copy
import math

from typing import List

from actor.base import Actor
from actor.misc import right_rotation

from common.data_structure import Location, BoundingBox

class StaticActor(Actor):

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

    _category: str = 'static'
    _sub_category: str = 'static'

    def __init__(self, id: int, location: Location):
        super(StaticActor, self).__init__(id)
        self._location = copy.deepcopy(location)

    def json_data(self):
        return {
            "id": self.id,
            "category": self._category,
            "sub_category": self._sub_category,
            "location": self._location.json_data(),
            "speed": self.speed,
            "angular_speed": self.angular_speed,
            "acceleration": self.acceleration,
            "bbox": self._bbox.json_data(),
            "polygon": self.get_polygon_points()
        }

    @classmethod
    def blueprint(cls):
        return {
            'category': cls._category,
            'sub_category': cls._sub_category,
            'bbox': cls._bbox.json_data()
        }

    @property
    def speed(self) -> float:
        return 0.0

    @property
    def angular_speed(self) -> float:
        return 0.0

    @property
    def acceleration(self) -> float:
        return 0.0

    ###### public properties ######
    @property
    def location(self) -> Location:
        return copy.deepcopy(self._location)

    @property
    def bbox(self) -> BoundingBox:
        return copy.deepcopy(self._bbox)

    def update_location(self, location: Location):
        self._location = copy.deepcopy(location)

    def get_forward_vector(self) -> List:
        init_vector = [1, 0]
        forward_vector = right_rotation(init_vector, -self._location.yaw)
        return forward_vector

    def get_polygon_points(self) -> List[List[float]]:
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
        pass