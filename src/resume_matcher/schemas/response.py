from pydantic import BaseModel


class AnalyzeResponse(BaseModel):
    score: float = 0.0
    summary: str = ""
    matched_keywords: list[str] = []
    missing_keywords: list[str] = []
