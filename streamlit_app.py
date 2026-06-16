import os
import re
import io
from collections import Counter

import streamlit as st
from google import genai
from google.genai import types as genai_types

st.set_page_config(
    page_title="ATS Intelligence",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEFAULT_MODEL = "gemini-2.0-flash"
FALLBACK_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

for key in ("resume_text", "jd_text", "analysis_result", "chat_history", "use_local"):
    if key not in st.session_state:
        st.session_state[key] = "" if key != "chat_history" else []
    if key == "use_local" and st.session_state[key] == "":
        st.session_state[key] = False

STOPWORDS = {
    "the","a","an","and","or","in","of","to","for","with","on","at","by","is","are",
    "was","were","be","been","being","have","has","had","do","does","did","will",
    "would","could","should","may","might","shall","can","need","must","this","that",
    "these","those","it","its","we","our","you","your","they","their","them","not",
    "no","nor","but","so","if","than","then","also","very","just","about","above",
    "after","all","any","because","before","between","both","each","few","more",
    "most","other","some","such","only","own","same","too","under","up","into",
    "over","here","there","when","where","why","how","what","which","who","whom",
}


def get_client():
    api_key = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        api_key = st.session_state.get("gemini_api_key", "")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def extract_text_from_file(uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    fname = uploaded_file.name.lower()
    raw = uploaded_file.read()
    if fname.endswith(".txt"):
        return raw.decode("utf-8", errors="replace")
    if fname.endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                return "\n".join(p.text or "" for p in pdf.pages)
        except ImportError:
            pass
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(raw))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except ImportError:
            pass
        return raw.decode("utf-8", errors="replace")
    if fname.endswith(".docx"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs)
        except ImportError:
            pass
        return raw.decode("utf-8", errors="replace")
    return raw.decode("utf-8", errors="replace")


def call_gemini(prompt: str, model: str = DEFAULT_MODEL) -> str | None:
    client = get_client()
    if client is None:
        return None
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        if resp.text:
            return resp.text
        if resp.candidates and resp.candidates[0].finish_reason == 4:
            return None
        return None
    except Exception as e:
        err_str = str(e).lower()
        if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
            return None
        raise


def parse_analysis(text: str) -> dict:
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
    return {"score": score, "matched": matched, "missing": missing, "summary": summary or text[:500]}


def local_analyze(resume_text: str, jd_text: str) -> str:
    resume_lower = resume_text.lower()
    jd_lower = jd_text.lower()
    jd_words = [w for w in re.findall(r'\b[a-zA-Z]{3,}\b', jd_lower) if w not in STOPWORDS]
    resume_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', resume_lower))
    word_counts = Counter(jd_words)
    jd_ranked = sorted(word_counts.items(), key=lambda x: -x[1])
    matched = []
    missing = []
    for word, count in jd_ranked[:50]:
        if word in resume_words:
            matched.append(word)
        elif count > 1:
            missing.append(word)
    score = (len(matched) / max(len(matched) + len(missing), 1)) * 100 if matched or missing else 0

    lines = [
        f"ATS Score: {score:.0f}",
        f"Matched Keywords: {', '.join(matched[:20]) if matched else 'None found'}",
        f"Missing Keywords: {', '.join(missing[:20]) if missing else 'None detected'}",
        f"Summary: Found {len(matched)} matching keywords out of {len(matched) + len(missing)} key terms identified in the job description.",
        f"Skill Gaps: {', '.join(missing[:10]) if missing else 'No significant gaps detected'}",
        f"Recommendations: {'Focus on adding: ' + ', '.join(missing[:5]) if missing else 'Your resume aligns well with this role.'}",
    ]
    return "\n".join(lines)


def try_gemini_with_fallback(prompt: str, model: str = DEFAULT_MODEL) -> str | None:
    models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]
    for m in models_to_try:
        result = call_gemini(prompt, model=m)
        if result is not None:
            return result
    return None


ANALYSIS_PROMPT = """You are an expert ATS (Applicant Tracking System) analyzer. Analyze this resume against the job description.

Resume:
{resume}

Job Description:
{jd}

Return your analysis in this format:
ATS Score: <0-100>
Matched Keywords: <comma-separated>
Missing Keywords: <comma-separated>
Summary: <2-3 sentence analysis>
Skill Gaps: <specific skills missing>
Recommendations: <actionable improvements>"""

OPTIMIZER_PROMPT = """You are a professional resume writer. Rewrite/optimize the following resume to better match this job description. Preserve all genuine experience but improve keyword alignment and impact.

Resume:
{resume}

Job Description:
{jd}

Return the optimized resume and a brief summary of changes made."""

COACH_PROMPT = """You are an AI Career Coach. The user's resume is being matched against this job description. Based on the analysis, provide:

1. Career advice and skill development roadmap
2. Interview preparation tips
3. Specific courses or certifications to bridge gaps
4. Long-term career growth suggestions

Resume:
{resume}

Job Description:
{jd}

Current Chat History:
{history}

User Message:
{message}"""

