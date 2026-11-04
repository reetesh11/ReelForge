"""per-emotion reference clips for cloned voices: voice_emotion_clips

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_emotion_clips",
        sa.Column("project_id", sa.String(length=26), nullable=False),
        sa.Column("story_key", sa.String(length=64), nullable=False),
        sa.Column("emotion", sa.String(length=16), nullable=False),
        sa.Column("artifact_id", sa.String(length=26), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False, server_default=""),
        sa.Column("clip_seconds", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "story_key", "emotion"),
    )


def downgrade() -> None:
    op.drop_table("voice_emotion_clips")
