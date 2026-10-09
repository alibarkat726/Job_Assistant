"""Transaction-local tenant context, including transactions opened after commit."""
import uuid

from sqlalchemy import event, text
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession


@event.listens_for(Session, "after_begin")
def restore_tenant_context(session, transaction, connection):
    tenant = session.info.get("tenant_id")
    if tenant and connection.dialect.name == "postgresql":
        connection.execute(
            text("SELECT set_config('app.current_user_id', :tenant, true)"),
            {"tenant": str(tenant)},
        )


async def bind_tenant(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    tenant_id = uuid.UUID(str(tenant_id))
    previous = db.info.get("tenant_id")
    if previous is not None and previous != tenant_id:
        raise PermissionError("A database session cannot switch tenants.")
    db.info["tenant_id"] = tenant_id
    # Authentication may already have started a transaction without context.
    await db.execute(
        text("SELECT set_config('app.current_user_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )
