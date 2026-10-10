"""social: friendships, groups, group_members, requests; group FKs; share claims

Revision ID: 0002_social
Revises: 0001_initial
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0002_social"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade():
    op.create_table(
        "friendships",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("friend_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "friend_id", name="pk_friendships"),
        sa.CheckConstraint("status IN ('pending','accepted')", name="ck_friendships_status"),
        sa.CheckConstraint("user_id <> friend_id", name="ck_friendships_not_self"),
    )
    # One relationship per unordered pair: (a,b) and (b,a) cannot both exist.
    op.execute("CREATE UNIQUE INDEX uq_friendships_pair ON friendships "
               "(LEAST(user_id, friend_id), GREATEST(user_id, friend_id))")
    op.create_index("ix_friendships_friend_id", "friendships", ["friend_id"])

    op.create_table(
        "groups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("invite_code", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "group_members",
        sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.Text, nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("group_id", "user_id", name="pk_group_members"),
        sa.CheckConstraint("role IN ('owner','member')", name="ck_group_members_role"),
    )
    op.create_index("ix_group_members_user_id", "group_members", ["user_id"])

    op.create_table(
        "requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("groups.id"), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("fulfilled_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('open','fulfilled','cancelled')", name="ck_requests_status"),
        sa.CheckConstraint("char_length(text) BETWEEN 1 AND 280", name="ck_requests_text_len"),
        sa.CheckConstraint("(status = 'fulfilled') = (fulfilled_by IS NOT NULL)",
                           name="ck_requests_fulfilled_iff_by"),
    )
    op.create_index("ix_requests_status_created", "requests", ["status", sa.text("created_at DESC")])
    op.create_index("ix_requests_author_id", "requests", ["author_id"])
    op.create_index("ix_requests_group_id", "requests", ["group_id"])

    # Wave 1 left these as plain uuids until `groups` existed.
    op.create_foreign_key("fk_items_group_id", "items", "groups", ["group_id"], ["id"])
    op.create_foreign_key("fk_share_listings_group_id", "share_listings", "groups", ["group_id"], ["id"])
    op.create_index("ix_items_group_removed", "items", ["group_id", "removed_at"])
    op.add_column("share_listings",
                  sa.Column("claimed_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
    op.create_index("ix_share_listings_status_group", "share_listings", ["status", "group_id"])


def downgrade():
    op.drop_index("ix_share_listings_status_group", table_name="share_listings")
    op.drop_column("share_listings", "claimed_by")
    op.drop_index("ix_items_group_removed", table_name="items")
    op.drop_constraint("fk_share_listings_group_id", "share_listings", type_="foreignkey")
    op.drop_constraint("fk_items_group_id", "items", type_="foreignkey")
    op.drop_table("requests")
    op.drop_table("group_members")
    op.drop_table("groups")
    op.drop_table("friendships")
