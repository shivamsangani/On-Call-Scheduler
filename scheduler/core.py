from scheduler.models import Entry, Override, Schedule
from datetime import datetime
from itertools import pairwise

def base_user_at(schedule: Schedule, t: datetime) -> str | None: 
    """Who the regular rota puts on call at moment t"""
    if t < schedule.handover_start_at: 
        return None 

    shift_number = (t - schedule.handover_start_at) // schedule.handover_interval

    return schedule.users[shift_number % len(schedule.users)]

def on_call_at(schedule: Schedule, overrides: list[Override], t: datetime) -> str | None: 
    """Who is actually on call at moment t"""
    for override in overrides:
        #overrides don't overlap, at most one can cover t, so return on first match is safe 
        if override.covers(t): 
            return override.user

    return base_user_at(schedule, t) 


def handovers_between(schedule: Schedule, window_start: datetime, window_end: datetime) -> list[datetime]: 
    """Every handover strictly inside the window"""
    #give the shift number of the first shift that is before or at window_start
    first_shift_number = max(0, (window_start - schedule.handover_start_at) // schedule.handover_interval)

    #calculate the first shift's start time
    #(only append shifts that are strictly inside the window)
    shift_start_time = schedule.handover_start_at + (first_shift_number * schedule.handover_interval)

    handovers = []

    while shift_start_time < window_end: 
        if shift_start_time > window_start: 
            handovers.append(shift_start_time)
        shift_start_time += schedule.handover_interval

    return handovers

def list_change_points(schedule: Schedule, overrides: list[Override], window_start: datetime, window_end: datetime) -> list[datetime]: 
    """Every moment where the on-call person might change"""
    change_points = {window_start, window_end}


    handovers = handovers_between(schedule, window_start, window_end)
    change_points.update(handovers)
    
    for override in overrides: 
        if window_start < override.start_at < window_end: 
            change_points.add(override.start_at)
        if window_start < override.end_at < window_end: 
            change_points.add(override.end_at)

    return sorted(change_points)

def merge_adjacent(entries: list[Entry]) -> list[Entry]: 
    """Join back to back entries for the same user"""
    merged = []
    for entry in entries: 
        if merged and entry.user == merged[-1].user and entry.start_at == merged[-1].end_at: 
            merged[-1] = Entry(entry.user, merged[-1].start_at, entry.end_at)
        else: 
            merged.append(entry)

    return merged



def render_schedule(schedule: Schedule, overrides: list[Override], window_start: datetime, window_end: datetime) -> list[Entry]: 
    """Generate full schedule"""
    change_points = list_change_points(schedule, overrides, window_start, window_end)

    entries = []

    for seg_start, seg_end in pairwise(change_points): 
        user_on_call = on_call_at(schedule, overrides, seg_start)
        if user_on_call is not None: 
            entries.append(Entry(user_on_call, seg_start, seg_end))

    return merge_adjacent(entries)

    




    