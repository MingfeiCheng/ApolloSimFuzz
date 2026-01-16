from tinyrpc import RPCClient
from tinyrpc.protocols.msgpackrpc import MSGPACKRPCProtocol as MsgpackRPCProtocol
from tinyrpc.transports.zmq import ZmqClientTransport
import zmq

from loguru import logger

class DotRPCProxy:
    def __init__(self, client, prefix="", one_way=False):
        self.client = client
        self.prefix = prefix
        self.one_way = one_way

    def __getattr__(self, name):
        new_prefix = f"{self.prefix}.{name}" if self.prefix else name
        print(f"__getattr__ -> new prefix: {new_prefix}")
        return DotRPCProxy(self.client, new_prefix, self.one_way)

    def __call__(self, *args, **kwargs):
        # 🔥 flatten args: MsgpackRPC 需要 list，而不是嵌套 tuple
        print(f"__call__ -> prefix={self.prefix}, args={args}, kwargs={kwargs}")

        flat_args = list(args)
        return self.client.call(self.prefix, flat_args, {}, one_way=self.one_way)


REP_PORT = 10667

ctx = zmq.Context()
transport = ZmqClientTransport.create(ctx, f"tcp://127.0.0.1:{REP_PORT}")
client = RPCClient(MsgpackRPCProtocol(), transport)

proxy = DotRPCProxy(client)

print(proxy.sim.reset())
print(proxy.sim.get_time())
print(proxy.map.load_map("borregas_ave"))
print(proxy.map.lane.get_all(False, "CITY_DRIVING"))
# print(proxy.server.shutdown())
