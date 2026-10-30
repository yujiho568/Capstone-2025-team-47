from datetime import datetime
from pydantic import BaseModel,Field,ConfigDict,AwareDatetime,StrictBool,StrictInt,field_validator
from typing import Literal

class RiskResult(BaseModel):
    risk: float = Field(ge=0,le=100,allow_inf_nan=False,strict=True)
    model_config=ConfigDict(extra='forbid')
class OcResult(RiskResult):
    engine: Literal['ocsvm']
    score: float = Field(allow_inf_nan=False,strict=True)
    is_anomaly: StrictBool
class DbResult(RiskResult):
    engine: Literal['dbscan']
    cluster: StrictInt
    is_noise: StrictBool
    nearest_dist: float = Field(ge=0,allow_inf_nan=False,strict=True)
    eps: float = Field(gt=0,allow_inf_nan=False,strict=True)
    r: float = Field(ge=0,allow_inf_nan=False,strict=True)
class ResultPayload(BaseModel):
    ok: StrictBool
    eventID: str = Field(min_length=1)
    userId: str = Field(min_length=1)
    timestamp: AwareDatetime
    eventName: str = Field(min_length=1)
    modelVersion: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    initial_session: StrictBool
    embedding_dim: StrictInt = Field(gt=0,le=4096)
    result: OcResult | DbResult = Field(discriminator='engine')
    model_config=ConfigDict(extra='forbid')
    @field_validator('ok')
    @classmethod
    def success_required(cls,value):
        if not value: raise ValueError('not_a_detection_result')
        return value

class ImportS3Request(BaseModel):
    credential_name: str = 'default'
    max_files: int = Field(100,ge=1,le=1000)
    continuation_token: str | None = Field(None,max_length=4096)
    dry_run: bool = False
    model_config=ConfigDict(extra='forbid')
class ImportS3Summary(BaseModel):
    scanned: int
    imported: int
    skipped_existing: int
    errors: int
    failures: list[dict]
    continuation_token: str | None = None
    synced_at: datetime
    status: Literal['success','partial_failure']
