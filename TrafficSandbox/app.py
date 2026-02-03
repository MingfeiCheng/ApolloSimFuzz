# file: sandbox_server.py
import os
import sys
import zmq
import time
import types
import json
import threading

from datetime import datetime
from loguru import logger
from tinyrpc.server import RPCServer
from tinyrpc.transports.zmq import ZmqServerTransport
from tinyrpc.protocols.msgpackrpc import MSGPACKRPCProtocol as MsgpackRPCProtocol
from tinyrpc.dispatch import RPCDispatcher
from zmq.error import ContextTerminated, ZMQError

from flask import Flask, render_template
from flask_socketio import SocketIO

from config import Config
from common.utils import discover_modules
from common.rpc_utils import register_module_api, sandbox_api

from simulator import Simulator
from map_toolkit import MapManager

_RPC_CONTEXT = threading.local()

REP_PORT = 10667
VIS_PORT = 8888
DEFAULT_MAP = "borregas_ave"

class GracefulRPCServer(RPCServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._running = True

    def serve_forever(self):
        logger.info("[RPC] TinyRPC server loop started.")
        while self._running:
            try:
                self.receive_one_message()
            except ContextTerminated:
                logger.info("[RPC] ZMQ context terminated.")
                break
            except ZMQError as e:
                if e.errno in (156384763, 88):
                    logger.info("[RPC] ZMQ socket closed.")
                    break
                else:
                    logger.warning(f"[RPC] ZMQ error: {e}")
                    break
            except Exception as e:
                logger.error(f"[RPC] RPC loop error: {e}")
                break
        logger.info("[RPC] serve_forever() exited.")

    def stop(self):
        logger.info("[RPC] GracefulRPCServer.stop() called.")
        self._running = False
        try:
            if hasattr(self.transport, "socket"):
                self.transport.socket.close(linger=0)
            if hasattr(self.transport, "context"):
                self.transport.context.term()  # ✅ 立即唤醒阻塞的 receive
        except Exception as e:
            logger.warning(f"[RPC] Ignored socket close error: {e}")


class TrafficSandbox:
    def __init__(self, fps: float = 100.0):
        
        self.host = "0.0.0.0"
        
        self.timeout = 120.0
        
        self.shutdown_requested = False
        
        self.sim = Simulator(fps=fps)
        self.map = MapManager()

        self._ctx = zmq.Context()

        self.dispatcher = RPCDispatcher()
        self.dispatcher.root_object = self
        
        register_module_api(self.dispatcher, self, namespace="")

        orig_dispatch = self.dispatcher.dispatch
        def debug_dispatch(self, request, caller=None):
            try:
                _RPC_CONTEXT.active = True
                logger.info(
                    f"[RPC DISPATCH] {request.method}, args={getattr(request, 'args', None)}"
                )
                response = orig_dispatch(request, caller)
                logger.debug(
                    f"[RPC DISPATCH] Done: {request.method}, result={getattr(response, 'result', None)}"
                )
                return response
            except Exception as e:
                logger.exception(f"[RPC DISPATCH] Exception in {request.method}: {e}")
                raise
            finally:
                _RPC_CONTEXT.active = False

        self.dispatcher.dispatch = types.MethodType(debug_dispatch, self.dispatcher)
            
        self.transport = ZmqServerTransport.create(self._ctx, f"tcp://{self.host}:{REP_PORT}")
        self.server = GracefulRPCServer(
            transport=self.transport,
            protocol=MsgpackRPCProtocol(),
            dispatcher=self.dispatcher
        )
        
        # vis
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = 'secret!'
        self.socketio = SocketIO(
            self.app,
            async_mode="threading",
            cors_allowed_origins="*",
            logger=False,
            engineio_logger=False
        )
        self._setup_routes()
        
        threading.Thread(target=self.traffic_dataflow, daemon=True).start()
    
    # front
    def _emit_traffic(self, data):
        try:
            self.socketio.emit("traffic_update", data)
        except Exception as e:
            logger.error(f"[SocketIO] Failed to emit traffic: {e}")
        
    def traffic_dataflow(self):
        logger.info("[Sandbox] Publisher thread started for frontend.")
        while not self.shutdown_requested:
            try:
                snapshot = self.sim.get_snapshot()
                traffic_data = {
                    "map_name": self.map.get_current_map(),
                    "frame": snapshot.get("frame", 0),
                    "game_time": snapshot.get("game_time", 0.0),
                    "real_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "actors": snapshot.get("actors", []),
                    "traffic_lights": snapshot.get("traffic_lights", [])
                }
                # self.socketio.emit("traffic_update", traffic_data)
                self.socketio.start_background_task(self._emit_traffic, traffic_data)
                time.sleep(0.05)
            except Exception as e:
                logger.warning(f"[Sandbox] Publisher error: {e}")
                time.sleep(1.0)
                
    def start_flask(self):
        logger.info(f"[SimRender] Flask app imported templates from: {self.app.template_folder}")
        logger.info(f"[SimRender] Server starting on {self.host}:{VIS_PORT}")
        try:
            self.socketio.run(
                self.app,
                host=self.host,
                port=VIS_PORT,
                debug=False,
                use_reloader=False,
                log_output=False
            )
        except Exception as e:
            logger.error(f"[SimRender] Server error: {e}")
        finally:
            logger.info("[SimRender] Server stopped.")
                
    @sandbox_api("set_timeout")
    def set_timeout(self, timeout: float):
        """Remote callable: Set the timeout duration for map loading."""
        logger.info(f"[Sandbox] Setting timeout to {timeout} seconds.")
        self.timeout = timeout
        return {"status": "ok", "timeout": self.timeout}
    
    @sandbox_api(name="load_map")
    def load_map(self, map_name: str):
        logger.info(f"[Sandbox] Reloading map from: {map_name}")

        try:
            self.socketio.emit("map_loading_start", {"map_name": map_name})
        except Exception as e:
            logger.warning(f"[SocketIO] Failed to emit map_loading_start: {e}")

        try:
            self.map.load_map(map_name)
            new_map_data = self.map.get_render_data()
        except Exception as e:
            logger.error(f"[Sandbox] Failed to load map {map_name}: {e}")
            self.socketio.emit("map_loading_error", {"error": str(e)})
            return {"status": "error", "message": str(e)}

        try:
            # payload = json.loads(json.dumps(new_map_data))
            self.socketio.emit("init_map", new_map_data)
            logger.info(f"[Sandbox] Map {map_name} sent to frontend")
        except Exception as e:
            logger.error(f"[Sandbox] Failed to emit map {map_name}: {e}")
            self.socketio.emit("map_loading_error", {"error": str(e)})

        self.socketio.emit("map_loading_done", {"map_name": map_name})
        return {"status": "ok", "map": map_name}

    ### frontend #####
    def _setup_routes(self):
        @self.app.route('/')
        def index():
            logger.info("[Sandbox] Serving index page.")
            return render_template(
                "index.html"
            )
    
    def start(self):
        logger.info("Starting TrafficSandbox...")
        self.sim.start(blocking=False)
        
        # start front
        threading.Thread(target=self.start_flask, daemon=True).start()
        
        logger.info(f"TinyRPC server listening on tcp://{self.host}:{REP_PORT}")
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            self.shutdown()
        finally:
            logger.info("[Main] Waiting for cleanup to finish...")
            time.sleep(0.5)
            sys.exit(0)

    @sandbox_api(name="shutdown")
    def shutdown(self):
        """Remote callable: Gracefully shut down the server and all components."""
        logger.info("[RPC] Shutdown command received. Preparing to stop server, simulator, and renderer...")

        response = {"status": "ok", "message": "Server shutting down."}
        
        self.shutdown_requested = True

        def async_cleanup():
            time.sleep(0.2)

            try:
                logger.info("[RPC] Stopping simulator...")
                self.sim.shutdown()
            except Exception as e:
                logger.warning(f"[RPC] Simulator shutdown failed: {e}")

            try:
                logger.info("[RPC] Attempting to stop SocketIO...")
                if hasattr(self.socketio, "stop"):
                    # Only stop if running inside HTTP server context
                    from flask import has_request_context
                    if has_request_context():
                        self.socketio.stop()
                    else:
                        logger.info("[RPC] No HTTP context detected, skipping socketio.stop()")
            except Exception as e:
                logger.warning(f"[RPC] Render shutdown failed: {e}")

            try:
                logger.info("[RPC] Stopping TinyRPC transport...")
                if hasattr(self, "transport") and hasattr(self.transport, "socket"):
                    self.transport.socket.close(linger=0)
                if hasattr(self, "_ctx"):
                    self._ctx.term()
                logger.info("[RPC] TinyRPC transport closed.")
            except Exception as e:
                logger.warning(f"[RPC] Failed to close ZMQ transport cleanly: {e}")

            try:
                if hasattr(self, "server") and hasattr(self.server, "stop"):
                    self.server.stop()
                    logger.info("[RPC] GracefulRPCServer loop exited.")
            except Exception as e:
                logger.warning(f"[RPC] Server stop failed: {e}")
                
            logger.info("[RPC] All components stopped successfully.")

        threading.Thread(target=async_cleanup, daemon=True).start()
        logger.info("[RPC] Shutdown sequence initiated.")
        return response

if __name__ == "__main__":
    discover_modules(os.path.dirname(os.path.abspath(__file__)))

    # argument
    import argparse
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--fps", type=float, default=100.0)
    args = arg_parser.parse_args()

    # setup logging
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    Config.log_dir = log_dir
    Config.debug = True
    Config.fps = args.fps

    level = 'DEBUG'
    logger.configure(handlers=[{"sink": sys.stderr, "level": level}])
    logger_file = os.path.join(Config.log_dir, 'run.log')

    logger.add(
        logger_file,
        level=level,
        mode="a",
        rotation="10 MB",   # 超过 10MB 触发轮转
        retention=0,        # 旧日志立刻删除
    )


    sandbox = TrafficSandbox(fps=Config.fps)
    sandbox.start()