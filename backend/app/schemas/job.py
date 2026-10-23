from datetime import datetime

from pydantic import BaseModel


class JobOut(BaseModel):
    id: int
    job_type: str
    status: str
    priority: int
    payload: dict
    result: dict | None
    olt_id: int | None
    onu_id: int | None
    created_by: int | None
    attempts: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    error_message: str | None
    error_code: str | None

    model_config = {"from_attributes": True}
