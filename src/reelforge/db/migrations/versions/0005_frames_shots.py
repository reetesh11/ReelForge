"""frames and shots stages: frame_slots and shot_slots

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frame_slots",
        sa.Column("project_id", sa.String(length=26), nullable=False),
        sa.Column("story_key", sa.String(length=64), nullable=False),
        sa.Column("framing", sa.String(length=16), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("prompt_source", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("prompt_basis", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("continue_previous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("approved_artifact_id", sa.String(length=26), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "story_key"),
    )
    op.create_table(
        "shot_slots",
        sa.Column("project_id", sa.String(length=26), nullable=False),
        sa.Column("story_key", sa.String(length=64), nullable=False),
        sa.Column("shot_type", sa.String(length=16), nullable=True),
        sa.Column("quality", sa.String(length=8), nullable=True),
        sa.Column("motion_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("prompt_source", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("prompt_basis", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("approved_artifact_id", sa.String(length=26), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "story_key"),
    )


def downgrade() -> None:
    op.drop_table("shot_slots")
    op.drop_table("frame_slots")
