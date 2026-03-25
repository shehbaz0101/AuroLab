from pydantic import BaseModel, Field
from typing import Optional, Dict


class ProtocolRequest(BaseModel):
    experiment: str = Field(..., min_length=5)
    constraints: Optional[Dict] = None