COVER_LETTER_PROMPT = """Write a professional, personalized cover letter for this resume and job description. Be specific, mention relevant skills, and show enthusiasm. Company culture should be addressed professionally.

Resume:
{resume}

Job Description:
{jd}"""

SKILL_GAP_PROMPT = """Analyze the skill gaps between this resume and job description. For each missing skill, suggest:
1. How critical it is (Critical/Important/Nice-to-have)
2. A free resource to learn it
3. Estimated time to learn the basics

Resume:
{resume}

Job Description:
{jd}"""

with st.sidebar:
    st.title("ATS Intelligence")
    st.caption("AI-Powered Resume Analysis")
    st.divider()
    page = st.radio(
        "Navigate",
        [
            "ATS Match Score",
            "Resume Upload & Analysis",
            "Skill Gap Detection",
            "Resume Optimizer",
            "AI Career Coach",
            "Cover Letter Generator",
            "Settings",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("Made by Murali Madevan")
    st.caption("[LinkedIn](https://www.linkedin.com/in/murali-madevan/)")

if page == "Settings":
    st.header("Settings")
    current_key = st.session_state.get("gemini_api_key", "")
    new_key = st.text_input("Gemini API Key", value=current_key, type="password")
    if new_key:
        st.session_state["gemini_api_key"] = new_key
    st.session_state["use_local"] = st.toggle("Use local analysis only (no API key needed)", value=st.session_state.get("use_local", False))
    if st.button("Clear session data"):
        for key in list(st.session_state.keys()):
            if key != "gemini_api_key" and key != "use_local":
                del st.session_state[key]
        st.rerun()
    if st.session_state.get("use_local"):
        st.info("Local analysis mode active. AI features (Coach, Optimizer, Cover Letter) will be limited.")

elif page == "Resume Upload & Analysis":
    st.header("Resume Upload & Analysis")
    col1, col2 = st.columns(2)
    with col1:
        uploaded = st.file_uploader("Upload Resume (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"])
        if uploaded:
            st.session_state["resume_text"] = extract_text_from_file(uploaded)
            st.success(f"Uploaded {uploaded.name} ({len(st.session_state.resume_text)} chars)")
        resume = st.text_area("Or paste resume text", st.session_state.resume_text, height=300)
        if resume:
            st.session_state["resume_text"] = resume
    with col2:
        jd = st.text_area("Paste Job Description", st.session_state.jd_text, height=300)
        if jd:
            st.session_state["jd_text"] = jd

    if st.button("Run Analysis", type="primary", use_container_width=True):
        if not st.session_state.resume_text or len(st.session_state.resume_text) < 20:
            st.error("Resume text too short (min 20 chars)")
        elif not st.session_state.jd_text or len(st.session_state.jd_text) < 20:
            st.error("Job description too short (min 20 chars)")
        else:
            if st.session_state.get("use_local"):
                with st.spinner("Running local analysis..."):
                    result = local_analyze(
                        st.session_state.resume_text[:15000],
                        st.session_state.jd_text[:10000],
                    )
                    st.session_state["analysis_result"] = result
                    st.info("Local analysis complete. For AI-powered results, disable local mode and add a Gemini API key in Settings.")
            else:
                with st.spinner("Analyzing with Gemini..."):
                    prompt = ANALYSIS_PROMPT.format(
                        resume=st.session_state.resume_text[:15000],
                        jd=st.session_state.jd_text[:10000],
                    )
                    result = try_gemini_with_fallback(prompt)
                    if result is not None:
                        st.session_state["analysis_result"] = result
                        st.success("Analysis complete!")
                    else:
                        st.warning("Gemini API quota exceeded. Falling back to local analysis.")
                        result = local_analyze(
                            st.session_state.resume_text[:15000],
                            st.session_state.jd_text[:10000],
                        )
                        st.session_state["analysis_result"] = result
                        st.info("Local analysis complete. Add a Gemini API key in Settings for AI-powered results.")

    if st.session_state.get("analysis_result"):
        with st.expander("Raw Analysis", expanded=False):
            st.text(st.session_state.analysis_result)

elif page == "ATS Match Score":
    st.header("ATS Match Score")
    if not st.session_state.get("analysis_result"):
        st.info("Go to 'Resume Upload & Analysis' to run an analysis first.")
    else:
        parsed = parse_analysis(st.session_state.analysis_result)
        score = parsed["score"]
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("ATS Score", f"{score:.0f}%")
            st.progress(score / 100)
        with col2:
            st.metric("Matched Keywords", str(len(parsed["matched"])))
            if parsed["matched"]:
                st.write("**Matched:**", ", ".join(parsed["matched"][:15]))
        with col3:
            st.metric("Missing Keywords", str(len(parsed["missing"])))
            if parsed["missing"]:
                st.write("**Missing:**", ", ".join(parsed["missing"][:15]))
        if parsed["summary"]:
            st.subheader("Summary")
            st.write(parsed["summary"])

        st.subheader("Score Breakdown")
        breakdown = {
            "Keyword Match": min(score * 0.35, 35),
            "Content Relevance": min(score * 0.30, 30),
            "Format & Structure": min(score * 0.20, 20),
            "Experience Alignment": min(score * 0.15, 15),
        }
        for k, v in breakdown.items():
            st.write(f"{k}: {v:.1f}/100")

elif page == "Skill Gap Detection":
    st.header("Skill Gap Detection")
    if not st.session_state.get("analysis_result"):
        st.info("Go to 'Resume Upload & Analysis' to run an analysis first.")
    else:
        if st.button("Analyze Skill Gaps", type="primary"):
            if st.session_state.get("use_local"):
                parsed = parse_analysis(st.session_state.analysis_result)
                if parsed["missing"]:
                    st.subheader("Detected Gaps")
                    for skill in parsed["missing"]:
                        with st.container(border=True):
                            st.write(f"**{skill}**")
                            st.write("Criticality: Important")
                            st.write("Resource: Search LinkedIn Learning or Coursera")
                else:
                    st.info("No skill gaps detected.")
            else:
                with st.spinner("Analyzing skill gaps..."):
                    prompt = SKILL_GAP_PROMPT.format(
                        resume=st.session_state.resume_text[:15000],
                        jd=st.session_state.jd_text[:10000],
                    )
                    result = try_gemini_with_fallback(prompt)
                    if result is not None:
                        st.markdown(result)
                    else:
                        st.warning("Gemini unavailable. Showing basic gaps.")
                        parsed = parse_analysis(st.session_state.analysis_result)
                        if parsed["missing"]:
                            for skill in parsed["missing"]:
                                with st.container(border=True):
                                    st.write(f"**{skill}**")
                        else:
                            st.info("No skill gaps detected.")
    if st.session_state.get("analysis_result"):
        parsed = parse_analysis(st.session_state.analysis_result)
        if parsed["missing"]:
            st.subheader("Detected Gaps")
            for skill in parsed["missing"]:
                with st.container(border=True):
                    st.write(f"**{skill}**")

elif page == "Resume Optimizer":
    st.header("Resume Optimizer")
    if not st.session_state.resume_text or not st.session_state.jd_text:
        st.info("Upload a resume and job description first.")
    else:
        st.info("This will rewrite your resume to better match the job description while preserving your genuine experience.")
        if st.button("Optimize Resume", type="primary"):
            if st.session_state.get("use_local"):
                st.warning("Resume optimizer requires Gemini API. Add an API key in Settings or disable local mode.")
            else:
                with st.spinner("Optimizing resume..."):
                    prompt = OPTIMIZER_PROMPT.format(
                        resume=st.session_state.resume_text[:15000],
                        jd=st.session_state.jd_text[:10000],
                    )
                    result = try_gemini_with_fallback(prompt)
                    if result is not None:
                        st.subheader("Optimized Resume")
                        st.markdown(result)
                        st.download_button(
                            "Download as TXT", data=result, file_name="optimized_resume.txt", mime="text/plain",
                        )
                    else:
                        st.error("All Gemini models are quota-exceeded. Try again later or use a different API key.")

elif page == "AI Career Coach":
    st.header("AI Career Coach")
    if not st.session_state.resume_text or not st.session_state.jd_text:
        st.info("Upload a resume and job description first to enable career coaching.")
    else:
        if st.session_state.get("use_local"):
            st.warning("Career Coach requires Gemini API. Add an API key in Settings or disable local mode.")
        else:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
            if prompt := st.chat_input("Ask your career coach..."):
                st.session_state.chat_history.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)
                history_text = "\n".join(
                    f"{m['role']}: {m['content']}" for m in st.session_state.chat_history[-6:]
                )
                full_prompt = COACH_PROMPT.format(
                    resume=st.session_state.resume_text[:15000],
                    jd=st.session_state.jd_text[:10000],
                    history=history_text,
                    message=prompt,
                )
                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        result = try_gemini_with_fallback(full_prompt)
                        if result is not None:
                            st.markdown(result)
                            st.session_state.chat_history.append({"role": "assistant", "content": result})
                        else:
                            st.error("All Gemini models are quota-exceeded. Try again later.")

elif page == "Cover Letter Generator":
    st.header("Cover Letter Generator")
    if not st.session_state.resume_text or not st.session_state.jd_text:
        st.info("Upload a resume and job description first.")
    else:
        if st.session_state.get("use_local"):
            st.warning("Cover Letter Generator requires Gemini API. Add an API key in Settings or disable local mode.")
        else:
            tone = st.selectbox("Tone", ["Professional", "Enthusiastic", "Formal", "Concise"])
            if st.button("Generate Cover Letter", type="primary"):
                with st.spinner("Generating cover letter..."):
                    prompt = COVER_LETTER_PROMPT.format(
                        resume=st.session_state.resume_text[:15000],
                        jd=st.session_state.jd_text[:10000],
                    )
                    prompt = f"Tone: {tone}\n\n{prompt}"
                    result = try_gemini_with_fallback(prompt)
                    if result is not None:
                        st.subheader("Cover Letter")
                        st.markdown(result)
                        st.download_button(
                            "Download as TXT", data=result, file_name="cover_letter.txt", mime="text/plain",
                        )
                    else:
                        st.error("All Gemini models are quota-exceeded. Try again later.")
