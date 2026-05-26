import json
import os

LOGBOOK_PATH = "/Users/leonardchiang/Documents/Projects/Logbook/data/logbook_1.json"

# Comprehensive list of keys to scrub from metadata
SCRUB_KEYS = {
    'DATE', 'AIRCRAFT TYPE', 'AIRCRAFT REG', 'REGISTRATION', 'REG', 'AC REG', 'A/C REG', 'A/C_REG', 'TAIL NO',
    'PIC', 'COPILOT', 'CO-PILOT', 'CAPACITY', 'ROUTE', 'REMARKS',
    'DAY P1', 'DAY P1(U/S)', 'DAY P1US', 'DAY P2', 'DAY DUAL', 'DAY P/UT', 'DAY_P1', 'DAY_P1US', 'DAY_P2', 'DAY_DUAL',
    'NIGHT P1', 'NIGHT P1(U/S)', 'NIGHT P1US', 'NIGHT P2', 'NIGHT DUAL', 'NIGHT P/UT', 'NIGHT_P1', 'NIGHT_P1US', 'NIGHT_P2', 'NIGHT_DUAL',
    'IF', 'INST FLYING', 'SIM', 'SIM TIME', 'SIM_TIME', 'INSTRUMENT', 'INST_FLYING',
    'FLIGHT ID', 'FLIGHT SN', 'FLT_SN', 'FLIGHT_ID', 'REG NO', 'REGISTRATION NO',
    'DEP', 'DEP TIME', 'ARR', 'ARR TIME', 'TOTAL', 'TOTAL TIME', 'TOTAL_TIME', 'ARR_TIME', 'DEP_TIME',
    'OPERATOR', 'LABEL', 'AC_CATEGORY', 'AIRCRAFT_CATEGORY', 'ID', 'IS_OPENING', 'IS_ADJUSTMENT', 'DATE_OBJ', 'DATE_STR'
}

def cleanup():
    if not os.path.exists(LOGBOOK_PATH):
        print("Logbook not found.")
        return

    with open(LOGBOOK_PATH, 'r') as f:
        data = json.load(f)

    cleaned_count = 0
    flt_sn_removed = 0
    
    for entry in data.get('history', []):
        # 1. Remove flt_sn redundancy
        if 'flt_sn' in entry:
            if 'flight_id' not in entry or not entry['flight_id']:
                entry['flight_id'] = entry['flt_sn']
            del entry['flt_sn']
            flt_sn_removed += 1

        # 2. Scrub metadata
        metadata = entry.get('metadata', {})
        if not metadata:
            continue
            
        new_metadata = {}
        for k, v in metadata.items():
            if k.strip().upper() not in SCRUB_KEYS:
                new_metadata[k] = v
            else:
                cleaned_count += 1
        
        entry['metadata'] = new_metadata

    with open(LOGBOOK_PATH, 'w') as f:
        json.dump(data, f, indent=4)

    print(f"Cleanup complete.")
    print(f" - Standardized {flt_sn_removed} entries to flight_id.")
    print(f" - Removed {cleaned_count} redundant metadata entries.")

if __name__ == "__main__":
    cleanup()
