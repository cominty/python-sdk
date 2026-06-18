from pydantic import BaseModel, ConfigDict


class ApiTokenCreated(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token_type: str
    access_token: str


class ApiTokenOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    created_at: str
    name: str
    created_by: str
