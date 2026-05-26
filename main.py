from engine import CAD407Logbook
from dashboard import LogbookDashboard

# Initialize Engine
my_logbook = CAD407Logbook(pilot_name="L CHIANG")

def get_mvp_data(logbook, category=None, query=None):
    """Function for UI to fetch all needed display data at once."""
    history = logbook.history
    sync_adjustments = getattr(logbook, 'sync_adjustments', [])
    return {
        "ytd_stats": LogbookDashboard.get_ytd_summary(history, category=category, query=query, sync_adjustments=sync_adjustments),
        "type_breakdown": LogbookDashboard.get_summary_by_type(history, category=category, query=query),
        "full_history": history,
        "sync_adjustments": sync_adjustments
    }

def add_adjustment(logbook, column, value, reason):
    """Bridge for the UI Adjustment Form."""
    logbook.add_manual_adjustment(column, value, reason)
    return "Adjustment Added Successfully"

def get_logbook_preview(logbook, start_page_num, date_from=None, date_to=None):
    """Bridge for the UI Table Preview."""
    return logbook.get_paginated_data(start_page=int(start_page_num), date_from=date_from, date_to=date_to)

print("Logbook MVP Backend Loaded.")