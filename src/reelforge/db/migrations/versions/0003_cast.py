"""cast stage: character library columns and cast_slots

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("seed", sa.Integer(), nullable=True))
    op.add_column("characters", sa.Column("model_key", sa.String(length=64), nullable=True))
    op.add_column("characters", sa.Column("model_id", sa.Text(), nullable=True))
    op.add_column(
        "characters", sa.Column("license", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "characters", sa.Column("license_url", sa.Text(), nullable=False, server_default="")
    )
    op.add_column("characters", sa.Column("master_path", sa.Text(), nullable=True))
    op.add_column("characters", sa.Column("master_sha256", sa.String(length=64), nullable=True))
    op.add_column(
        "characters", sa.Column("voice_reference", sa.Text(), nullable=False, server_default="")
    )
    op.add_column("characters", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE characters SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
    with op.batch_alter_table("characters") as batch:
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
    op.create_table(
        "cast_slots",
        sa.Column("project_id", sa.String(length=26), nullable=False),
        sa.Column("story_key", sa.String(length=64), nullable=False),
        sa.Column("bible_line", sa.Text(), nullable=False, server_default=""),
        sa.Column("bible_source", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("look_source", sa.Text(), nullable=False, server_default=""),
        sa.Column("base_seed", sa.Integer(), nullable=True),
        sa.Column("next_seed", sa.Integer(), nullable=True),
        sa.Column("candidate_ids", sa.JSON(), nullable=False),
        sa.Column("approved_artifact_id", sa.String(length=26), nullable=True),
        sa.Column("approved_candidate_id", sa.String(length=26), nullable=True),
        sa.Column("origin", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("variant_of_id", sa.String(length=26), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("voice_reference", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "story_key"),
    )


def downgrade() -> None:
    op.drop_table("cast_slots")
    with op.batch_alter_table("characters") as batch:
        for col in (
            "created_at",
            "voice_reference",
            "master_sha256",
            "master_path",
            "license_url",
            "license",
            "model_id",
            "model_key",
            "seed",
        ):
            batch.drop_column(col)
