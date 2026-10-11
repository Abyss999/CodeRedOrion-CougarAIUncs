"""user_identities (OAuth sign-in, Google first); users.password_hash nullable

Revision ID: 0005_user_identities
Revises: 0004_items_wave2
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT, UUID

revision = "0005_user_identities"
down_revision = "0004_items_wave2"
branch_labels = None
depends_on = None

# An unusable werkzeug hash: check_password_hash() returns False for it (no "$" separator).
_NO_PASSWORD = "!"


def upgrade():
    op.create_table(
        "user_identities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("email", CITEXT, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "subject", name="uq_user_identities_provider_subject"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])
    op.alter_column("users", "password_hash", existing_type=sa.Text, nullable=True)


def downgrade():
    # OAuth-only users keep their rows but get an unusable password (email login keeps failing with 401).
    op.execute(f"UPDATE users SET password_hash = '{_NO_PASSWORD}' WHERE password_hash IS NULL")
    op.alter_column("users", "password_hash", existing_type=sa.Text, nullable=False)
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
