import os
import re

from google import genai

from resume_matcher.schemas.response import AnalyzeResponse

ANALYSIS_PROMPT = """You are an expert ATS (Applicant Tracking System) analyzer. Analyze this resume against the job description.

Resume:
{resume}

Job Description:
{jd}

Return your analysis in EXACTLY this format:
ATS Score: <0-100>
Matched Keywords: <comma-separated list>
Missing Keywords: <comma-separated list>
Summary: <2-3 sentence analysis>
Skill Gaps: <specific missing skills>
Recommendations: <actionable improvements>"""


class AnalysisService:
    def analyze(
        self,
        resume_text: str,
        jd_text: str,
        use_gemini: bool = False,
        gemini_api_key: str | None = None,
    ) -> AnalyzeResponse:
        api_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        if not api_key or not use_gemini:
            return self._local_analyze(resume_text, jd_text)

        client = genai.Client(api_key=api_key)
        prompt = ANALYSIS_PROMPT.format(resume=resume_text[:15000], jd=jd_text[:10000])

        try:
            resp = client.models.generate_content(
                model="gemini-2.0-flash", contents=prompt
            )
            return self._parse_gemini_response(resp.text)
        except Exception:
            return self._local_analyze(resume_text, jd_text)

    def _parse_gemini_response(self, text: str) -> AnalyzeResponse:
        score = 0.0
        matched = []
        missing = []
        summary = ""

        m = re.search(r"(?:ATS\s*)?[Ss]core[^\d]*(\d+(?:\.\d+)?)", text)
        if m:
            score = min(float(m.group(1)), 100)

        m = re.search(r"(?:[Mm]atched|Found)[^:]*:?\s*(.+)", text)
        if m:
            matched = [x.strip() for x in re.split(r"[,;]", m.group(1)) if x.strip()]

        m = re.search(r"(?:[Mm]issing|[Gg]ap)[^:]*:?\s*(.+)", text)
        if m:
            missing = [x.strip() for x in re.split(r"[,;]", m.group(1)) if x.strip()]

        m = re.search(r"(?:[Ss]ummary|[Oo]verview)[^:]*:?\s*(.+?)(?=\n\n|\Z)", text, re.DOTALL)
        if m:
            summary = m.group(1).strip()

        return AnalyzeResponse(
            score=score,
            summary=summary or text[:500],
            matched_keywords=matched,
            missing_keywords=missing,
        )

    def _local_analyze(self, resume_text: str, jd_text: str) -> AnalyzeResponse:
        resume_lower = resume_text.lower()
        jd_lower = jd_text.lower()

        stopwords = {"the", "a", "an", "and", "or", "in", "of", "to", "for", "with", "on", "at", "by", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "shall", "can", "need", "must", "this", "that", "these", "those", "it", "its", "we", "our", "you", "your", "they", "their", "them"}
        jd_words = [w for w in re.findall(r'\b[a-zA-Z]{3,}\b', jd_lower) if w not in stopwords]
        resume_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', resume_lower))

        word_counts = {}
        for w in jd_words:
            word_counts[w] = word_counts.get(w, 0) + 1
        jd_unique = sorted(word_counts.items(), key=lambda x: -x[1])

        matched = []
        missing = []
        for word, count in jd_unique[:50]:
            if word in resume_words:
                matched.append(word)
            else:
                if count > 1:
                    missing.append(word)

        score = (len(matched) / max(len(matched) + len(missing), 1)) * 100 if matched or missing else 0

        return AnalyzeResponse(
            score=round(score, 1),
            summary=f"Found {len(matched)} matching keywords out of {len(matched) + len(missing)} key terms.",
            matched_keywords=matched[:20],
            missing_keywords=missing[:20],
        )
