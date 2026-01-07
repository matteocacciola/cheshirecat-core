from typing import Any, Dict, Set
from weakref import WeakValueDictionary

from cat.utils import singleton, run_sync_or_async


@singleton
class HumptyDumpty:
    """
    A singleton class for managing event subscriptions and dispatching.

    The HumptyDumpty class provides a mechanism to subscribe decorated methods from objects
    to named events and dispatch those events with optional positional and keyword arguments.
    It supports both synchronous and asynchronous callbacks.

    Attributes:
        _subscribers: A dictionary mapping event names to sets of (obj_id, method_name) tuples.
        _objects: A weak reference dictionary to keep track of subscribed objects.

    Methods:
        subscribe_from: Subscribe all decorated methods from an object.
        unsubscribe_from: Unsubscribe all decorated methods from an object.
        dispatch: Dispatch an event to all registered callbacks.
    """
    def __init__(self):
        # Object-based subscriptions (obj_id, method_name)
        self._subscribers: Dict[str, Set[tuple[int, str]]] = {}
        # Use WeakValueDictionary to avoid preventing garbage collection
        self._objects: WeakValueDictionary[int, Any] = WeakValueDictionary()

    def subscribe_from(self, obj: Any) -> None:
        """
        Subscribe all methods decorated with @subscriber from an object.

        This method ensures that the same object cannot be subscribed multiple times
        by using the object's id as a unique identifier.
        """
        obj_id = id(obj)
        self._objects[obj_id] = obj

        for name, method in vars(type(obj)).items():
            if not callable(method) or not hasattr(method, "event_name"):
                continue

            event_name = method.event_name
            if event_name not in self._subscribers:
                self._subscribers[event_name] = set()

            # Add as (obj_id, method_name) tuple - set will prevent duplicates
            self._subscribers[event_name].add((obj_id, name))

    def unsubscribe_from(self, obj: Any) -> None:
        """
        Unsubscribe all methods decorated with @subscriber from an object.
        """
        obj_id = id(obj)

        for name, method in vars(type(obj)).items():
            if not callable(method) or not hasattr(method, "event_name"):
                continue

            event_name = method.event_name
            if event_name in self._subscribers:
                self._subscribers[event_name].discard((obj_id, name))

        # Remove from objects dict (WeakValueDictionary will handle cleanup)
        if obj_id in self._objects:
            del self._objects[obj_id]

    def dispatch(self, event_name: str, *args, **kwargs) -> None:
        """
        Dispatch an event to all registered callbacks.
        """
        if event_name not in self._subscribers:
            return
        for obj_id, method_name in self._subscribers[event_name]:
            # Check if object still exists (weak reference might have been cleaned up)
            if obj_id in self._objects:
                obj = self._objects[obj_id]
                callback = getattr(obj, method_name)
                run_sync_or_async(callback, *args, **kwargs)


def subscriber(event_name: str):
    """
    Decorator to mark a method as an event subscriber.

    Usage:
        @subscriber("event_name")
        def my_handler(self, ...):
            pass
    """
    def decorator(func):
        func.event_name = event_name
        return func

    return decorator
