"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('brand_kits',
    sa.Column('id', sa.String(length=26), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('data_dir', sa.Text(), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('settings',
    sa.Column('key', sa.String(length=128), nullable=False),
    sa.Column('value', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('voices',
    sa.Column('id', sa.String(length=26), nullable=False),
    sa.Column('mode', sa.String(length=16), nullable=False),
    sa.Column('model_key', sa.String(length=64), nullable=True),
    sa.Column('voice_ref', sa.Text(), nullable=True),
    sa.Column('reference_artifact_id', sa.String(length=26), nullable=True),
    sa.Column('speed', sa.Float(), nullable=False),
    sa.Column('language', sa.String(length=16), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('characters',
    sa.Column('id', sa.String(length=26), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('aliases', sa.JSON(), nullable=False),
    sa.Column('look_text', sa.Text(), nullable=False),
    sa.Column('master_artifact_id', sa.String(length=26), nullable=True),
    sa.Column('sheet_artifact_ids', sa.JSON(), nullable=False),
    sa.Column('voice_id', sa.String(length=26), nullable=True),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('parent_character_id', sa.String(length=26), nullable=True),
    sa.ForeignKeyConstraint(['parent_character_id'], ['characters.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['voice_id'], ['voices.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('projects',
    sa.Column('id', sa.String(length=26), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('data_dir', sa.Text(), nullable=False),
    sa.Column('stage', sa.String(length=32), server_default='DRAFT', nullable=False),
    sa.Column('brand_kit_id', sa.String(length=26), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['brand_kit_id'], ['brand_kits.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('approvals',
    sa.Column('id', sa.String(length=26), nullable=False),
    sa.Column('project_id', sa.String(length=26), nullable=False),
    sa.Column('stage', sa.String(length=32), nullable=False),
    sa.Column('owner_type', sa.String(length=32), nullable=True),
    sa.Column('owner_id', sa.String(length=64), nullable=True),
    sa.Column('artifact_id', sa.String(length=26), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('artifacts',
    sa.Column('id', sa.String(length=26), nullable=False),
    sa.Column('project_id', sa.String(length=26), nullable=False),
    sa.Column('owner_type', sa.String(length=32), nullable=False),
    sa.Column('owner_id', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('take_no', sa.Integer(), nullable=False),
    sa.Column('path', sa.Text(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('inputs_fp', sa.String(length=64), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('version', sa.String(length=64), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('model_key', sa.String(length=64), nullable=False),
    sa.Column('seed', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('duration_s', sa.Float(), nullable=True),
    sa.Column('width', sa.Integer(), nullable=True),
    sa.Column('height', sa.Integer(), nullable=True),
    sa.Column('created_by_job', sa.String(length=26), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_artifacts_inputs_fp', 'artifacts', ['inputs_fp'], unique=False)
    op.create_index('ix_artifacts_owner_active', 'artifacts', ['project_id', 'owner_type', 'owner_id', 'kind', 'is_active'], unique=False)
    op.create_table('jobs',
    sa.Column('id', sa.String(length=26), nullable=False),
    sa.Column('project_id', sa.String(length=26), nullable=True),
    sa.Column('type', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('heavy', sa.Boolean(), nullable=False),
    sa.Column('mem_need_gb', sa.Float(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('progress', sa.Integer(), server_default='0', nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('pid', sa.Integer(), nullable=True),
    sa.Column('command', sa.JSON(), nullable=True),
    sa.Column('log_path', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('peak_rss_mb', sa.Float(), nullable=True),
    sa.Column('exit_code', sa.Integer(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_jobs_queue', 'jobs', ['status', 'priority', 'created_at'], unique=False)
    op.create_table('project_characters',
    sa.Column('project_id', sa.String(length=26), nullable=False),
    sa.Column('story_key', sa.String(length=64), nullable=False),
    sa.Column('character_id', sa.String(length=26), nullable=False),
    sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('project_id', 'story_key')
    )
    op.create_table('reel_versions',
    sa.Column('id', sa.String(length=26), nullable=False),
    sa.Column('project_id', sa.String(length=26), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('edl_artifact_id', sa.String(length=26), nullable=True),
    sa.Column('final_artifact_id', sa.String(length=26), nullable=True),
    sa.Column('credits', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('scenes',
    sa.Column('id', sa.String(length=26), nullable=False),
    sa.Column('project_id', sa.String(length=26), nullable=False),
    sa.Column('story_key', sa.String(length=64), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('shot_type', sa.String(length=32), nullable=False),
    sa.Column('duration_s', sa.Float(), nullable=False),
    sa.Column('frames', sa.Integer(), nullable=True),
    sa.Column('continue_from', sa.String(length=64), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('story_versions',
    sa.Column('id', sa.String(length=26), nullable=False),
    sa.Column('project_id', sa.String(length=26), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('yaml_text', sa.Text(), nullable=False),
    sa.Column('is_current', sa.Boolean(), nullable=False),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('artifact_inputs',
    sa.Column('artifact_id', sa.String(length=26), nullable=False),
    sa.Column('input_artifact_id', sa.String(length=26), nullable=False),
    sa.ForeignKeyConstraint(['artifact_id'], ['artifacts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['input_artifact_id'], ['artifacts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('artifact_id', 'input_artifact_id')
    )
    op.create_table('lines',
    sa.Column('id', sa.String(length=26), nullable=False),
    sa.Column('scene_id', sa.String(length=26), nullable=False),
    sa.Column('character_id', sa.String(length=26), nullable=True),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('language', sa.String(length=16), nullable=False),
    sa.Column('speed', sa.Float(), nullable=False),
    sa.Column('pause_before', sa.Float(), nullable=False),
    sa.Column('pause_after', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_index('ix_artifacts_inputs_fp', table_name='artifacts')
    op.drop_index('ix_artifacts_owner_active', table_name='artifacts')
    op.drop_index('ix_jobs_queue', table_name='jobs')
    op.drop_table('lines')
    op.drop_table('artifact_inputs')
    op.drop_table('story_versions')
    op.drop_table('scenes')
    op.drop_table('reel_versions')
    op.drop_table('project_characters')
    op.drop_table('jobs')
    op.drop_table('artifacts')
    op.drop_table('approvals')
    op.drop_table('projects')
    op.drop_table('characters')
    op.drop_table('voices')
    op.drop_table('settings')
    op.drop_table('brand_kits')
