from dataclasses import dataclass
from datetime import datetime, timedelta
from scheduler.core import render_schedule
from scheduler.loader import format_time
from scheduler.models import Schedule, Override, Entry

class CoverError(Exception): ...

@dataclass(frozen=True)
class CoverRequest: 
    requester: str
    start_at: datetime 
    end_at: datetime 
    reason: str 

@dataclass(frozen=True)
class Candidate: 
    user: str
    hours_on_call: float
    #true if the candidate isn't on call at any point in the 12 hours before or after the cover window  
    rested: bool 
    reason: str

def validate_request(schedule: Schedule, overrides: list[Override], request: CoverRequest, now: datetime) -> None: 
    if request.end_at <= request.start_at: 
        raise CoverError("request end time before or at start time") 

    if request.start_at < now: 
        raise CoverError("request is in the past") 

    if request.requester not in schedule.users:  
        raise CoverError(f"{request.requester} is not on this rota")

    entries = render_schedule(schedule, overrides, request.start_at, request.end_at)
    

    if len(entries) == 1 and entries[0].user == request.requester: 
        return

    on_call = ", ".join(f"{e.user} {format_time(e.start_at)}–{format_time(e.end_at)}" for e in entries) or "no one"
    raise CoverError(f"{request.requester} is not on call for that whole window: {on_call}") 

def hours_on_call(entries: list[Entry], user: str) -> float: 
    total = timedelta()

    for entry in entries: 
        if entry.user == user: 
            total += entry.end_at - entry.start_at

    return total / timedelta(hours=1)

def rank_candidates(schedule: Schedule, overrides: list[Override], request: CoverRequest, fairness_days=14, rest_hours=12) -> list[Candidate]: 
    fairness = timedelta(days=fairness_days)
    entries = render_schedule(schedule, overrides, request.start_at-fairness, request.end_at + fairness)

    rest = timedelta(hours=rest_hours)
    nearby_on_call = render_schedule(schedule, overrides, request.start_at-rest, request.end_at+rest)
    busy = {e.user for e in nearby_on_call}

    candidates = []

    for user in dict.fromkeys(schedule.users): 
        if user != request.requester: 
            hours = hours_on_call(entries, user)
            rested = user not in busy 
            reason = f"{hours:.0f}h on call in ±{fairness_days}d, " + ("rested" if rested else f"on call within {rest_hours}h")
            candidates.append(Candidate(user, hours, rested, reason))

    if not candidates: 
        raise CoverError("no one else on the rota can cover")
    
    #fewer hours on call first, then rested before not rested, the alphabetical
    #only moves on when there's a tie 
    candidates.sort(key=lambda c: (c.hours_on_call, not c.rested, c.user))
    return candidates

def propose_override(request: CoverRequest, candidate: Candidate) -> Override: 
    return Override(candidate.user, request.start_at, request.end_at)


    
    