"""request_audiences: one request, many audiences (friends and/or groups); drop requests.group_id

Revision ID: 0006_request_audiences
Revises: 0005_user_identities

Backfill: every existing request gets exactly one audience row: `friends` when its group_id was
null, otherwise `group` with that group_id. requests.group_id is then DROPPED, so the audience
table is the only source of truth (a kept-but-unused column would go stale the first time a
request is posted to two audiences, and code reading it would silently get the wrong scope).

Downgrade is lossy for requests posted to several audiences, since the old model holds one scope:
group_id comes back as the request's first group audience (oldest row) when it has NO friends
audience, else null (friends). Single-audience requests round-trip exactly.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0006_request_audiences"
down_revision = "0005_user_identities"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "request_audiences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_id", UUID(as_uuid=True), sa.ForeignKey("requests.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("groups.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('friends','group')", name="ck_request_audiences_kind"),
        sa.CheckConstraint("(kind = 'group') = (group_id IS NOT NULL)",
                           name="ck_request_audiences_group_iff_kind"),
    )
    # At most one friends audience per request, and each group at most once per request.
    op.create_index("uq_request_audiences_friends", "request_audiences", ["request_id"], unique=True,
                    postgresql_where=sa.text("kind = 'friends'"))
    op.create_index("uq_request_audiences_group", "request_audiences", ["request_id", "group_id"],
                    unique=True, postgresql_where=sa.text("kind = 'group'"))
    op.create_index("ix_request_audiences_group_id", "request_audiences", ["group_id"])

    op.execute("""
        INSERT INTO request_audiences (request_id, kind, group_id, created_at)
        SELECT id, CASE WHEN group_id IS NULL THEN 'friends' ELSE 'group' END, group_id, created_at
        FROM requests
    """)

    # Dropping the column also drops its FK and ix_requests_group_id (whatever the FK's generated name).
    op.drop_column("requests", "group_id")


def downgrade():
    op.add_column("requests", sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("groups.id"),
                                        nullable=True))
    op.create_index("ix_requests_group_id", "requests", ["group_id"])
    op.execute("""
        UPDATE requests r SET group_id = (
            SELECT ra.group_id FROM request_audiences ra
            WHERE ra.request_id = r.id AND ra.kind = 'group'
            ORDER BY ra.created_at, ra.id LIMIT 1)
        WHERE NOT EXISTS (SELECT 1 FROM request_audiences f
                          WHERE f.request_id = r.id AND f.kind = 'friends')
    """)
    op.drop_index("ix_request_audiences_group_id", table_name="request_audiences")
    op.drop_index("uq_request_audiences_group", table_name="request_audiences")
    op.drop_index("uq_request_audiences_friends", table_name="request_audiences")
    op.drop_table("request_audiences")
