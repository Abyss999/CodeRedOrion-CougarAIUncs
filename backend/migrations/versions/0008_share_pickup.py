"""share_listings pickup spot (note, lat/lng, place name) + friend_codes

Revision ID: 0008_share_pickup
Revises: 0007_items_nutrition
"""
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql  # noqa: F401
from alembic import op

revision = "0008_share_pickup"
down_revision = "0007_items_nutrition"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "friend_codes",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_friend_codes_user_id", "friend_codes", ["user_id"])
    op.create_index("ix_friend_codes_expires_at", "friend_codes", ["expires_at"])
    # All nullable: existing listings simply have no pickup spot. Shape is validated in the app too.
    op.add_column("share_listings", sa.Column("pickup_note", sa.Text(), nullable=True))
    op.add_column("share_listings", sa.Column("pickup_lat", sa.Float(), nullable=True))
    op.add_column("share_listings", sa.Column("pickup_lng", sa.Float(), nullable=True))
    op.add_column("share_listings", sa.Column("pickup_place", sa.Text(), nullable=True))
    op.create_check_constraint("ck_share_pickup_latlng", "share_listings",
                               "(pickup_lat IS NULL) = (pickup_lng IS NULL)")
    op.create_check_constraint("ck_share_pickup_range", "share_listings",
                               "pickup_lat IS NULL OR (pickup_lat BETWEEN -90 AND 90 "
                               "AND pickup_lng BETWEEN -180 AND 180)")
    op.create_check_constraint("ck_share_pickup_note_len", "share_listings",
                               "pickup_note IS NULL OR char_length(pickup_note) <= 120")
    op.create_check_constraint("ck_share_pickup_place_len", "share_listings",
                               "pickup_place IS NULL OR char_length(pickup_place) <= 120")


def downgrade():
    op.drop_table("friend_codes")
    for name in ("ck_share_pickup_place_len", "ck_share_pickup_note_len",
                 "ck_share_pickup_range", "ck_share_pickup_latlng"):
        op.drop_constraint(name, "share_listings", type_="check")
    for col in ("pickup_place", "pickup_lng", "pickup_lat", "pickup_note"):
        op.drop_column("share_listings", col)
