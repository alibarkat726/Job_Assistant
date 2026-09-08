import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db.session import get_db
from app.users.models import User
from app.auth.dependencies import get_current_user
from app.dashboard.repository import DashboardRepository
from app.dashboard.services import DashboardService
from app.dashboard.schemas import (
    DashboardApplicationListResponse,
    DashboardApplicationDetailResponse,
    SkillGapAnalyticsResponse
)

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


async def get_dashboard_service(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardService:
    repo = DashboardRepository(db=db, tenant_id=current_user.id)
    return DashboardService(repo=repo)


@router.get("/applications", response_model=DashboardApplicationListResponse)
async def list_dashboard_applications(
    status: Optional[str] = Query(None, description="Filter applications by status (e.g. 'draft', 'tailored', 'applied')"),
    svc: DashboardService = Depends(get_dashboard_service)
):
    """List all job applications with their match counts and basic info."""
    return await svc.list_applications(status=status)


@router.get("/applications/{app_id}", response_model=DashboardApplicationDetailResponse)
async def get_dashboard_application_detail(
    app_id: uuid.UUID,
    svc: DashboardService = Depends(get_dashboard_service)
):
    """Fetch the full aggregated detail view for a specific application (JD, Matches, CV, Interview Prep)."""
    return await svc.get_application_detail(app_id)


@router.get("/analytics/skill-gaps", response_model=SkillGapAnalyticsResponse)
async def get_skill_gap_analytics(
    svc: DashboardService = Depends(get_dashboard_service)
):
    """
    Get an aggregated analytics report on skill gaps across all processed JDs.
    Returns the most frequently missing and matched required skills.
    """
    return await svc.get_skill_gap_analytics()
