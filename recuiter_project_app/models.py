# models.py
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
import json
from config import get_job_config
from datetime import datetime


class Candidate(BaseModel):
    email: str
    name: Optional[str] = None
    city: Optional[str] = None
    degree: Optional[str] = None
    experience: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    raw_text: str = ""
    source: str = ""   # 'gmail' or 'form'
    #attachments: List[Dict[str,str]] = Field(default_factory=list)  # [{"name":..., "drive_file_id":...}]
    job_id: str = "AI"
    role_applied: Optional[str] = job_id
    status: str = "received"
    test_score: Optional[float] = None
    cv_score: Optional[float] = None
    overall_score: Optional[float] = None
    interview_questions: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    interview_event_id: Optional[str] = None
    form_id: Optional[str] = None  # Add form_id field to store Google Form ID
    interview_email_sent: bool = False
    rejection_email_sent: bool = False
    final_evaluation: str=""
    
class PipelineState(BaseModel):
    job_id: str = Field(default_factory=lambda: f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    candidates: List[Candidate] = Field(default_factory=list)
    drive_folder_id: Optional[str] = None
    sheet_id: Optional[str] = None
    calendar_id: Optional[str] = None




