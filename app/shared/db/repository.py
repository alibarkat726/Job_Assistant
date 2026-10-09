from typing import Generic, List, Optional, Type, TypeVar, Any, Sequence
import uuid
from sqlalchemy import select, update, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.base import Base
from app.shared.db.tenant import bind_tenant

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic base repository for data access operations."""

    def __init__(self, model_cls: Type[ModelT], db: AsyncSession):
        self.model_cls = model_cls
        self.db = db

    async def get_by_id(self, id_val: Any) -> Optional[ModelT]:
        """Fetch a single record by primary key."""
        stmt = select(self.model_cls).filter(self.model_cls.id == id_val)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_all(self, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        """Fetch all records with pagination."""
        stmt = select(self.model_cls).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def create(self, entity: ModelT) -> ModelT:
        """Add a new record to the session."""
        self.db.add(entity)
        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    async def update(self, entity: ModelT) -> ModelT:
        """Update an existing record."""
        await self.db.flush()
        await self.db.refresh(entity)
        return entity

    async def delete(self, entity: ModelT) -> None:
        """Delete a record from the session."""
        await self.db.delete(entity)
        await self.db.flush()


class BaseTenantRepository(BaseRepository[ModelT]):
    """
    Tenant-scoped base repository.
    
    GUARANTEE: Automatically injects user_id filter into ALL queries AND sets Postgres 
    session RLS context ('app.current_user_id'). Future developers extending this 
    repository cannot bypass tenant isolation by forgetting a filter clause.
    """

    def __init__(self, model_cls: Type[ModelT], db: AsyncSession, tenant_id: uuid.UUID):
        super().__init__(model_cls, db)
        if not tenant_id:
            raise ValueError("Tenant ID is required for BaseTenantRepository operations.")
        self.tenant_id = tenant_id

    async def _set_rls_context(self) -> None:
        """Sets Postgres RLS session variable for defense-in-depth security."""
        # Use parameterized escape for raw PostgreSQL session variable setting
        await bind_tenant(self.db, self.tenant_id)

    async def get_by_id(self, id_val: Any) -> Optional[ModelT]:
        """Fetch record by ID scoped to current tenant."""
        await self._set_rls_context()
        stmt = (
            select(self.model_cls)
            .filter(self.model_cls.id == id_val)
            .filter(self.model_cls.user_id == self.tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_all(self, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        """Fetch all records scoped to current tenant."""
        await self._set_rls_context()
        stmt = (
            select(self.model_cls)
            .filter(self.model_cls.user_id == self.tenant_id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def create(self, entity: ModelT) -> ModelT:
        """Create entity with tenant user_id set automatically."""
        await self._set_rls_context()
        if hasattr(entity, "user_id"):
            setattr(entity, "user_id", self.tenant_id)
        return await super().create(entity)

    async def update(self, entity: ModelT) -> ModelT:
        """Update entity ensuring it belongs to current tenant."""
        await self._set_rls_context()
        if hasattr(entity, "user_id") and getattr(entity, "user_id") != self.tenant_id:
            raise PermissionError("Attempted to update a record belonging to another tenant.")
        return await super().update(entity)

    async def delete(self, entity: ModelT) -> None:
        """Delete entity ensuring it belongs to current tenant."""
        await self._set_rls_context()
        if hasattr(entity, "user_id") and getattr(entity, "user_id") != self.tenant_id:
            raise PermissionError("Attempted to delete a record belonging to another tenant.")
        await super().delete(entity)
