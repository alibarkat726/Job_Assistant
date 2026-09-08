from fastapi import (
    APIRouter,
    Depends,
    File,
    UploadFile,
    Response,
    status,
    Request,
)
from fastapi.responses import Response as RawResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.session import get_db
from app.shared.middleware.rate_limiter import limiter
from app.users.models import User
from app.auth.dependencies import get_current_user
from app.cv.repository import CVRepository
from app.cv.services import CVIntakeService
from app.cv.schemas import (
    CVResponse,
    CVUploadResponse,
    CVUpdateRequest,
)

router = APIRouter(prefix="/api/v1/cvs", tags=["CV Intake"])


async def get_cv_service(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CVIntakeService:
    """Dependency injection providing a tenant-scoped CVIntakeService."""
    repo = CVRepository(db=db, tenant_id=current_user.id)
    return CVIntakeService(cv_repo=repo)


@router.post("/upload", response_model=CVUploadResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def upload_cv(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    cv_service: CVIntakeService = Depends(get_cv_service),
):
    """
    Upload raw CV file (PDF, DOCX, or plain text).
    Sniffs format, extracts text, runs Intake Agent, and saves unfinalized draft for user review.
    """
    contents = await file.read()
    filename = file.filename or "cv_upload"
    return await cv_service.upload_and_parse_cv(
        user_id=current_user.id,
        filename=filename,
        file_bytes=contents,
    )


@router.get("/me", response_model=CVResponse)
async def get_my_cv(
    current_user: User = Depends(get_current_user),
    cv_service: CVIntakeService = Depends(get_cv_service),
):
    """Fetch current authenticated user's active canonical or draft CV."""
    return await cv_service.get_current_user_cv(current_user.id)


@router.put("/draft", response_model=CVResponse)
async def update_cv_draft(
    dto: CVUpdateRequest,
    current_user: User = Depends(get_current_user),
    cv_service: CVIntakeService = Depends(get_cv_service),
):
    """Review and edit parsed structured CV data before or after finalization."""
    return await cv_service.update_cv_draft(current_user.id, dto)


@router.post("/finalize", response_model=CVResponse)
async def finalize_cv(
    current_user: User = Depends(get_current_user),
    cv_service: CVIntakeService = Depends(get_cv_service),
):
    """Finalize draft CV into user's canonical profile baseline."""
    return await cv_service.finalize_cv(current_user.id)


@router.get("/raw")
async def download_raw_cv(
    current_user: User = Depends(get_current_user),
    cv_service: CVIntakeService = Depends(get_cv_service),
):
    """Download original raw uploaded CV file (PDF, DOCX, or TXT)."""
    file_bytes, filename, mime_type = await cv_service.download_raw_file(current_user.id)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return RawResponse(content=file_bytes, media_type=mime_type, headers=headers)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_cv(
    current_user: User = Depends(get_current_user),
    cv_service: CVIntakeService = Depends(get_cv_service),
):
    """Delete active CV, raw storage file, and child records, returning user to no-CV state."""
    await cv_service.delete_current_user_cv(current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
