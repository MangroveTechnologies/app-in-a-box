"""Shared base model for all Pydantic models."""
from pydantic import BaseModel, ConfigDict


class AppBaseModel(BaseModel):
    """Base model with camelCase alias generation for wire format."""
    model_config = ConfigDict(
        populate_by_name=True,
    )
