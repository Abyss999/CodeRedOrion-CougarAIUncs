import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Index, text
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.sql import func

from .extensions import db

CATEGORIES = (
    "produce_leafy", "produce_hardy", "dairy", "meat", "seafood", "bakery",
    "eggs", "leftovers", "pantry_dry", "frozen", "other",
)
STORAGES = ("fridge", "pantry", "freezer")
SOURCES = ("photo", "single_photo", "text", "barcode", "receipt", "manual")
EXPIRY_SOURCES = ("default", "gemini", "user")
OUTCOMES = ("used", "donated", "thrown_out")
WASTE_REASONS = ("expired", "didnt_like", "forgot", "other")


def utcnow():
    return datetime.now(timezone.utc)


def _uuid_pk():
    return db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                     server_default=text("gen_random_uuid()"))


class User(db.Model):
    __tablename__ = "users"
    id = _uuid_pk()
    email = db.Column(CITEXT, nullable=False, unique=True)
    password_hash = db.Column(db.Text, nullable=False)
    display_name = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())


class Item(db.Model):
    __tablename__ = "items"
    id = _uuid_pk()
    owner_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    group_id = db.Column(UUID(as_uuid=True), nullable=True)  # FK to groups added in the social wave
    name = db.Column(db.Text, nullable=False)
    category = db.Column(db.Text, nullable=False)
    storage = db.Column(db.Text, nullable=False)
    quantity = db.Column(db.Numeric, nullable=False, default=1)
    unit = db.Column(db.Text, nullable=False, default="piece")
    est_weight_kg = db.Column(db.Numeric, nullable=True)
    est_price = db.Column(db.Numeric(10, 2), nullable=True)
    source = db.Column(db.Text, nullable=False)
    added_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    predicted_expiry = db.Column(db.Date, nullable=False)
    expiry_source = db.Column(db.Text, nullable=False, default="default")
    removed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    outcome = db.Column(db.Text, nullable=True)
    waste_reason = db.Column(db.Text, nullable=True)
    removed_after_expiry = db.Column(db.Boolean, nullable=True)

    __table_args__ = (
        CheckConstraint("(removed_at IS NULL) = (outcome IS NULL)", name="ck_items_removed_iff_outcome"),
        CheckConstraint("(outcome = 'thrown_out') = (waste_reason IS NOT NULL)",
                        name="ck_items_reason_iff_thrown_out"),
        Index("ix_items_owner_removed_expiry", "owner_id", "removed_at", "predicted_expiry"),
    )


class ShareListing(db.Model):
    __tablename__ = "share_listings"
    id = _uuid_pk()
    item_id = db.Column(UUID(as_uuid=True), db.ForeignKey("items.id"), nullable=False, index=True)
    owner_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    group_id = db.Column(UUID(as_uuid=True), nullable=True)
    status = db.Column(db.Text, nullable=False, default="open")
    recipient_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    fulfilled_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('open','fulfilled','cancelled')", name="ck_share_status"),
    )


class FoodEvent(db.Model):
    """Append-only; a TimescaleDB hypertable on `time` (PK must include the partition column)."""
    __tablename__ = "food_events"
    id = _uuid_pk()
    time = db.Column(db.DateTime(timezone=True), primary_key=True, nullable=False,
                     default=utcnow, server_default=func.now())
    user_id = db.Column(UUID(as_uuid=True), nullable=False)
    item_id = db.Column(UUID(as_uuid=True), nullable=False)
    group_id = db.Column(UUID(as_uuid=True), nullable=True)
    event_type = db.Column(db.Text, nullable=False)
    category = db.Column(db.Text, nullable=False)
    quantity = db.Column(db.Numeric, nullable=True)
    est_weight_kg = db.Column(db.Numeric, nullable=True)
    est_price = db.Column(db.Numeric(10, 2), nullable=True)
    outcome = db.Column(db.Text, nullable=True)
    waste_reason = db.Column(db.Text, nullable=True)
    co2e_kg = db.Column(db.Numeric, nullable=True)

    __table_args__ = (
        Index("ix_food_events_user_time", "user_id", text("time DESC")),
        CheckConstraint("event_type IN ('add','share','expiry_warning','remove')",
                        name="ck_food_events_type"),
        CheckConstraint("(outcome = 'thrown_out') = (waste_reason IS NOT NULL)",
                        name="ck_food_events_reason_iff_thrown_out"),
    )
