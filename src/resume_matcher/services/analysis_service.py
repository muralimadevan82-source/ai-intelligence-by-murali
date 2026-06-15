from resume_matcher.schemas.response import AnalyzeResponse


class AnalysisService:
    def analyze(
        self,
        resume_text: str,
        jd_text: str,
        use_gemini: bool = False,
        gemini_api_key: str | None = None,
    ) -> AnalyzeResponse:
        return AnalyzeResponse(
            score=0.0,
            summary="Analysis not implemented yet.",
            matched_keywords=[],
            missing_keywords=[],
        )
