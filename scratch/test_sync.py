import sys
import os
sys.path.append('/Users/leonardchiang/Documents/Projects/Logbook')

from engine import CAD407Logbook
from datetime import datetime

# Setup
lb = CAD407Logbook(user_id="test_sync")
lb.history = [
    {'date_obj': datetime(2022, 1, 1), 'day_p1': 1.0, 'id': '1'},
    {'date_obj': datetime(2022, 2, 1), 'day_p1': 2.0, 'id': '2'},
    {'date_obj': datetime(2022, 3, 1), 'day_p1': 3.0, 'id': '3'},
]
lb.sync_adjustments = [
    {'date': '2022-01-15', 'date_obj': datetime(2022, 1, 15), 'offsets': {'day_p1': 10.0}, 'id': 'adj1'}
]

print("--- Testing get_paginated_data ---")
pages = lb.get_paginated_data()
for p in pages:
    print(f"Page {p['page_number']} Carried Forward: {p['carried_forward']['day_p1']}")
    # Entry 1 (Jan) total: 1.0
    # Adjustment (Jan 15): +10.0
    # Entry 2 (Feb) total: 1.0 + 10.0 + 2.0 = 13.0
    # Entry 3 (Mar) total: 13.0 + 3.0 = 16.0
    
from dashboard import LogbookDashboard
print("\n--- Testing LogbookDashboard ---")
stats = LogbookDashboard.get_summary(lb.history, sync_adjustments=lb.sync_adjustments)
print(f"Total P1 Day: {stats['day_p1']}") # Should be 1+2+3 + 10 = 16.0

lb.save_data()
os.remove("data/logbook_test_sync.json")
