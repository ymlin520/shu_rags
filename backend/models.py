from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("搜尋問題不可為空白")
        return value


class SearchResult(BaseModel):
    score: float
    category: str = ""
    question: str
    answer: str
    url: str = ""
    keywords: str = ""
    updated_at: str = ""


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class AnswerResponse(BaseModel):
    query: str
    answer: str
    results: list[SearchResult]
    generated: bool
    model: str = ""
    notice: str = ""
    followups: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    helpful: bool
    source_question: str = Field(default="", max_length=500)


class FeedbackResponse(BaseModel):
    saved: bool = True


class TicketCreateRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    subject: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=3000)
    office: str = Field(default="", max_length=100)
    category: str = Field(default="其他", max_length=100)
    requester_name: str = Field(min_length=1, max_length=100)
    requester_contact: str = Field(min_length=1, max_length=200)


class TicketUpdateRequest(BaseModel):
    status: str = Field(pattern="^(待處理|處理中|已解決)$")
    assignee: str = Field(default="", max_length=100)
    resolution: str = Field(default="", max_length=3000)
    office: str = Field(default="", max_length=100)


class TicketRateRequest(BaseModel):
    access_key: str = Field(min_length=16, max_length=100)
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)


class TicketReplyRequest(BaseModel):
    access_key: str = Field(min_length=16, max_length=100)
    message: str = Field(min_length=1, max_length=3000)
    allow_faq: bool = False


class MailSettingsRequest(BaseModel):
    server: str = Field(default="smtp.gmail.com", max_length=200)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = Field(default="", max_length=200)
    from_name: str = Field(default="校務 FAQ 工單系統", max_length=100)
    password: str = Field(default="", max_length=200)
    offices: dict[str, str] = Field(default_factory=dict)


class MailTestRequest(BaseModel):
    to: str = Field(default="", max_length=200)


class OfficeMailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
