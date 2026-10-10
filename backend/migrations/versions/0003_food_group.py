"""items.food_group: user-facing grouping (protein/veggies/fruit/...) with backfill

Revision ID: 0003_food_group
Revises: 0002_social
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_food_group"
down_revision = "0002_social"
branch_labels = None
depends_on = None

_GROUPS = "'protein','veggies','fruit','dairy','grains','pantry','leftovers','frozen','other'"

# Inlined copy of app.services.food_group.FRUIT_WORDS (migrations must not depend on app code).
_FRUIT = """apple apples apricot apricots avocado avocados banana bananas berry berries blackberry
blackberries blueberry blueberries cantaloupe cherry cherries clementine clementines coconut cranberry
cranberries currant date dates fig figs grape grapes grapefruit guava honeydew kiwi kiwis lemon lemons
lime limes lychee mandarin mandarins mango mangos mangoes melon melons nectarine nectarines orange
oranges papaya passionfruit peach peaches pear pears persimmon pineapple pineapples plum plums
pomegranate pomegranates raspberry raspberries strawberry strawberries tangerine tangerines
watermelon""".split()


def upgrade():
    op.add_column("items", sa.Column("food_group", sa.Text, nullable=True))
    op.create_check_constraint(
        "ck_items_food_group", "items", f"food_group IS NULL OR food_group IN ({_GROUPS})")
    pattern = r"\m(" + "|".join(_FRUIT) + r")\M"
    op.execute(sa.text("""
        UPDATE items SET food_group = CASE
            WHEN category IN ('meat','seafood','eggs') THEN 'protein'
            WHEN category = 'bakery' THEN 'grains'
            WHEN category = 'pantry_dry' THEN 'pantry'
            WHEN category = 'dairy' THEN 'dairy'
            WHEN category = 'leftovers' THEN 'leftovers'
            WHEN category = 'frozen' THEN 'frozen'
            WHEN category IN ('produce_leafy','produce_hardy') THEN
                CASE WHEN lower(name) ~ :pat THEN 'fruit' ELSE 'veggies' END
            ELSE 'other' END
    """).bindparams(pat=pattern))


def downgrade():
    op.drop_constraint("ck_items_food_group", "items", type_="check")
    op.drop_column("items", "food_group")
