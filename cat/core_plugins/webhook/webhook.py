import hashlib
import hmac
import json
from typing import Literal, List, get_args

import requests
from pydantic import BaseModel, Field
from cat import endpoint
import cat.core_plugins.webhook.crud as crud_webhook
from cat.services.string_crypto import StringCrypto

WEBHOOK_EVENT = Literal["knowledge_source_loaded", "plugin_installed", "plugin_uninstalled"]


crypto = StringCrypto()


class WebhookResponse(BaseModel):
    agent_id: str
    url: str
    event: WEBHOOK_EVENT
    header_key: str | None = Field(default="X-CheshireCat-Signature")


class WebhookPayload(WebhookResponse):
    secret: str


def trigger_webhook(webhook_data: WebhookPayload, payload):
    target_url = webhook_data.url
    custom_header_key = webhook_data.header_key

    secret = crypto.decrypt(webhook_data.secret)
    body_bytes = json.dumps(payload, separators=(',', ':')).encode("utf-8")

    signature = hmac.new(
        secret.encode("utf-8"),
        msg=body_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()

    headers = {"Content-Type": "application/json", custom_header_key: signature}
    requests.post(target_url, data=body_bytes, headers=headers)


@endpoint.get("/events", tags=["Webhooks"], prefix="/webhooks", response_model=List[str])
async def get_available_events() -> List[str]:
    return list(get_args(WEBHOOK_EVENT))


@endpoint.post("/", tags=["Webhooks"], prefix="/webhooks", response_model=WebhookResponse)
async def register_webhook(webhook: WebhookPayload) -> WebhookResponse:
    global crypto

    settings = webhook.model_dump(exclude={"agent_id", "event"}) | {"secret": crypto.encrypt(webhook.secret)}
    stored_webhook = crud_webhook.set_webhook(webhook.agent_id, webhook.event, settings)
    return WebhookResponse(
        agent_id=webhook.agent_id,
        url=stored_webhook["url"],
        event=webhook.event,
        header_key=stored_webhook.get("header_key"),
    )


@endpoint.delete("/", tags=["Webhooks"], prefix="/webhooks")
async def delete_webhook(webhook: WebhookPayload) -> None:
    secret = crypto.encrypt(webhook.secret)

    crud_webhook.delete_webhook(webhook.agent_id, webhook.event, webhook.url, secret)
