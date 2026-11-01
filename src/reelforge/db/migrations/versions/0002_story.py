"""story stage: story_changes, story_versions.created_at, jobs.result

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("result", sa.JSON(), nullable=True))
    op.add_column("story_versions", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE story_versions SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
    with op.batch_alter_table("story_versions") as batch:
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        batch.create_unique_constraint("uq_story_versions_project_version", ["project_id", "version"])
    op.create_table(
        "story_changes",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("project_id", sa.String(length=26), nullable=False),
        sa.Column("story_version_id", sa.String(length=26), nullable=False),
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("kinds", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["story_version_id"], ["story_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_story_changes_owner",
        "story_changes",
        ["project_id", "owner_type", "owner_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_story_changes_owner", table_name="story_changes")
    op.drop_table("story_changes")
    with op.batch_alter_table("story_versions") as batch:
        batch.drop_constraint("uq_story_versions_project_version", type_="unique")
        batch.drop_column("created_at")
    op.drop_column("jobs", "result")
