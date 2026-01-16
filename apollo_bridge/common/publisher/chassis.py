from apollo_modules.modules.common.proto.header_pb2 import Header
from apollo_modules.modules.canbus.proto.chassis_pb2 import Chassis

from .base import Publisher
from registry import PUBLISHER_REGISTRY

@PUBLISHER_REGISTRY.register('publisher.chassis')
class ChassisPublisher(Publisher):

    channel: str = '/apollo/canbus/chassis'
    msg_type: str = 'apollo.canbus.Chassis'
    msg_cls: any = Chassis

    def __init__(self, idx, bridge):
        super(ChassisPublisher, self).__init__(idx, bridge)

    def _process_data(self, message):
        header = Header(
            timestamp_sec=message.timestamp,
            module_name='MAGGIE',
            sequence_num=self.frame_count
        )

        speed_mps = message.speed_mps
        if message.reverse:
            gear_location = Chassis.GearPosition.GEAR_REVERSE
            speed_mps = -speed_mps
        else:
            gear_location = Chassis.GearPosition.GEAR_NEUTRAL

        chassis = Chassis(
            header=header,
            engine_started=True,
            driving_mode=Chassis.DrivingMode.COMPLETE_AUTO_DRIVE,
            gear_location=gear_location,
            speed_mps=speed_mps,
            throttle_percentage=message.throttle_percentage,
            brake_percentage=message.brake_percentage,
            steering_percentage=message.steering_percentage
        )

        return chassis