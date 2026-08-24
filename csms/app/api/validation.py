"""Reusable authoritative input validation for write APIs."""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def _strip(value: str) -> str:
    return value.strip()


TrimmedSiteName = Annotated[str, AfterValidator(_strip), Field(min_length=2, max_length=120)]
TrimmedAddress = Annotated[str, AfterValidator(_strip), Field(min_length=5, max_length=300)]
OperatingHours = Annotated[str, AfterValidator(_strip), Field(max_length=500)]
ShortName = Annotated[str, AfterValidator(_strip), Field(min_length=2, max_length=200)]


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SiteCoordinatesMixin(StrictRequestModel):
    latitude: Optional[float] = Field(None, ge=-90, le=90, allow_inf_nan=False)
    longitude: Optional[float] = Field(None, ge=-180, le=180, allow_inf_nan=False)

    @model_validator(mode="after")
    def reject_null_island(self):
        if self.latitude == 0 and self.longitude == 0:
            raise ValueError("latitude and longitude must not both be zero")
        return self
