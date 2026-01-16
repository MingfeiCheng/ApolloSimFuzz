from registry import ACTOR_REGISTRY
from .base import VehicleActor, Location, BoundingBox, PerfectVehicleActor

@ACTOR_REGISTRY.register("vehicle.lincoln.mkz_lgsvl")
class LincolnMKZLGSVL(VehicleActor):

    # basic information - fixed
    category: str = 'vehicle.lincoln.mkz_lgsvl'

    _bbox: BoundingBox = BoundingBox(
        length=4.70,
        width=2.06,
        height=2.05
    )

    _max_acceleration: float = 2.0 #5.59 # not accuracy
    _max_deceleration: float = -6.0

    _front_edge_to_center: float = 3.705
    _back_edge_to_center: float = 0.995
    _left_edge_to_center: float = 1.03
    _right_edge_to_center: float = 1.03

    _max_steer_angle: float = 8.20304748437 # radians * 180 / math.pi
    _max_steer_angle_rate: float = 6.98131700798
    _steer_ratio: float = 16.0

    _wheelbase: float = 2.837007
    _max_abs_speed_when_stopped: float = 0.2


    def __init__(self, id: int, location: Location):
        super(LincolnMKZLGSVL, self).__init__(id, location)


@ACTOR_REGISTRY.register("vehicle.lincoln.mkz_lgsvl.perfect")
class PerfectLincolnMKZLGSVL(PerfectVehicleActor):

    # basic information - fixed
    category: str = 'vehicle.lincoln.mkz_lgsvl.perfect'

    _bbox: BoundingBox = BoundingBox(
        length=4.70,
        width=2.06,
        height=2.05
    )

    _max_acceleration: float = 2.0  # 5.59 # not accuracy
    _max_deceleration: float = -6.0

    _front_edge_to_center: float = 3.705
    _back_edge_to_center: float = 0.995
    _left_edge_to_center: float = 1.03
    _right_edge_to_center: float = 1.03

    _max_steer_angle: float = 8.20304748437  # radians * 180 / math.pi
    _max_steer_angle_rate: float = 6.98131700798
    _steer_ratio: float = 16.0

    _wheelbase: float = 2.837007
    _max_abs_speed_when_stopped: float = 0.2

    def __init__(self, id: int, location: Location):
        super(PerfectLincolnMKZLGSVL, self).__init__(id, location)
