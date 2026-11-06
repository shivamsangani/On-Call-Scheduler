"""Plain data types used throughout the scheduler"""

from dataclasses import dataclass
from datetime import datetime, timedelta 

# objects can't change after they're created
@dataclass(frozen=True)
class Schedule: 
    users: tuple[str, ...]
    handover_start_at: datetime
    #conversion from days happens once
    handover_interval: timedelta

@dataclass(frozen=True)
class Override: 
    user: str 
    start_at: datetime 
    end_at: datetime 

    def covers(self, t: datetime) -> bool: 
        """true if t falls inside [start_at, end_at)"""
        return self.start_at <= t < self.end_at 

@dataclass(frozen=True)
class Entry: 
    user: str
    start_at: datetime 
    end_at: datetime 