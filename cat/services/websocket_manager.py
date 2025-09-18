from typing import List, Dict
from fastapi.websockets import WebSocket


class WebSocketManager:
    def __init__(self):
        # Keep connections in dictionary: user_id -> WebSocket
        self.connections = {}

    def add_connection(self, id_conn: str, websocket: WebSocket):
        """Add a new WebSocket connection"""
        self.connections[id_conn] = websocket

    def get_connection(self, id_conn: str) -> WebSocket | None:
        """Retrieve a WebSocket connection by user id_conn"""
        return self.connections.get(id_conn, None)

    def remove_connection(self, id_conn: str):
        """Remove a WebSocket connection by user id_conn"""
        if id_conn in self.connections:
            del self.connections[id_conn]

    def broadcast(self, message: dict):
        """Broadcast a message to all connected WebSockets"""
        for connection in self.connections.values():
            connection.send_json(message)

    async def close_all_connections(self):
        """Close all WebSocket connections"""
        for connection in self.connections.values():
            await connection.close()
        self.connections.clear()

    async def close_connection(self, id_conn: str):
        """Close a WebSocket connection by user id_conn"""
        connection = self.get_connection(id_conn)
        if connection:
            await connection.close()
            self.remove_connection(id_conn)

    async def close_connections(self, ids: List[str]):
        """Close multiple WebSocket connections by user id_conn"""
        for id_conn in ids:
            await self.close_connection(id_conn)

    def get_connections(self) -> Dict:
        """Retrieve all WebSocket connections"""
        return self.connections

    def get_connection_ids(self) -> List[str]:
        """Retrieve all user ids of WebSocket connections"""
        return list(self.connections.keys())

    def get_connection_count(self) -> int:
        """Retrieve the number of WebSocket connections"""
        return len(self.connections)

    def is_connected(self, id_conn: str) -> bool:
        """Check if a WebSocket connection exists by user id_conn"""
        return id_conn in self.connections

    def is_empty(self) -> bool:
        """Check if there are no WebSocket connections"""
        return not self.connections

    def is_connected_to(self, id_conn: str) -> bool:
        """Check if a WebSocket connection exists by user id_conn"""
        return self.is_connected(id_conn)

    def is_connected_to_any(self, ids: List[str]) -> bool:
        """Check if any WebSocket connection exists by user id_conn"""
        return any(self.is_connected(id_conn) for id_conn in ids)

    def is_connected_to_all(self, ids: List[str]) -> bool:
        """Check if all WebSocket connections exist by user id_conn"""
        return all(self.is_connected(id_conn) for id_conn in ids)
