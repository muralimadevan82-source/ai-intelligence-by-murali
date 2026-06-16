import os
import re
import io

import streamlit as st
from google import genai

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ATS Intelligence",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ────────────────────────────────────────────────────────────────
DEFAULT_MODEL = "gemini-2.0-flash"

# ── Session state ────────────────────────────────────────────────────────────
for key in ("resume_text", "jd_text", "analysis_result", "chat_history"):
    if key not in st.session_state:
        st.session_state[key] = "" if key != "chat_history" else []

# ── Helpers ──────────────────────────────────────────────────────────────────

def get_client():
    api_key = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        api_key = st.session_state.get("gemini_api_key", "")
    if not api_key:
        st.error("Gemini API key missing. Set GEMINI_API_KEY in secrets or enter it in Settings.")
        st.stop()
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
            from pdfminer.high_level import extract_text
            return extract_text(io.BytesIO(raw))
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


def call_gemini(prompt: str, model: str = DEFAULT_MODEL) -> str:
    client = get_client()
    resp = client.models.generate_content(model=model, contents=prompt)
    return resp.text


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


# ── Prompts ──────────────────────────────────────────────────────────────────

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

# ── Sidebar ──────────────────────────────────────────────────────────────────

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

# ── Pages ────────────────────────────────────────────────────────────────────

if page == "Settings":
    st.header("Settings")
    current_key = st.session_state.get("gemini_api_key", "")
    new_key = st.text_input("Gemini API Key", value=current_key, type="password")
    if new_key:
        st.session_state["gemini_api_key"] = new_key
    if st.button("Clear session data"):
        for key in list(st.session_state.keys()):
            if key != "gemini_api_key":
                del st.session_state[key]
        st.rerun()

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
            with st.spinner("Analyzing with Gemini..."):
                prompt = ANALYSIS_PROMPT.format(
                    resume=st.session_state.resume_text[:15000],
                    jd=st.session_state.jd_text[:10000],
                )
                try:
                    result = call_gemini(prompt)
                    st.session_state["analysis_result"] = result
                    st.success("Analysis complete!")
                except Exception as e:
                    st.error(f"Analysis failed: {e}")

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
            with st.spinner("Analyzing skill gaps..."):
                prompt = SKILL_GAP_PROMPT.format(
                    resume=st.session_state.resume_text[:15000],
                    jd=st.session_state.jd_text[:10000],
                )
                try:
                    result = call_gemini(prompt)
                    st.markdown(result)
                except Exception as e:
                    st.error(f"Skill gap analysis failed: {e}")
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
            with st.spinner("Optimizing resume..."):
                prompt = OPTIMIZER_PROMPT.format(
                    resume=st.session_state.resume_text[:15000],
                    jd=st.session_state.jd_text[:10000],
                )
                try:
                    result = call_gemini(prompt)
                    st.subheader("Optimized Resume")
                    st.markdown(result)
                    st.download_button(
                        "Download as TXT",
                        data=result,
                        file_name="optimized_resume.txt",
                        mime="text/plain",
                    )
                except Exception as e:
                    st.error(f"Optimization failed: {e}")

elif page == "AI Career Coach":
    st.header("AI Career Coach")
    if not st.session_state.resume_text or not st.session_state.jd_text:
        st.info("Upload a resume and job description first to enable career coaching.")
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
                    try:
                        response = call_gemini(full_prompt)
                        st.markdown(response)
                        st.session_state.chat_history.append({"role": "assistant", "content": response})
                    except Exception as e:
                        st.error(f"Coach response failed: {e}")

elif page == "Cover Letter Generator":
    st.header("Cover Letter Generator")
    if not st.session_state.resume_text or not st.session_state.jd_text:
        st.info("Upload a resume and job description first.")
    else:
        tone = st.selectbox("Tone", ["Professional", "Enthusiastic", "Formal", "Concise"])
        if st.button("Generate Cover Letter", type="primary"):
            with st.spinner("Generating cover letter..."):
                prompt = COVER_LETTER_PROMPT.format(
                    resume=st.session_state.resume_text[:15000],
                    jd=st.session_state.jd_text[:10000],
                )
                prompt = f"Tone: {tone}\n\n{prompt}"
                try:
                    result = call_gemini(prompt)
                    st.subheader("Cover Letter")
                    st.markdown(result)
                    st.download_button(
                        "Download as TXT",
                        data=result,
                        file_name="cover_letter.txt",
                        mime="text/plain",
                    )
                except Exception as e:
                    st.error(f"Cover letter generation failed: {e}")
