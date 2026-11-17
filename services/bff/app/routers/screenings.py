from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.domain.interfaces import ScreeningService
from app.domain.screening import (
    AnswerReceipt,
    ScreeningResult,
    ScreeningSession,
    StartScreeningRequest,
    SubmitAnswerRequest,
)
from app.routers.dependencies import get_screening_service

router = APIRouter(prefix="/screenings", tags=["screenings"])
Service = Annotated[ScreeningService, Depends(get_screening_service)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ScreeningSession)
async def start_screening(request: StartScreeningRequest, service: Service) -> ScreeningSession:
    """Start a screening (currently a stateless mock session)."""
    session = await service.start(request.survey_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Survey not found")
    return session


@router.post("/{screening_id}/answers", response_model=AnswerReceipt)
async def submit_answer(
    screening_id: UUID, request: SubmitAnswerRequest, service: Service,
) -> AnswerReceipt:
    """Acknowledge an answer; the mock does not store or evaluate it."""
    receipt = await service.submit_answer(screening_id, request)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Screening not found")
    return receipt


@router.get("/{screening_id}/results", response_model=ScreeningResult)
async def get_results(screening_id: UUID, service: Service) -> ScreeningResult:
    """Return a fixed mock result, independent of submitted answers."""
    result = await service.get_results(screening_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Screening not found")
    return result


@router.get(
    "/{screening_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {
        "schema": {"type": "string", "format": "binary"},
    }}}},
)
async def download_pdf(screening_id: UUID, service: Service) -> Response:
    """Download a static placeholder PDF, not a generated clinical report."""
    pdf = await service.get_pdf(screening_id)
    if pdf is None:
        raise HTTPException(status_code=404, detail="Screening not found")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="screening-{screening_id}.pdf"'},
    )
