from common.data_structure import Location, BoundingBox

from actor.static.base import StaticActor
from registry import ACTOR_REGISTRY

@ACTOR_REGISTRY.register("static.traffic_cone")
class TrafficCone(StaticActor):

    # basic information - fixed
    category: str = 'static.traffic_cone'

    _bbox: BoundingBox = BoundingBox(
        length=0.35,
        width=0.35,
        height=0.7
    )

    def __init__(self, id: int, location: Location):
        super(TrafficCone, self).__init__(id, location)