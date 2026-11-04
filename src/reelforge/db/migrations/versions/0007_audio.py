"""sound cues: audio_slots

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audio_slots",
        sa.Column("project_id", sa.String(length=26), nullable=False),
        sa.Column("cue_id", sa.String(length=64), nullable=False),
        sa.Column("picked_artifact_id", sa.String(length=26), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "cue_id"),
    )


def downgrade() -> None:
    op.drop_table("audio_slots")
