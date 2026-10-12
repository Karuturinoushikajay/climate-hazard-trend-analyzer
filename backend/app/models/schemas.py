"""Request bodies. Limits are intentional: they keep archive calls small and predictable."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BBox(BaseModel):
    model_config = ConfigDict(extra="forbid")
    west: float = Field(ge=-180, le=180, allow_inf_nan=False)
    south: float = Field(ge=-90, le=90, allow_inf_nan=False)
    east: float = Field(ge=-180, le=180, allow_inf_nan=False)
    north: float = Field(ge=-90, le=90, allow_inf_nan=False)

    @model_validator(mode="after")
    def _check_box(self) -> BBox:
        if self.south >= self.north:
            raise ValueError("South must be less than north")
        if self.west >= self.east:
            raise ValueError("West must be less than east. Boxes that cross the dateline are not supported.")
        if self.north - self.south > 15 or self.east - self.west > 15:
            raise ValueError("Keep the box within 15 degrees on each side")
        if self.north - self.south < 0.1 or self.east - self.west < 0.1:
            raise ValueError("That box is smaller than 0.1 degrees. Choose a city point instead.")
        return self


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hazard: str = "heatwave"
    region_id: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=120)
    mode: str = "city"
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    bbox: BBox | None = None
    start_year: int = Field(ge=1940, le=2100)
    end_year: int = Field(ge=1940, le=2100)
    baseline_start_year: int = Field(default=1961, ge=1940, le=2100)
    baseline_end_year: int = Field(default=1990, ge=1940, le=2100)
    percentile: float = Field(default=95, ge=90, le=99, allow_inf_nan=False)
    min_duration: int = Field(default=3, ge=2, le=10)

    @field_validator("hazard")
    @classmethod
    def _hazard(cls, value: str) -> str:
        if value != "heatwave":
            raise ValueError("Only the heatwave hazard is implemented")
        return value

    @field_validator("mode")
    @classmethod
    def _mode(cls, value: str) -> str:
        if value not in {"city", "region", "bbox"}:
            raise ValueError("mode must be city, region, or bbox")
        return value

    @field_validator("region_id", mode="before")
    @classmethod
    def _region_id(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("region_id must be a string")
        text = value.strip()
        if not text:
            return None
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        if any(char not in allowed for char in text):
            raise ValueError("region_id contains unsupported characters")
        return text

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("name must be a string")
        if any(ord(char) < 32 for char in value):
            raise ValueError("name contains control characters")
        text = " ".join(value.split())
        return text or None

    @model_validator(mode="after")
    def _years(self) -> AnalyzeRequest:
        if self.end_year < self.start_year:
            raise ValueError("End year must be on or after the start year")
        span = self.end_year - self.start_year + 1
        if span < 10:
            raise ValueError("Choose at least 10 years so a trend can be estimated")
        if span > 80:
            raise ValueError("Choose a range of 80 years or fewer")
        if self.baseline_end_year < self.baseline_start_year:
            raise ValueError("Baseline end year must be on or after the baseline start year")
        baseline_span = self.baseline_end_year - self.baseline_start_year + 1
        if baseline_span < 10:
            raise ValueError("Baseline must cover at least 10 years")
        if baseline_span > 50:
            raise ValueError("Baseline must cover 50 years or fewer")
        this_year = date.today().year
        if self.start_year > this_year or self.end_year > this_year:
            raise ValueError("Years cannot be in the future")
        if self.baseline_start_year > this_year or self.baseline_end_year > this_year:
            raise ValueError("Baseline years cannot be in the future")
        return self


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis: dict

    @model_validator(mode="after")
    def _check(self) -> ExportRequest:
        insight = self.analysis.get("insight") if isinstance(self.analysis, dict) else None
        headline = insight.get("headline") if isinstance(insight, dict) else None
        if not isinstance(headline, str) or not headline.strip() or len(headline) > 600:
            raise ValueError("The analysis insight is missing")
        annual = self.analysis.get("annual")
        events = self.analysis.get("events")
        if not isinstance(annual, list) or not annual or len(annual) > 120:
            raise ValueError("The annual series is missing or too long")
        if not isinstance(events, list) or len(events) > 400:
            raise ValueError("The event list is missing or too long")
        return self
