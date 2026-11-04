"""voice stage: voice_slots, library voice columns, line approval and shot-length timestamp

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_slots",
        sa.Column("project_id", sa.String(length=26), nullable=False),
        sa.Column("story_key", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="preset"),
        sa.Column("model", sa.String(length=16), nullable=True),
        sa.Column("voice_id", sa.Text(), nullable=True),
        sa.Column("reference_artifact_id", sa.String(length=26), nullable=True),
        sa.Column("reference_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("speed", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="hi"),
        sa.Column("clip_seconds", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "story_key"),
    )
    op.add_column("voices", sa.Column("reference_text", sa.Text(), nullable=False, server_default=""))
    op.add_column("voices", sa.Column("reference_path", sa.Text(), nullable=True))
    op.add_column("voices", sa.Column("reference_sha256", sa.String(length=64), nullable=True))
    op.add_column("voices", sa.Column("clip_seconds", sa.Float(), nullable=True))
    op.add_column("lines", sa.Column("approved_artifact_id", sa.String(length=26), nullable=True))
    op.add_column("scenes", sa.Column("shot_length_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("scenes") as batch:
        batch.drop_column("shot_length_at")
    with op.batch_alter_table("lines") as batch:
        batch.drop_column("approved_artifact_id")
    with op.batch_alter_table("voices") as batch:
        for col in ("clip_seconds", "reference_sha256", "reference_path", "reference_text"):
            batch.drop_column(col)
    op.drop_table("voice_slots")
