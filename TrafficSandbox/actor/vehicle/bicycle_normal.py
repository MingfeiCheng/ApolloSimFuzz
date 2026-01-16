from registry import ACTOR_REGISTRY

from .base import VehicleActor, Location, BoundingBox, PerfectVehicleActor

@ACTOR_REGISTRY.register("vehicle.bicycle.normal")
class BicycleNormal(VehicleActor):

    # basic information - fixed
    category: str = "vehicle.bicycle.normal"

    _bbox: BoundingBox = BoundingBox(
        length=3.0,
        width=1.0,
        height=1.8
    )

    _max_acceleration: float = 2.0 #5.59 # not accuracy
    _max_deceleration: float = -6.0

    _front_edge_to_center: float = 1.5
    _back_edge_to_center: float = 1.5
    _left_edge_to_center: float = 0.5
    _right_edge_to_center: float = 0.5

    _max_steer_angle: float = 8.20304748437 # radians * 180 / math.pi
    _max_steer_angle_rate: float = 6.98131700798

    _steer_ratio: float = 16.0

    _wheelbase: float = 2.8448
    _max_abs_speed_when_stopped: float = 0.2

    def __init__(self, id: int, location: Location):
        super(BicycleNormal, self).__init__(id, location)

@ACTOR_REGISTRY.register("vehicle.bicycle.normal.perfect")
class PerfectBicycleNormal(PerfectVehicleActor):

    # basic information - fixed
    category: str = "vehicle.bicycle.normal.perfect"

    _bbox: BoundingBox = BoundingBox(
        length=3.0,
        width=1.0,
        height=1.8
    )

    _max_acceleration: float = 2.0 #5.59 # not accuracy
    _max_deceleration: float = -6.0

    _front_edge_to_center: float = 1.5
    _back_edge_to_center: float = 1.5
    _left_edge_to_center: float = 0.5
    _right_edge_to_center: float = 0.5

    _max_steer_angle: float = 8.20304748437 # radians * 180 / math.pi
    _max_steer_angle_rate: float = 6.98131700798

    _steer_ratio: float = 16.0

    _wheelbase: float = 2.8448
    _max_abs_speed_when_stopped: float = 0.2

    def __init__(self, id: int, location: Location):
        super(PerfectBicycleNormal, self).__init__(id, location)
