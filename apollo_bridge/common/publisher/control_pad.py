from apollo_modules.modules.common.proto.header_pb2 import Header
from apollo_modules.modules.canbus.proto.chassis_pb2 import Chassis
from apollo_modules.modules.control.proto.pad_msg_pb2 import PadMessage, DrivingAction

from .base import Publisher
from registry import PUBLISHER_REGISTRY

@PUBLISHER_REGISTRY.register('publisher.control_pad')
class ControlPadPublisher(Publisher):

    channel: str = '/apollo/control/pad'
    msg_type: str = 'apollo.control.PadMessage'
    msg_cls: any = PadMessage
    frequency: float = 1000.0 # set large as we do not need to limit the frequency here

    def __init__(self, idx, bridge):
        super(ControlPadPublisher, self).__init__(idx, bridge)

    def _process_data(self, message):
        
        header = Header(
            timestamp_sec=message.timestamp,
            module_name='MAGGIE',
            sequence_num=self.frame_count
        )

        if message.action == 0:
            pad_action = DrivingAction.STOP
        elif message.action == 1:
            pad_action = DrivingAction.START
        else:
            pad_action = DrivingAction.RESET

        pad_info = PadMessage(
            header=header,
            driving_mode=Chassis.DrivingMode.COMPLETE_AUTO_DRIVE,
            action=pad_action,
        )

        return pad_info