"""items.nutrition: per-100 g nutrition, JSONB

Revision ID: 0007_items_nutrition
Revises: 0006_request_audiences
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_items_nutrition"
down_revision = "0006_request_audiences"
branch_labels = None
depends_on = None


def upgrade():
    # Nullable, no default: existing items simply have no nutrition. The object shape is validated in
    # the app (services/nutrition.py); the DB only guarantees it is a JSON object, never a scalar.
    op.add_column("items", sa.Column("nutrition", JSONB(none_as_null=True), nullable=True))
    op.create_check_constraint("ck_items_nutrition_object", "items",
                               "nutrition IS NULL OR jsonb_typeof(nutrition) = 'object'")


def downgrade():
    op.drop_constraint("ck_items_nutrition_object", "items", type_="check")
    op.drop_column("items", "nutrition")
