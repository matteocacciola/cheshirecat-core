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
    # Establish connection
    await websocket.accept()

    # Add the new WebSocket connection to the manager.
    websocket_manager = info.lizard.websocket_manager
    websocket_manager.add_connection(info.user.id, websocket)

    stray_cat = info.stray_cat or StrayCat(
        user_data=info.user,
        agent_id=info.cheshire_cat.id,
        plugin_manager_generator=lambda: info.cheshire_cat.plugin_manager,
    )
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

            # Run the `stray` object's method in a threadpool since it might be a CPU-bound operation.
            await stray_cat.run_websocket(user_message)
    except WebSocketDisconnect:
        log.info(f"WebSocket connection closed for user {info.user.id}")
    finally:
        # Remove connection on disconnect
        websocket_manager.remove_connection(stray_cat.user.id)
