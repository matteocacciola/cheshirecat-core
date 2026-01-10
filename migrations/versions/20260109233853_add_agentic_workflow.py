"""add agentic workflow

Revision ID: 20260109233853
Revises: None
Create Date: 2026-01-09 23:38:53

"""
from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import uuid4

from migrations.env import MigrationContext
from cat.db import crud

# revision identifiers, used by the migration system
revision: str = '20260109233853'
down_revision: Union[str, Sequence[str], None] = None


def upgrade(context: MigrationContext) -> None:
    """Apply migration"""
    for agent_id in crud.get_agents_main_keys():
        settings = context.get_json(f"agent:{agent_id}")
        if settings is None:
            settings = []

        # Check if 'agentic_workflow' config already exists
        if any(s.get("category") == "agentic_workflow" for s in settings):
            continue

        # Add new configuration
        new_config = {
            "name": "CoreAgenticWorkflowConfig",
            "value": {},
            "category": "agentic_workflow",
            "setting_id": str(uuid4()),
            "updated_at": datetime.now(timezone.utc).timestamp(),
        }
        settings.append(new_config)
        context.set_json(f"agent:{agent_id}", settings)


def downgrade(context: MigrationContext) -> None:
    """Revert migration"""
    pass
