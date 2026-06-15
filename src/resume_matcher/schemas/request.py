from typing import List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    resume_text: str = Field(min_length=20)
    jd_text: str = Field(
        min_length=20,
        validation_alias=AliasChoices("jd_text", "job_description"),
    )
    use_gemini: bool = True
    gemini_api_key: Optional[str] = None

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    chat_history: List[ChatMessage] = Field(default_factory=list)
    current_message: str
    resume_text: str
    jd_text: str
    gemini_api_key: Optional[str] = None

class ExportPDFRequest(BaseModel):
    resume_text: str
