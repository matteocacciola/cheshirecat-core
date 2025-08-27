from cat.auth.permissions import AuthPermission, AuthResource, check_websocket_permissions
from cat.auth.connection import AuthorizedInfo
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cat.convo.messages import UserMessage
from cat.log import log
from cat.looking_glass.stray_cat import StrayCat

router = APIRouter()


@router.websocket("/ws")
@router.websocket("/ws/{agent_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    info: AuthorizedInfo = check_websocket_permissions(AuthResource.CONVERSATION, AuthPermission.WRITE),
):
    """
    Endpoint to handle incoming WebSocket connections by user id, process messages, and check for messages.
    """
    # Extract the StrayCat object from the DependingCats object.
    stray = StrayCat(user_data=info.user, agent_id=info.cheshire_cat.id)

    # Establish connection
    await websocket.accept()

    # Add the new WebSocket connection to the manager.
    websocket_manager = info.cheshire_cat.websocket_manager
    websocket_manager.add_connection(stray.user.id, websocket)

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
            await stray.run_websocket(user_message)
    except WebSocketDisconnect:
        log.info(f"WebSocket connection closed for user {stray.user.id}")
    finally:
        # Remove connection on disconnect
        websocket_manager.remove_connection(stray.user.id)
