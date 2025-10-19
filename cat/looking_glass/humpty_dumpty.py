from typing import Callable, Any, List, Dict

from cat.utils import singleton, run_sync_or_async


@singleton
class HumptyDumpty:
    """
    A singleton class for managing event subscriptions and dispatching.

    The HumptyDumpty class provides a mechanism to subscribe callbacks to named events and dispatch those events with
    optional positional and keyword arguments. It supports both synchronous and asynchronous callbacks.

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

    def unsubscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        if event_name in self._subscribers:
            self._subscribers[event_name].remove(callback)

    def subscribe_from(self, obj: Any):
        for name, method in vars(type(obj)).items():
            if not callable(method) or not hasattr(method, "event_name"):
                continue

            self.subscribe(
                method.event_name,
                method.__get__(obj),  # type: ignore
            )

    def unsubscribe_from(self, obj: Any):
        for name, method in vars(type(obj)).items():
            if not callable(method) or not hasattr(method, "event_name"):
                continue

            self.unsubscribe(
                method.event_name,
                method.__get__(obj),  # type: ignore
            )

    def dispatch(self, event_name: str, *args, **kwargs) -> None:
        if event_name in self._subscribers:
            for callback in self._subscribers[event_name]:
                run_sync_or_async(callback, *args, **kwargs)


def subscriber(event_name: str):
    def decorator(func):
        func.event_name = event_name
        return func
    return decorator
