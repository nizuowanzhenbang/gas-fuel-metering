"""Explicit fixed-offset business days. No DST or historical timezone inference."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from ..config import get_settings


class BusinessDayPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)
    timezone: Literal['UTC', 'UTC+08:00'] = 'UTC'
    start_minute: int = Field(default=0, ge=0, le=1439)
    version: Literal['fixed-offset-v1'] = 'fixed-offset-v1'

    @property
    def tz(self):
        return timezone(timedelta(hours=8 if self.timezone == 'UTC+08:00' else 0))

    def window(self, day: date):
        start = datetime.combine(day, time.min, tzinfo=self.tz) + timedelta(minutes=self.start_minute)
        return BusinessWindow(policy=self, start_utc=start.astimezone(timezone.utc),
                              end_utc=(start + timedelta(days=1)).astimezone(timezone.utc))

    def latest_completed_date(self, now: datetime) -> date:
        if now.tzinfo is None:
            raise ValueError('now must include a UTC offset')
        today = now.astimezone(self.tz).date()
        current = today if now >= self.window(today).start_utc else today - timedelta(days=1)
        return current - timedelta(days=1)


class BusinessWindow(BaseModel):
    policy: BusinessDayPolicy
    start_utc: datetime
    end_utc: datetime


def current_policy() -> BusinessDayPolicy:
    settings = get_settings()
    return BusinessDayPolicy(timezone=settings.business_timezone, start_minute=settings.business_day_start_minute)
