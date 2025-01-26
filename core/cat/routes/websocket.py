from cat.auth.permissions import AuthPermission, AuthResource, check_websocket_permissions
from cat.auth.connection import ContextualCats
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cat.convo.messages import UserMessage
from cat.log import log

router = APIRouter()


@router.websocket("/ws")
@router.websocket("/ws/{agent_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    cats: ContextualCats = check_websocket_permissions(AuthResource.CONVERSATION, AuthPermission.WRITE),
):
    """
    Endpoint to handle incoming WebSocket connections by user id, process messages, and check for messages.
    """

    # Extract the StrayCat object from the DependingCats object.
    stray = cats.stray_cat

    # Add the new WebSocket connection to the manager.
    await websocket.accept()
    try:
        # Process messages
        while True:
            # Receive the next message from the WebSocket.
            user_message_text = await websocket.receive_json()
            user_message = UserMessage(**user_message_text)

            # Run the `stray` object's method in a threadpool since it might be a CPU-bound operation.
            await stray.run_websocket(user_message)
    except WebSocketDisconnect:
        # Handle the event where the user disconnects their WebSocket.
        await stray.close()
        log.info("WebSocket connection closed")
