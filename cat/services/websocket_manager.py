from typing import List, Dict
from fastapi.websockets import WebSocket


class WebsocketManager:
    def __init__(self):
        # Keep connections in dictionary: user_id -> WebSocket
        self.connections = {}

    def add_connection(self, id: str, websocket: WebSocket):
        """Add a new WebSocket connection"""
        
        self.connections[id] = websocket

    def get_connection(self, id: str) -> WebSocket | None:
        """Retrieve a WebSocket connection by user id"""
        
        return self.connections.get(id, None)

    def remove_connection(self, id: str):
        """Remove a WebSocket connection by user id"""
        if id in self.connections:
            del self.connections[id]

    def broadcast(self, message: dict):
        """Broadcast a message to all connected WebSockets"""
        for connection in self.connections.values():
            connection.send_json(message)

    async def close_all_connections(self):
        """Close all WebSocket connections"""
        for connection in self.connections.values():
            await connection.close()
        self.connections.clear()

    async def close_connection(self, id: str):
        """Close a WebSocket connection by user id"""
        connection = self.get_connection(id)
        if connection:
            await connection.close()
            self.remove_connection(id)

    async def close_connections(self, ids: List[str]):
        """Close multiple WebSocket connections by user id"""
        for id in ids:
            await self.close_connection(id)

    def get_connections(self) -> Dict:
        """Retrieve all WebSocket connections"""
        return self.connections

    def get_connection_ids(self) -> List[str]:
        """Retrieve all user ids of WebSocket connections"""
        return list(self.connections.keys())

    def get_connection_count(self) -> int:
        """Retrieve the number of WebSocket connections"""
        return len(self.connections)

    def is_connected(self, id: str) -> bool:
        """Check if a WebSocket connection exists by user id"""
        return id in self.connections

    def is_empty(self) -> bool:
        """Check if there are no WebSocket connections"""
        return not self.connections

    def is_connected_to(self, id: str) -> bool:
        """Check if a WebSocket connection exists by user id"""
        return self.is_connected(id)

    def is_connected_to_any(self, ids: List[str]) -> bool:
        """Check if any WebSocket connection exists by user id"""
        return any(self.is_connected(id) for id in ids)

    def is_connected_to_all(self, ids: List[str]) -> bool:
        """Check if all WebSocket connections exist by user id"""
        return all(self.is_connected(id) for id in ids)
