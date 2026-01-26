import hashlib
import hmac
import json
import os.path
from typing import List, Literal, get_args, Dict, Any
import requests
from pydantic import BaseModel, Field

from cat import (
    hook,
    endpoint,
    AuthorizedInfo,
    check_permissions,
    AuthResource,
    AuthPermission,
    PointStruct,
    log,
    StrayCat,
)
import cat.core_plugins.webhooks.crud as crud_webhook
from cat.services.string_crypto import StringCrypto
from cat.utils import get_plugins_path, is_url


WEBHOOK_EVENT = Literal["knowledge_source_loaded", "plugin_installed", "plugin_uninstalled"]

crypto = StringCrypto()


class WebhookResponse(BaseModel):
    url: str
    event: WEBHOOK_EVENT
    header_key: str | None = Field(default="X-CheshireCat-Signature")


class WebhookPayload(WebhookResponse):
    secret: str


def trigger_webhook(webhook_data: WebhookPayload, payload: Dict[str, Any]):
    target_url = webhook_data.url
    custom_header_key = webhook_data.header_key

    secret = crypto.decrypt(webhook_data.secret)

    signature = hmac.new(
        secret.encode("utf-8"),
        msg=json.dumps(payload, separators=(',', ':')).encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    headers = {"Content-Type": "application/json", custom_header_key: signature}
    requests.post(target_url, json=payload, headers=headers)


def parse_agent_key(info: AuthorizedInfo, webhook: WebhookPayload) -> str:
    if webhook.event is not "knowledge_source_loaded":
        return info.lizard.agent_key
    if not info.cheshire_cat:
        raise ValueError("Cannot register / unregister the webhook without a CheshireCat instance")
    return info.cheshire_cat.agent_key


@endpoint.get("/events", tags=["Webhooks"], prefix="/webhooks", response_model=List[str])
async def get_available_events() -> List[str]:
    return list(get_args(WEBHOOK_EVENT))


@endpoint.post("/", tags=["Webhooks"], prefix="/webhooks", response_model=WebhookResponse)
async def register_webhook(
    webhook: WebhookPayload,
    info: AuthorizedInfo = check_permissions(AuthResource.SYSTEM, AuthPermission.WRITE),
) -> WebhookResponse:
    global crypto

    agent_id = parse_agent_key(info, webhook)

    settings = webhook.model_dump(exclude={"event"}) | {"secret": crypto.encrypt(webhook.secret)}
    stored_webhook = crud_webhook.set_webhook(agent_id, webhook.event, settings)
    return WebhookResponse(
        url=stored_webhook["url"],
        event=webhook.event,
        header_key=stored_webhook.get("header_key"),
    )


@endpoint.delete("/", tags=["Webhooks"], prefix="/webhooks")
async def delete_webhook(
    webhook: WebhookPayload,
    info: AuthorizedInfo = check_permissions(AuthResource.SYSTEM, AuthPermission.DELETE),
) -> None:
    global crypto

    agent_id = parse_agent_key(info, webhook)

    secret = crypto.encrypt(webhook.secret)
    crud_webhook.delete_webhook(agent_id, webhook.event, webhook.url, secret)


@hook(priority=0)
def after_rabbithole_stored_documents(source, stored_points: List[PointStruct], cat) -> None:
    webhooks = crud_webhook.get_webhooks(cat.agent_key, "knowledge_source_loaded")
    if webhooks is None:
        return

    remote_dir = cat.agent_key + (f"/{cat.id}" if isinstance(cat, StrayCat) else "")
    file_exists = (
        cat.file_manager.file_exists(source, remote_dir)
        if not is_url(source)
        else True
    )

    payload = {
        "agent": cat.agent_key,
        "chat": cat.id if isinstance(cat, StrayCat) else None,
        "source": source,
        "points": [point.payload.get("metadata") for point in stored_points],
        "success": file_exists,
    }

    for webhook in webhooks:
        try:
            trigger_webhook(WebhookPayload(**webhook), payload)
            log.info(f"Triggered the webhook '{webhook['url']}' for the agent '{cat.agent_key}' on knowledge source loaded")
        except Exception as e:
            log.error(f"Failed to trigger the webhook '{webhook['url']}' for the agent '{cat.agent_key}' on knowledge source loaded: {e}")


@hook(priority=0)
def lizard_notify_plugin_installation(plugin_id: str, plugin_path: str, lizard) -> None:
    webhooks = crud_webhook.get_webhooks(lizard.agent_key, "plugin_installed")
    if webhooks is None:
        return

    success = os.path.exists(os.path.join(get_plugins_path(), plugin_id))
    payload = {"plugin_id": plugin_id, "success": success}

    for webhook in webhooks:
        try:
            trigger_webhook(WebhookPayload(**webhook), payload)
            log.info(f"Triggered the webhook '{webhook['url']}' on plugin installation")
        except Exception as e:
            log.error(f"Failed to trigger the webhook '{webhook['url']}' on plugin installation: {e}")


@hook(priority=0)
def lizard_notify_plugin_uninstallation(plugin_id: str, lizard) -> None:
    webhooks = crud_webhook.get_webhooks(lizard.agent_key, "plugin_uninstalled")
    if webhooks is None:
        return

    success = os.path.exists(os.path.join(get_plugins_path(), plugin_id))
    payload = {"plugin_id": plugin_id, "success": not success}

    for webhook in webhooks:
        try:
            trigger_webhook(WebhookPayload(**webhook), payload)
            log.info(f"Triggered webhook {webhook['url']} on plugin uninstallation")
        except Exception as e:
            log.error(f"Failed to trigger the webhook '{webhook['url']}' on plugin uninstallation: {e}")
