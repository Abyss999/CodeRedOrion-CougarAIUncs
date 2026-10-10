"""users, items, share_listings, food_events hypertable

Revision ID: 0001_initial
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT, UUID

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

_UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT),
        sa.Column("email", CITEXT, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("group_id", UUID(as_uuid=True), nullable=True),  # FK to groups: social wave
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("storage", sa.Text, nullable=False),
        sa.Column("quantity", sa.Numeric, nullable=False, server_default="1"),
        sa.Column("unit", sa.Text, nullable=False, server_default="piece"),
        sa.Column("est_weight_kg", sa.Numeric, nullable=True),
        sa.Column("est_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("predicted_expiry", sa.Date, nullable=False),
        sa.Column("expiry_source", sa.Text, nullable=False, server_default="default"),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.Text, nullable=True),
        sa.Column("waste_reason", sa.Text, nullable=True),
        sa.Column("removed_after_expiry", sa.Boolean, nullable=True),
        sa.CheckConstraint("(removed_at IS NULL) = (outcome IS NULL)", name="ck_items_removed_iff_outcome"),
        sa.CheckConstraint("(outcome = 'thrown_out') = (waste_reason IS NOT NULL)",
                           name="ck_items_reason_iff_thrown_out"),
        sa.CheckConstraint("storage IN ('fridge','pantry','freezer')", name="ck_items_storage"),
        sa.CheckConstraint("outcome IS NULL OR outcome IN ('used','donated','thrown_out')",
                           name="ck_items_outcome"),
        sa.CheckConstraint("waste_reason IS NULL OR waste_reason IN ('expired','didnt_like','forgot','other')",
                           name="ck_items_waste_reason"),
    )
    op.create_index("ix_items_owner_removed_expiry", "items", ["owner_id", "removed_at", "predicted_expiry"])

    op.create_table(
        "share_listings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT),
        sa.Column("item_id", UUID(as_uuid=True), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("group_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("recipient_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('open','fulfilled','cancelled')", name="ck_share_status"),
    )
    op.create_index("ix_share_listings_item_id", "share_listings", ["item_id"])

    # Hypertable: every unique index/PK must include the partition column, so PK = (id, time).
    op.create_table(
        "food_events",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=_UUID_DEFAULT),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("quantity", sa.Numeric, nullable=True),
        sa.Column("est_weight_kg", sa.Numeric, nullable=True),
        sa.Column("est_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("outcome", sa.Text, nullable=True),
        sa.Column("waste_reason", sa.Text, nullable=True),
        sa.Column("co2e_kg", sa.Numeric, nullable=True),
        sa.PrimaryKeyConstraint("id", "time", name="pk_food_events"),
        sa.CheckConstraint("event_type IN ('add','share','expiry_warning','remove')",
                           name="ck_food_events_type"),
        sa.CheckConstraint("(outcome = 'thrown_out') = (waste_reason IS NOT NULL)",
                           name="ck_food_events_reason_iff_thrown_out"),
    )
    op.execute("SELECT create_hypertable('food_events', by_range('time'))")
    op.execute("CREATE INDEX ix_food_events_user_time ON food_events (user_id, time DESC)")


def downgrade():
    op.drop_table("food_events")
    op.drop_table("share_listings")
    op.drop_table("items")
    op.drop_table("users")
