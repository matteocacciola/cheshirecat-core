import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_websocket_permissions
from cat.log import log
from cat.looking_glass import StrayCat
from cat.services.memory.messages import UserMessage

router = APIRouter(tags=["Websocket"])


@router.websocket("/ws")
@router.websocket("/ws/{agent_id}")
@router.websocket("/ws/{agent_id}/{chat_id}")
async def websocket_chat(
    websocket: WebSocket,
    info: AuthorizedInfo = check_websocket_permissions(AuthResource.CHAT, AuthPermission.WRITE),
):
    """
    Endpoint to handle incoming WebSocket connections by user id, process messages, and check for messages.
    """
    stray_cat = info.stray_cat or StrayCat(
        user_data=info.user,
        agent_id=info.cheshire_cat.agent_key,
        plugin_manager_generator=info.cheshire_cat.plugin_manager_generator,
    )

    # Establish connection
    await websocket.accept()

    # Add the new WebSocket connection to the manager.
    websocket_manager = info.lizard.websocket_manager
    websocket_manager.add_connection(stray_cat.id, websocket)
    try:
        # Process messages
        while True:
            # Receive the next message from the WebSocket.
            payload = await websocket.receive_json()

            if payload == "ping":
                # Respond to ping messages with a pong.
                await websocket.send_json("pong")
                continue

            if payload == "pong":
                # Ignore pong messages.
                continue

            user_message = UserMessage(**payload)

            # asyncio.shield keeps the LLM call alive even if the outer task is cancelled
            # (e.g. on server shutdown or mid-stream client disconnect), so the response is
            # still fully processed and persisted to memory.
            await asyncio.shield(stray_cat.run_websocket(user_message))
    except WebSocketDisconnect:
        log.info(f"WebSocket connection closed for conversation {stray_cat.id}")
    except asyncio.CancelledError:
        log.info(f"WebSocket handler cancelled for conversation {stray_cat.id}; ongoing LLM call will complete")
        raise  # propagate so the server can finish its shutdown sequence
    finally:
        # Remove connection on disconnect
        websocket_manager.remove_connection(stray_cat.id)
