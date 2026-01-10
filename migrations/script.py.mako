"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision}
Create Date: ${create_date}

"""
from typing import Sequence, Union

import time
from migrations.env import MigrationContext

# revision identifiers, used by the migration system
revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}


def upgrade(context: MigrationContext) -> None:
    """Apply migration"""
    pass


def downgrade(context: MigrationContext) -> None:
    """Revert migration"""
    pass