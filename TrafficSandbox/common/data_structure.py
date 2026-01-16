import math

from dataclasses import dataclass, asdict
from typing import Dict

@dataclass
class Lane:

    id: str
    s: float
    l: float

    def json_data(self):
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'Lane':
        return cls(**json_node)

@dataclass
class Location:

    x: float
    y: float
    z: float
    pitch: float
    yaw: float # heading
    roll: float

    @property
    def heading(self):
        return self.yaw

    def json_data(self):
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'Location':
        return cls(**json_node)

    def distance(self, other: 'Location') -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2) ** 0.5

@dataclass
class Waypoint:

    lane: Lane
    location: Location
    speed: float

    @classmethod
    def from_json(cls, json_node: Dict) -> 'Waypoint':
        json_node['lane'] = Lane.from_json(json_node['lane'])
        json_node['location'] = Location.from_json(json_node['location'])
        return cls(**json_node)

    def json_data(self):
        return asdict(self)

    def distance(self, other: 'Waypoint'):
        return math.sqrt((self.location.x - other.location.x) ** 2 + (self.location.y - other.location.y) ** 2 + (self.location.z - other.location.z) ** 2)

@dataclass
class BoundingBox:

    length: float
    width: float
    height: float

    def json_data(self):
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'BoundingBox':
        return cls(**json_node)