from pydantic import BaseModel,Field,ConfigDict,model_validator
from datetime import datetime
from typing import Literal

SESSION_KEY_PATTERN=r'^[A-Za-z0-9_.:-]+$'

class SessionChoiceInput(BaseModel):
    left_id:int
    right_id:int
    winner:Literal['left','right']

class ExpectedPairInput(BaseModel):
    left_id:int
    right_id:int

class SessionInput(BaseModel):
    study_id:int
    session_key:str=Field(min_length=2,max_length=80,pattern=SESSION_KEY_PATTERN)
    # Whole group in one request; empty list is rejected by the service so a
    # revision can never silently drop the group it replaces.
    choices:list[SessionChoiceInput]=Field(min_length=1,max_length=300)
    expected_pairs:list[ExpectedPairInput]=Field(default_factory=list,max_length=300)

class SessionOut(BaseModel):
    id:int
    study_id:int
    session_key:str
    revision:int
    status:str
    quarantine_reason:str
    choices:list[dict]
    expected_pairs:list[dict]
    content_digest:str
    created_at:datetime
    updated_at:datetime
    model_config=ConfigDict(from_attributes=True)

class SessionSubmitOut(SessionOut):
    created:bool
