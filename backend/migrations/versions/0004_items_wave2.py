"""items.freshness / freshness_checked_at / confidence; groups.created_by nullable (account deletion)

Revision ID: 0004_items_wave2
Revises: 0003_food_group
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0004_items_wave2"
down_revision = "0003_food_group"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("items", sa.Column("freshness", sa.Text, nullable=True))
    op.add_column("items", sa.Column("freshness_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("items", sa.Column("confidence", sa.Float, nullable=True))
    op.create_check_constraint("ck_items_freshness", "items",
                               "freshness IS NULL OR freshness IN ('fresh','semi_fresh','spoiled')")
    op.create_check_constraint("ck_items_freshness_checked_iff_freshness", "items",
                               "(freshness IS NULL) = (freshness_checked_at IS NULL)")
    op.create_check_constraint("ck_items_confidence", "items",
                               "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)")
    # DELETE /auth/me nulls the creator of groups that outlive the deleted user.
    op.alter_column("groups", "created_by", existing_type=UUID(as_uuid=True),
                    nullable=True)


def downgrade():
    # Lossy for orphan groups: give them to their longest-standing member; a group with no members is
    # detached from its rows and deleted (it was already unreachable).
    op.execute("""
        UPDATE groups SET created_by = (
            SELECT user_id FROM group_members m WHERE m.group_id = groups.id ORDER BY joined_at LIMIT 1)
        WHERE created_by IS NULL""")
    op.execute("UPDATE items SET group_id = NULL WHERE group_id IN (SELECT id FROM groups WHERE created_by IS NULL)")
    op.execute("UPDATE share_listings SET group_id = NULL WHERE group_id IN (SELECT id FROM groups WHERE created_by IS NULL)")
    op.execute("UPDATE requests SET group_id = NULL WHERE group_id IN (SELECT id FROM groups WHERE created_by IS NULL)")
    op.execute("DELETE FROM group_members WHERE group_id IN (SELECT id FROM groups WHERE created_by IS NULL)")
    op.execute("DELETE FROM groups WHERE created_by IS NULL")
    op.alter_column("groups", "created_by", existing_type=UUID(as_uuid=True),
                    nullable=False)
    op.drop_constraint("ck_items_confidence", "items", type_="check")
    op.drop_constraint("ck_items_freshness_checked_iff_freshness", "items", type_="check")
    op.drop_constraint("ck_items_freshness", "items", type_="check")
    op.drop_column("items", "confidence")
    op.drop_column("items", "freshness_checked_at")
    op.drop_column("items", "freshness")
