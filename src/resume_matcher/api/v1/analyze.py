from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError as PydanticValidationError

from resume_matcher.api.dependencies import get_analysis_service
from resume_matcher.schemas.request import AnalyzeRequest
from resume_matcher.schemas.response import AnalyzeResponse
from resume_matcher.services.analysis_service import AnalysisService
from resume_matcher.services.file_parser_service import extract_text_from_bytes

router = APIRouter()


def _validation_error(exc: PydanticValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=exc.errors())


async def _parse_payload(request: Request) -> AnalyzeRequest:
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("application/json"):
        try:
            return AnalyzeRequest.model_validate(await request.json())
        except JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="Malformed JSON payload.") from exc
        except PydanticValidationError as exc:
            raise _validation_error(exc) from exc

    form = await request.form()
    resume_text = str(form.get("resume_text") or "")
    resume_file = form.get("resume_file")

    if resume_file is not None and hasattr(resume_file, "read"):
        file_bytes = await resume_file.read()
        resume_text = extract_text_from_bytes(getattr(resume_file, "filename", None), file_bytes)

    raw_payload: dict[str, Any] = {
        "resume_text": resume_text,
        "jd_text": form.get("jd_text") or form.get("job_description") or "",
        "use_gemini": form.get("use_gemini", True),
        "gemini_api_key": form.get("gemini_api_key"),
    }

    try:
        return AnalyzeRequest.model_validate(raw_payload)
    except PydanticValidationError as exc:
        raise _validation_error(exc) from exc


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: Request,
    service: AnalysisService = Depends(get_analysis_service),
):
    payload = await _parse_payload(request)
    return service.analyze(
        payload.resume_text,
        payload.jd_text,
        use_gemini=payload.use_gemini,
        gemini_api_key=payload.gemini_api_key,
    )
