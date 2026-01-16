import json
import numpy as np

from typing import List, Dict
from dataclasses import dataclass, asdict

@dataclass
class Vector:
    x: float
    y: float
    z: float

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'Vector':
        return cls(**json_node)

@dataclass
class Lane:

    id: str
    s: float
    l: float

    def to_json(self):
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

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'Location':
        return cls(**json_node)

@dataclass
class Waypoint:

    lane: Lane
    location: Location

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'Waypoint':
        json_node['lane'] = Lane.from_json(json_node['lane'])
        json_node['location'] = Location.from_json(json_node['location'])
        return cls(**json_node)

@dataclass
class Obstacle:

    id: int
    category: str
    length: float
    width: float
    height: float
    location: Location
    velocity: Vector
    bbox_points: List[List[float]]

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'Obstacle':
        json_node['location'] = Location.from_json(json_node['location'])
        json_node['velocity'] = Vector.from_json(json_node['velocity'])
        return cls(**json_node)

@dataclass
class TrafficLightState:

    id: int
    state: str

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'TrafficLightState':
        return cls(**json_node)

@dataclass
class LocalizationMessage:

    timestamp: float
    location: Location
    heading: float
    velocity: Vector
    acceleration: Vector
    angular_velocity: Vector

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'LocalizationMessage':
        json_node['location'] = Location.from_json(json_node['location'])
        json_node['velocity'] = Vector.from_json(json_node['velocity'])
        json_node['acceleration'] = Vector.from_json(json_node['acceleration'])
        json_node['angular_velocity'] = Vector.from_json(json_node['angular_velocity'])
        return cls(**json_node)

@dataclass
class ChassisMessage:

    timestamp: float
    speed_mps: float
    throttle_percentage: float # NOTE: in [0, 100]
    brake_percentage: float
    steering_percentage: float
    reverse: bool

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'ChassisMessage':
        return cls(**json_node)

@dataclass
class PerfectObstacleMessage:

    timestamp: float
    obstacles: List[Obstacle]

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'PerfectObstacleMessage':
        json_node['obstacles'] = [Obstacle.from_json(item) for item in json_node['obstacles']]
        return cls(**json_node)

@dataclass
class PerfectTrafficLightMessage:

    timestamp: float
    traffic_lights: List[TrafficLightState]

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'PerfectTrafficLightMessage':
        json_node['traffic_lights'] = [TrafficLightState.from_json(item) for item in json_node['traffic_lights']]
        return cls(**json_node)

@dataclass
class RouteMessage:
    timestamp: float
    waypoints: List[Waypoint]

    def to_json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'RouteMessage':
        json_node['waypoints'] = [Waypoint.from_json(item) for item in json_node['waypoints']]
        return cls(**json_node)

@dataclass
class IMUMessage:

    timestamp: float
    angular_velocity: Vector
    linear_acceleration: Vector
    euler_angles: Vector

    def to_json(self) -> dict:
        """Serialize the message to a JSON string."""
        return {
            "timestamp": self.timestamp,
            "angular_velocity": self.angular_velocity.to_json(),
            "linear_acceleration": self.linear_acceleration.to_json(),
            "euler_angles": self.euler_angles.to_json(),
        }

    @classmethod
    def from_json(cls, json_node: Dict) -> 'IMUMessage':
        """Deserialize a JSON object to a IMUMessage."""
        json_node['angular_velocity'] = Vector.from_json(json_node['angular_velocity'])
        json_node['linear_acceleration'] = Vector.from_json(json_node['linear_acceleration'])
        json_node['euler_angles'] = Vector.from_json(json_node['euler_angles'])
        return cls(**json_node)

@dataclass
class GNSSMessage:

    timestamp: float
    latitude: float
    longitude: float
    altitude: float

    def to_json(self) -> dict:
        """Serialize the message to a JSON string."""
        return {
            "timestamp": self.timestamp,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
        }

    @classmethod
    def from_json(cls, json_node: Dict) -> 'GNSSMessage':
        """Deserialize a JSON object to a GNSSMessage."""
        return cls(
            timestamp=json_node["timestamp"],
            latitude=json_node["latitude"],
            longitude=json_node["longitude"],
            altitude=json_node["altitude"],
        )

@dataclass
class GPSMessage:

    timestamp: float
    location: Location
    heading: float
    ins_status: int
    pos_type: int

    def to_json(self) -> dict:
        """Serialize the message to a JSON string."""
        return json.dumps({
            "timestamp": self.timestamp,
            "location": self.location.to_json(),
            "heading": self.heading,
            "ins_status": self.ins_status,
            "pos_type": self.pos_type,
        })

    @classmethod
    def from_json(cls, json_node: Dict) -> 'GPSMessage':
        """Deserialize a JSON object to a GPSMessage."""
        json_node['location'] = Location.from_json(json_node['location'])
        return cls(**json_node)

@dataclass
class ControlPadMessage:
    # 0 - stop, 1 - start, 2 - reset
    timestamp: float
    action: int
    
    def to_json(self) -> dict:
        """Serialize the message to a JSON string."""
        return asdict(self)

    @classmethod
    def from_json(cls, json_node: Dict) -> 'ControlPadMessage':
        """Deserialize a JSON object to a ControlPadMessage."""
        return cls(
            timestamp=json_node["timestamp"],
            action=json_node["action"],
        )