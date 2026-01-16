import inspect
import traceback
import threading
from loguru import logger

_RPC_CONTEXT = threading.local()

import functools
import traceback
from loguru import logger

def sandbox_api(name=None):
    """Mark a method as exposed RPC endpoint (safe decorator with debug)."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            is_rpc = getattr(_RPC_CONTEXT, "active", False)
            try:
                result = func(*args, **kwargs)
                if is_rpc:
                    return {"status": "ok", "data": result}
                else:
                    return result
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"[RPC ERROR] {func.__name__}: {e}\n{tb}")
                if is_rpc:
                    return {
                        "status": "error",
                        "message": str(e),
                        "traceback": tb,
                    }
                raise

        wrapper._sandbox_api = True
        wrapper._sandbox_name = name or func.__name__
        return wrapper
    return decorator


def register_module_api(dispatcher, module_instance, namespace: str = None, visited=None):
    """
    Safely and lazily register all @sandbox_api methods from module_instance and its submodules.
    Supports C-extension objects and handles dynamic rebind (e.g., map reload).
    """
    if visited is None:
        visited = set()
    if id(module_instance) in visited:
        return
    visited.add(id(module_instance))

    cls_name = module_instance.__class__.__name__
    prefix = f"{namespace}." if namespace else ""

    # 注册 @sandbox_api 方法（类级别）
    for name, func in inspect.getmembers(module_instance.__class__, predicate=inspect.isfunction):
        if getattr(func, "_sandbox_api", False):
            rpc_name = f"{prefix}{func._sandbox_name}"

            # ✅ Lazy path resolver: 每次执行时重新解析路径
            def _lazy_caller(*args, __path=rpc_name, **kwargs):
                parts = __path.split(".")
                root = getattr(dispatcher, "root_object", None)
                if root is None:
                    raise RuntimeError("dispatcher.root_object is not set")

                for p in parts[:-1]:
                    root = getattr(root, p)
                method = getattr(root, parts[-1])
                return method(*args, **kwargs)

            dispatcher.add_method(_lazy_caller, name=rpc_name)
            logger.info(f"[RPC] Registered {cls_name} method: {rpc_name}")

    # ✅ 安全递归探索子模块
    for attr_name in dir(module_instance):
        if attr_name.startswith("_"):
            continue

        try:
            attr_value = getattr(module_instance, attr_name)
        except Exception:
            continue

        # 跳过基础类型、模块、函数等
        if isinstance(attr_value, (int, float, str, bool, list, tuple, dict, set, type(None))):
            continue
        if inspect.isfunction(attr_value) or inspect.ismethod(attr_value):
            continue
        if inspect.isclass(attr_value) or inspect.ismodule(attr_value):
            continue
        if id(attr_value) in visited:
            continue

        # ✅ 仅递归普通 Python 对象（有 __dict__ 或 slots）
        if hasattr(attr_value, "__dict__") or hasattr(attr_value, "__slots__"):
            sub_namespace = f"{prefix}{attr_name}"
            register_module_api(dispatcher, attr_value, namespace=sub_namespace, visited=visited)
