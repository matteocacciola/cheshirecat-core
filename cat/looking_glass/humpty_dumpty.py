import asyncio
import concurrent.futures
from typing import Callable, Any, List, Dict

from cat.utils import singleton


@singleton
class HumptyDumpty:
    """
    A singleton class for managing event subscriptions and dispatching.

    The HumptyDumpty class provides a mechanism to subscribe
    callbacks to named events and dispatch those events with optional
    positional and keyword arguments. It supports both synchronous
    and asynchronous callbacks.

    Attributes:
        _subscribers: A dictionary mapping event names to lists of callbacks.

    Methods:
        subscribe: Add a callback to the list of subscribers for a given event.
        dispatch: Dispatch an event to all registered callbacks.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[..., Any]]] = {}

    def subscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        self._subscribers[event_name].append(callback)

    def dispatch(self, event_name: str, *args, **kwargs) -> None:
        if event_name in self._subscribers:
            for callback in self._subscribers[event_name]:
                self._execute_callback(callback, *args, **kwargs)

    def _execute_callback(self, callback: Callable[..., Any], *args, **kwargs) -> Any:
        if not asyncio.iscoroutinefunction(callback) and not asyncio.iscoroutine(callback):
            return callback(*args, **kwargs)

        coro = callback(*args, **kwargs)

        try:
            asyncio.get_running_loop()
            def run_async_in_thread():
                return asyncio.run(coro)
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async_in_thread)
                return future.result()
        except RuntimeError:
            return asyncio.run(coro)

    @classmethod
    def run_sync_or_async(cls, callback: Callable[..., Any], *args, **kwargs) -> Any:
        instance = cls()
        return instance._execute_callback(callback, *args, **kwargs)


def subscriber(event_name: str):
    def decorator(func):
        func.event_name = event_name
        return func
    return decorator
