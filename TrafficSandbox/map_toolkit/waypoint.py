from dataclasses import dataclass, asdict

@dataclass
class Waypoint:
    
    lane_id: str
    is_junction: bool

    s: float
    l: float
    x: float
    y: float
    heading: float
    
    def to_dict(self) -> dict:
        return asdict(self)