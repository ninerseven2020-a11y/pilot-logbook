import math
import pandas as pd
import json
import os
from datetime import datetime, time
import uuid
try:
    from google import genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False
    # Attempt auto-install if missing (Self-Repair)
    try:
        import subprocess
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "google-genai"])
        from google import genai
        HAS_GENAI = True
        print("[SYSTEM] google-genai installed successfully via self-repair.")
    except:
        print("[SYSTEM] google-genai missing and auto-install failed.")

import requests

class CAD407Logbook:
    def __init__(self, user_id=None, pilot_name="L CHIANG"):
        self.user_id = user_id
        self.pilot_name = pilot_name
        self.history = []
        self.lines_per_page = 18
        self.pages_per_book = 78
        self.sync_adjustments = []
        
        # Mapping of internal keys to possible Excel header synonyms
        # Load from file if exists, otherwise use defaults
        # Define data_dir first
        self.data_dir = os.getenv("LOGBOOK_DATA_DIR", "data")
        self.synonyms_file = os.path.join(self.data_dir, "synonyms.json")
        self.COLUMN_MAP = self.load_synonyms()

        # Aircraft Type Database (FW = Fixed Wing, HELI = Helicopter)
        self.AIRCRAFT_DB = {
            'EC175': 'HELI', 'H175': 'HELI', 'AS332': 'HELI', 'AS335': 'HELI', 'EC155': 'HELI', 'EC135': 'HELI',
            'R44': 'HELI', 'R22': 'HELI', 'H269': 'HELI', 'HEA': 'HELI', 'SIM': 'HELI',
            'CL605': 'FW', 'DA42': 'FW', 'C172': 'FW', 'C152': 'FW', 'PA28': 'FW', 'B737': 'FW', 'A320': 'FW',
            'ZLIN': 'FW', 'DA40': 'FW', 'BE20': 'FW', 'B350': 'FW', 'JS31': 'FW', 'TB10': 'FW'
        }

        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
        if user_id:
            self.storage_file = os.path.join(self.data_dir, f"logbook_{user_id}.json")
        else:
            self.storage_file = os.path.join(self.data_dir, "logbook_data.json")
            
        self.load_data()

    def load_synonyms(self):
        """Loads synonyms from JSON file or returns defaults."""
        defaults = {
            'DEP': ['DATE', 'FLIGHT DATE', 'DATE OF FLIGHT'],
            'FLT_SN': ['FLT S/N', 'S/N', 'FLIGHT SN', 'FLIGHT_ID', 'SERIAL', 'Depart. S/N', 'DEPART. S/N'],
            'AC_TYPE': ['AC TYPE', 'AIRCRAFT TYPE', 'TYPE', 'AC Type'],
            'AC_REG': ['AC REG', 'REGISTRATION', 'REG', 'Reg.', 'Reg'],
            'CAPTAIN': ['CAPTAIN', 'PIC', 'CAPT'],
            'COPILOT': ['COPILOT', 'FO', 'SIC'],
            'CAPACITY': ['CAPACITY', 'ROLE', 'CAPACITY'],
            'ROUTE': ['ROUTE', 'SECTOR', 'JOURNEY'],
            'DAY_P1': ['DAY P1', 'P1 DAY'],
            'DAY_P1US': ['DAY P1 (U/S)', 'DAY P1US'],
            'DAY_P2': ['DAY P2', 'P2 DAY'],
            'DAY_DUAL': ['DAY DUAL', 'DUAL'],
            'NIGHT_P1': ['NIGHT P1', 'P1 NIGHT'],
            'NIGHT_P1US': ['NIGHT P1 (U/S)', 'NIGHT P1US'],
            'NIGHT_P2': ['NIGHT P2', 'P2 NIGHT'],
            'NIGHT_DUAL': ['NIGHT DUAL', 'DUAL NIGHT'],
            'INSTRUMENT': ['INSTRUMENT', 'IFR', 'IF'],
            'SIM_DAY': ['SIM DAY', 'SIMULATOR DAY'],
            'SIM_NIGHT': ['SIM NIGHT', 'SIMULATOR NIGHT'],
            'REMARKS': ['REMARKS', 'NOTES'],
            'ATD': ['ATD', 'DEP', 'DEP TIME'],
            'ATA': ['ATA', 'ARR', 'ARR TIME'],
            'TOTAL': ['TOTAL', 'TOTAL TIME', 'TOTAL HOURS'],
            'TAKEOFF': ['TAKEOFF', 'TO', 'No. of Takeoff'],
            'LANDING': ['LANDING', 'LDG', 'No. of Landing', 'No. of Landings']
        }
        if os.path.exists(self.synonyms_file):
            try:
                with open(self.synonyms_file, 'r') as f:
                    stored = json.load(f)
                    # Merge stored with defaults to ensure new keys (ATD, ATA, etc.) are always present
                    for k, v in defaults.items():
                        if k not in stored:
                            stored[k] = v
                    return stored
            except:
                return defaults
        return defaults

    def save_synonyms(self):
        """Saves current COLUMN_MAP to JSON file."""
        with open(self.synonyms_file, 'w') as f:
            json.dump(self.COLUMN_MAP, f, indent=4)

    def update_synonyms(self, new_map):
        """Updates the internal COLUMN_MAP and saves to disk."""
        self.COLUMN_MAP = new_map
        self.save_synonyms()

    def save_data(self):
        """Serializes history and profile to JSON."""
        def encoder(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj
        
        payload = {
            'pilot_name': self.pilot_name,
            'history': self.history,
            'sync_adjustments': self.sync_adjustments
        }
        print(f"[DEBUG] Saving {len(self.history)} entries to {self.storage_file}")
        with open(self.storage_file, "w") as f:
            json.dump(payload, f, default=encoder)

    def detect_columns_exact(self, df):
        """Tier 1: Look for exact standard CAD407 headers."""
        exact_map = {}
        standard_headers = {
            'DEP': 'DATE',
            'FLT_SN': 'FLT S/N',
            'AC_TYPE': 'AIRCRAFT TYPE',
            'AC_REG': 'AIRCRAFT REG',
            'CAPTAIN': 'PIC NAME',
            'COPILOT': 'COPILOT NAME',
            'ROUTE': 'ROUTE',
            'TOTAL': 'TOTAL TIME',
            'TAKEOFF': 'T/O',
            'LANDING': 'LDG'
        }
        for key, header in standard_headers.items():
            if header in df.columns:
                exact_map[key] = header
        return exact_map

    def detect_columns_smart(self, df):
        """
        Tries Exact -> Synonyms -> AI. Returns (map, needs_confirmation).
        """
        # 1. TIER 1: Exact CAD407 Match
        exact_map = self.detect_columns_exact(df)
        
        # 2. TIER 2: Synonym Match
        synonym_map = self.detect_columns(df)
        
        # Combined map (Exact takes priority)
        final_map = {**synonym_map, **exact_map}
        
        # Check for critical missing columns
        critical_keys = ['DEP', 'AC_TYPE', 'AC_REG', 'TOTAL']
        missing_critical = [k for k in critical_keys if not final_map.get(k)]
        
        # If all critical keys found via Tier 1 or 2, we are relatively confident
        if not missing_critical:
            return final_map, False 
            
        # 3. TIER 3: AI DATA SCAN (Hypothesis)
        print(f"[SMART ENGINE] Missing critical columns {missing_critical}. Engaging AI Brain...")
        try:
            ai_map = self.detect_columns_llm(df) # This already uses sample data
            if ai_map:
                # Merge AI guesses
                for k, v in ai_map.items():
                    if k not in final_map or not final_map[k]:
                        final_map[k] = v
                return final_map, True # REQUIRES CONFIRMATION
        except Exception as e:
            print(f"[SMART ENGINE] AI error: {e}")
            
        return final_map, len(missing_critical) > 0 # Confirm if anything is missing

    def detect_columns_llm(self, df):
        """
        Uses an LLM to map Excel columns to internal keys using headers and sample data.
        """
        sample_rows = df.head(5).to_dict(orient='records')
        columns_list = list(df.columns)
        
        prompt = f"""
You are an aviation logbook data expert. Map the following Excel columns to our internal logbook keys.
INTERNAL KEYS: {list(self.COLUMN_MAP.keys())}
EXCEL COLUMNS: {columns_list}

SAMPLE DATA (First 5 rows):
{json.dumps(sample_rows, indent=2, default=str)}

RULES:
1. Return ONLY a JSON object.
2. Keys must be from the INTERNAL KEYS list.
3. Values must be from the EXCEL COLUMNS list.
4. Use the SAMPLE DATA to help identify columns (e.g. if a column 'D' contains aircraft registrations like 'B-LVZ', map it to 'AC_REG').
5. If unsure, omit the key.
6. Do not include any text, markdown blocks, or explanation.
"""
        # 1. Try Gemini first (Production / Live App)
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            print("[SMART ENGINE] Using Google Gemini API...")
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                
                # Model fallback list for google-genai
                model_names = ['gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-1.5-pro']
                last_error = None
                
                for m_name in model_names:
                    try:
                        print(f"[SMART ENGINE] Trying model: {m_name}")
                        response = client.models.generate_content(
                            model=m_name,
                            contents=prompt
                        )
                        text = response.text
                        if "```json" in text:
                            text = text.split("```json")[1].split("```")[0]
                        elif "```" in text:
                            text = text.split("```")[1].split("```")[0]
                        return json.loads(text.strip())
                    except Exception as e:
                        last_error = str(e)
                        if "404" in last_error:
                            print(f"[SMART ENGINE] Model {m_name} not found (404).")
                            continue
                        raise e
                
                if last_error:
                    print(f"[SMART ENGINE] All models failed. Last error: {last_error}")

            except Exception as e:
                print(f"[SMART ENGINE] Gemini error: {e}")

        # 2. Try Local Ollama (Development / Aberdeen)
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3")
        
        print(f"[SMART ENGINE] Attempting local Ollama ({ollama_model})...")
        try:
            import requests
            response = requests.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                },
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                return json.loads(result.get('response', '{}'))
        except Exception as e:
            print(f"[SMART ENGINE] Ollama error: {e}")

        return None

    def load_data(self):
        """Loads history and profile from JSON. Self-heals if corrupted."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r") as f:
                    content = f.read().strip()
                    if not content:
                        self.history = []
                        return
                    data = json.loads(content)
                    if isinstance(data, dict):
                        self.pilot_name = data.get('pilot_name', self.pilot_name)
                        self.history = data.get('history', [])
                        self.sync_adjustments = data.get('sync_adjustments', [])
                        
                        # Ensure all entries have an ID
                        ids_added = False
                        for entry in self.history:
                            if 'id' not in entry:
                                import uuid
                                entry['id'] = str(uuid.uuid4())
                                ids_added = True
                        
                        if ids_added:
                            self.save_data()
                        self.normalize_history()
                    else:
                        self.history = data
            except (json.JSONDecodeError, ValueError) as e:
                print(f"[SYSTEM] Logbook file corrupted ({e}). Resetting to clean slate.")
                self.history = []
                self.save_data()
            except Exception as e:
                print(f"[SYSTEM] Error loading data for user {self.user_id}: {e}")
                self.history = []

    def normalize_history(self):
        """Ensures all entries in history have consistent keys for rendering and correct rounding."""
        hour_cols = ['day_p1', 'day_p1us', 'day_p2', 'day_dual', 'night_p1', 'night_p1us', 'night_p2', 'night_dual', 'inst_flying', 'sim_time']
        
        for entry in self.history:
            # Always recompute ac_category from the database
            entry['ac_category'] = self.get_ac_category(entry.get('ac_type'))

            # Key Mapping (Manual Entry keys -> Engine/Rendering keys)
            mapping = {
                'type': 'ac_type',
                'day_put': 'day_dual',
                'night_put': 'night_dual',
                'instr': 'inst_flying',
                'sim': 'sim_time'
            }
            
            for old_key, new_key in mapping.items():
                if old_key in entry:
                    if new_key not in entry or entry[new_key] == 0:
                        entry[new_key] = entry.get(old_key)

            # APPLY ROUNDING to all hour columns to ensure consistency
            for col in hour_cols:
                if col in entry:
                    entry[col] = self.cad_round_up(entry[col])

            # Date string for rendering (Oct 31 format)
            if 'date_obj' in entry:
                try:
                    dt_val = entry['date_obj']
                    if isinstance(dt_val, str):
                        dt = datetime.fromisoformat(dt_val.replace('Z', '+00:00'))
                        entry['date_obj'] = dt # Convert string back to datetime object in memory
                    else:
                        dt = dt_val
                    entry['date_str'] = dt.strftime('%b %d')
                except:
                    pass

            # Migration and Normalization: flight_nature -> label, organization -> operator
            if 'flight_nature' in entry:
                if not entry.get('label'):
                    entry['label'] = entry['flight_nature']
                del entry['flight_nature']
            
            if 'organization' in entry:
                if not entry.get('operator'):
                    entry['operator'] = entry['organization']
                del entry['organization']

            # Ensure operator and label exist
            if 'operator' not in entry:
                entry['operator'] = 'Default'
            if 'label' not in entry:
                # Fallback for opening entries from remarks
                if entry.get('is_opening') and entry.get('remarks'):
                    entry['label'] = entry['remarks']
                else:
                    entry['label'] = 'Default'

    def get_ac_category(self, ac_type):
        """Determines if aircraft is FW or HELI based on the database."""
        if not ac_type: return 'FW' # Default
        ac_type_upper = str(ac_type).upper().strip()
        
        # Check database
        if ac_type_upper in self.AIRCRAFT_DB:
            return self.AIRCRAFT_DB[ac_type_upper]
        
        # Heuristics
        if any(h in ac_type_upper for h in ['EC', 'AS', 'H1', 'BELL', 'ROBINSON', 'R22', 'R44', 'R66']):
            return 'HELI'
        
        return 'FW' # Default for others

    def cad_round_up(self, value):
        """Strictly rounds up to the nearest 0.1 per HKCAD instructions."""
        if not value or value == 0:
            return 0.0
            
        # Handle time objects (Excel time format)
        if isinstance(value, time):
            decimal_hours = value.hour + (value.minute / 60.0)
            # Round to 9 decimals to handle precision, then ceil to 0.1
            return math.ceil(round(decimal_hours, 9) * 10) / 10.0
            
        # Handle string "HH:MM"
        if isinstance(value, str) and ':' in value:
            try:
                parts = value.split(':')
                if len(parts) >= 2:
                    decimal_hours = int(parts[0]) + (int(parts[1]) / 60.0)
                    return math.ceil(round(decimal_hours, 9) * 10) / 10.0
            except ValueError:
                pass

        try:
            # Crucial: We must NOT round to 2 decimals first, as 0.801 should round UP to 0.9.
            # Using 9 decimals to avoid floating point noise (e.g. 0.300000000000004 -> 0.3)
            return math.ceil(round(float(value), 9) * 10) / 10.0
        except (ValueError, TypeError):
            return 0.0

    def add_entry(self, entry):
        """
        Simple addition with basic deduplication (exact matches only).
        """
        if not entry: return "ERROR", "Invalid entry."
        
        # Simple Deduplication: If we have an exact S/N match, check for missing Takeoff/Landing data
        flight_id = str(entry.get('flight_id', '')).strip()
        if flight_id and flight_id not in ['', 'None', 'nan', '---', 'Unknown']:
            for h in self.history:
                if str(h.get('flight_id', '')).strip() == flight_id:
                    # Always update operator/label if we have new non-default values
                    updated_meta = False
                    if entry.get('operator') and entry.get('operator') != 'Default':
                        h['operator'] = entry['operator']
                        if 'metadata' not in h: h['metadata'] = {}
                        h['metadata']['operator'] = entry['operator']
                        updated_meta = True
                    if entry.get('label') and entry.get('label') != 'Default':
                        h['label'] = entry['label']
                        if 'metadata' not in h: h['metadata'] = {}
                        h['metadata']['label'] = entry['label']
                        updated_meta = True

                    # Selective Update: If existing record has no T/O or Ldg, but the new one does, patch it
                    new_to = int(entry.get('takeoff', 0))
                    new_ldg = int(entry.get('landing', 0))
                    
                    if (h.get('takeoff', 0) == 0 and h.get('landing', 0) == 0) and (new_to > 0 or new_ldg > 0):
                        h['takeoff'] = new_to
                        h['landing'] = new_ldg
                        print(f"[DEBUG] [ENGINE] Patched T/O and Landing for flight {flight_id}")
                        return "UPDATED", "Flight updated with T/O and Landing data."
                    
                    if updated_meta:
                        return "UPDATED", "Flight metadata updated."
                        
                    print(f"[DEBUG] [ENGINE] Skipping DUPLICATE flight (S/N match): {flight_id}")
                    return "SKIPPED", "Duplicate flight."

        # If no S/N, check (Date + Reg + Times)
        if not flight_id:
            for h in self.history:
                if (h.get('date_str') == entry.get('date_str') and 
                    h.get('reg') == entry.get('reg') and 
                    h.get('dep_time') == entry.get('dep_time')):
                    print(f"[DEBUG] [ENGINE] Skipping DUPLICATE flight (Time/Reg match): {entry.get('date_str')} {entry.get('reg')}")
                    return "SKIPPED", "Duplicate flight."

        if 'id' not in entry:
            import uuid
            entry['id'] = str(uuid.uuid4())
            
        self.history.append(entry)
        return "ADDED", "New flight added."

        # 3. OVERLAP CHECK (Collision Detection)
        # If no exact match, check if the times overlap with ANY existing flight
        if not match:
            try:
                new_dep = entry.get('dep_time')
                new_arr = entry.get('arr_time')
                new_date = str(entry.get('date_obj'))
                
                def to_min(t_str):
                    if not t_str or ':' not in t_str: return None
                    h, m = map(int, t_str.split(':'))
                    return h * 60 + m

                new_start = to_min(new_dep)
                new_end = to_min(new_arr)
                
                if new_start is not None and new_end is not None:
                    if new_end < new_start: new_end += 1440 # Midnight cross
                    
                    for h in self.history:
                        if str(h.get('date_obj')) == new_date:
                            h_start = to_min(h.get('dep_time'))
                            h_end = to_min(h.get('arr_time'))
                            if h_start is not None and h_end is not None:
                                if h_end < h_start: h_end += 1440
                                
                                # Standard overlap formula: (StartA < EndB) and (EndA > StartB)
                                if (new_start < h_end) and (new_end > h_start):
                                    msg = f"TIME OVERLAP: New flight ({new_dep}-{new_arr}) conflicts with an existing flight ({h.get('dep_time')}-{h.get('arr_time')}) on {new_date}."
                                    print(f"[ENGINE] BLOCKING: {msg}")
                                    return "OVERLAP", msg
            except Exception as e:
                print(f"[ENGINE] Overlap check failed: {e}")

        if match:
            print(f"[ENGINE] Merging data into existing flight: {entry.get('flight_id') or entry.get('reg')}")
            # Merge fields: take the non-zero or non-empty value
            for k, v in entry.items():
                if k in ['id', 'date_obj', 'date_str']: continue
                
                existing_val = match.get(k)
                if isinstance(v, (int, float)):
                    if not existing_val or existing_val == 0:
                        match[k] = v
                elif isinstance(v, str):
                    if not existing_val or existing_val in ["", "---", "Default", "Unknown"]:
                        match[k] = v
            return "MERGED", "Merged into existing flight."
        else:
            # Not a match, add as new
            if 'id' not in entry:
                import uuid
                entry['id'] = str(uuid.uuid4())
            self.history.append(entry)
            return "ADDED", "New flight added."

    def add_opening_balance(self, ac_type, year=1900, day_p1=0, day_p1us=0, day_p2=0, day_dual=0, 
                            night_p1=0, night_p1us=0, night_p2=0, night_dual=0, 
                            inst=0, sim=0, label="Opening Balance", operator="Default"):
        entry = {
            'date_obj': datetime(year, 1, 1),
            'date_str': str(year),
            'ac_type': ac_type,
            'ac_category': self.get_ac_category(ac_type),
            'reg': "---",
            'pic': "---",
            'copilot': "---",
            'capacity': "---",
            'route': "",
            'day_p1': float(day_p1), 'day_p1us': float(day_p1us), 'day_p2': float(day_p2), 'day_dual': float(day_dual),
            'night_p1': float(night_p1), 'night_p1us': float(night_p1us), 'night_p2': float(night_p2), 'night_dual': float(night_dual),
            'inst_flying': float(inst), 'sim_time': float(sim),
            'label': label,
            'is_opening': True,
            'is_adjustment': False,
            'operator': operator,
            'id': str(uuid.uuid4())
        }
        self.history.append(entry)
        self.save_data()

    def delete_entry(self, entry_id):
        self.history = [h for h in self.history if h.get('id') != entry_id]
        self.save_data()

    def update_entry(self, entry_id, updated_data):
        for i, entry in enumerate(self.history):
            if entry.get('id') == entry_id:
                # Update fields while preserving ID and certain immutable fields
                for key, value in updated_data.items():
                    if key not in ['id', 'date_obj']:
                        entry[key] = value
                
                # Re-parse date if provided in updated_data
                date_val = updated_data.get('date') or updated_data.get('date_str')
                if date_val:
                    try:
                        if len(str(date_val)) == 4 and str(date_val).isdigit():
                            # It's a year (opening balance)
                            year = int(date_val)
                            entry['date_obj'] = datetime(year, 1, 1)
                            entry['date_str'] = str(year)
                            entry['is_opening'] = True
                        else:
                            # Try YYYY-MM-DD
                            try:
                                entry['date_obj'] = datetime.strptime(str(date_val), "%Y-%m-%d")
                            except:
                                # Try common display formats if needed, or keep existing
                                pass
                            
                            if 'date_obj' in entry:
                                if entry.get('is_opening'):
                                    entry['date_str'] = str(entry['date_obj'].year)
                                else:
                                    entry['date_str'] = entry['date_obj'].strftime('%b %d')
                    except Exception as e:
                        print(f"[UPDATE ENTRY] Date parse error: {e}")
                break
        self.save_data()

    def batch_update_entries(self, ids, updates):
        """Update multiple entries at once and save only once."""
        id_set = set(ids)
        updated_count = 0
        for entry in self.history:
            if entry.get('id') in id_set:
                for key, value in updates.items():
                    if key not in ['id', 'date_obj']:
                        entry[key] = value
                
                if 'date' in updates:
                    try:
                        entry['date_obj'] = datetime.strptime(updates['date'], "%Y-%m-%d")
                        entry['date_str'] = entry['date_obj'].strftime('%b %d')
                    except:
                        pass
                updated_count += 1
        
        if updated_count > 0:
            self.save_data()
        return updated_count

    def add_manual_adjustment(self, column_name, value, remarks="Manual Correction"):
        adjustment = {
            'date_obj': datetime.now(),
            'date_str': "ADJUST",
            'ac_type': "ADJ",
            'reg': "---",
            'pic': "---",
            'copilot': "---",
            'capacity': "---",
            'route': "Adjustment",
            'day_p1': 0, 'day_p1us': 0, 'day_p2': 0, 'day_dual': 0,
            'night_p1': 0, 'night_p1us': 0, 'night_p2': 0, 'night_dual': 0,
            'inst_flying': 0, 'sim_time': 0,
            'remarks': remarks,
            'is_opening': False,
            'is_adjustment': True,
            'operator': "Default",
            'label': "Adjustment"
        }
        adjustment[column_name] = float(value)
        self.history.append(adjustment)
        self.save_data()

    def add_sync_adjustment(self, date_str, offsets, remarks="Sync with Paper"):
        """
        Adds a hidden adjustment point.
        offsets: dict like {'day_p1': 0.5, 'night_p1': -0.2}
        """
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        except:
            date_obj = datetime.now()

        # Round offsets to 1 decimal place
        rounded_offsets = {k: round(float(v), 1) for k, v in offsets.items() if abs(float(v)) > 0.001}

        adjustment = {
            'id': str(uuid.uuid4()),
            'date': date_str,
            'date_obj': date_obj,
            'offsets': rounded_offsets,
            'remarks': remarks
        }
        self.sync_adjustments.append(adjustment)
        # Sort adjustments by date for easier calculation later
        self.sync_adjustments.sort(key=lambda x: x['date_obj'])
        self.save_data()
        return adjustment

    def delete_sync_adjustment(self, adj_id):
        self.sync_adjustments = [a for a in self.sync_adjustments if a.get('id') != adj_id]
        self.save_data()

    def detect_columns(self, df):
        """
        Scans dataframe columns and maps them to internal keys based on synonyms.
        Uses sample data to validate mapping (e.g. no decimals for landings).
        """
        df_columns = df.columns
        detected_map = {}
        all_cols = [str(col).strip() for col in df_columns]
        
        # Explicitly ignore these confusing columns (that aren't IDs)
        IGNORE_LIST = ['ARRIVAL S/N', 'ARR S/N']
        
        print(f"[ENGINE] Analyzing Columns: {all_cols}")
        
        # Track used columns (original names)
        used_cols = set()
        for col in all_cols:
            if col.upper() in IGNORE_LIST:
                used_cols.add(col)
                print(f"[ENGINE] Blacklisted: {col}")

        for key, synonyms in self.COLUMN_MAP.items():
            match_found = False
            
            # 1. Look for Exact Match
            for col in all_cols:
                if col in used_cols and key not in ['CAPTAIN', 'COPILOT']: continue
                
                col_upper = col.upper()
                if any(syn.upper() == col_upper for syn in synonyms):
                    detected_map[key] = col
                    used_cols.add(col)
                    match_found = True
                    break
            
            # 2. Look for Partial Match (aggressive)
            if not match_found:
                for col in all_cols:
                    if col in used_cols and key not in ['CAPTAIN', 'COPILOT']: continue
                    col_upper = col.upper()
                    if any((len(col_upper) >= 3 and syn.upper() in col_upper) or 
                           (len(syn.upper()) >= 3 and col_upper in syn.upper()) for syn in synonyms):
                        # SANITY CHECK: If mapping to TAKEOFF or LANDING, ensure data is integer-like
                        if key in ['TAKEOFF', 'LANDING']:
                            # Check first 5 non-null values
                            sample = df[col].dropna().head(5).tolist()
                            is_decimal = False
                            for val in sample:
                                try:
                                    f_val = float(val)
                                    if f_val % 1 != 0: # Has decimal part
                                        is_decimal = True
                                        break
                                except: pass
                            
                            if is_decimal:
                                print(f"[ENGINE] Rejected '{col}' for {key} - detected decimals.")
                                continue # Skip this column for this key
                                
                        detected_map[key] = col
                        used_cols.add(col)
                        match_found = True
                        break
            
            if not match_found:
                detected_map[key] = None
        
        print(f"[ENGINE] Mapped columns: { {k: v for k, v in detected_map.items() if v} }")
        return detected_map

    def parse_ias_row(self, row, operator="Default", label="Default", col_map=None):
        if not col_map:
            col_map = {k: v[0] for k, v in self.COLUMN_MAP.items()}

        def get_val(key, default=0.0):
            col_name = col_map.get(key)
            if not col_name: return default
            val = row.get(col_name)
            return default if pd.isna(val) else val

        # 1. Date Handling
        dep_val = row.get(col_map.get('DEP'))
        if pd.isna(dep_val):
            # This is fine now, app.py will handle carryover
            dep_dt = None
        else:
            try:
                if isinstance(dep_val, datetime):
                    dep_dt = dep_val
                else:
                    dep_dt = pd.to_datetime(dep_val).to_pydatetime()
            except:
                dep_dt = None

        # 2. Extract EVERYTHING into metadata (audit trail)
        metadata = {
            'operator': operator,
            'label': label
        }
        for col in row.index:
            if not pd.isna(row[col]):
                val = row[col]
                # Convert time-like objects to strings for metadata storage
                if isinstance(val, (datetime, pd.Timestamp)):
                    val = val.strftime('%Y-%m-%d %H:%M')
                metadata[str(col)] = val

                                # 3. Required Fields Extraction
        is_sim = str(get_val('AC_REG', '')).strip() == "B-LVZ"

        # 3. GFS Fleet Special Handling (B-LVA to B-LVJ)
        reg_raw = str(get_val('AC_REG', '')).strip().upper()
        gfs_fleet = ['B-LVA', 'B-LVB', 'B-LVC', 'B-LVD', 'B-LVE', 'B-LVF', 'B-LVG', 'B-LVH', 'B-LVI', 'B-LVJ']
        is_gfs = any(r in reg_raw for r in gfs_fleet)
        
        route_raw = str(get_val('ROUTE', '')).strip()
        remarks_raw = str(get_val('REMARKS', '')).strip()
        
        final_route = route_raw
        final_remarks = remarks_raw
        
        if is_gfs:
            # NOTE: We no longer force "VHHH VHHH" here to preserve original data in Manage History.
            # Standardization is now handled by the UI/Preview layer only.
            
            # 2. Extract Mission/Training info from Route
            import re
            # Look for MCC, ITR, SAR, CASEVAC, NVG, LPC, OPC, CHECK, etc.
            patterns = [
                r'(MCC\s?\d+)', r'(ITR\s?\d+)', r'(SAR)', r'(CASEVAC)', 
                r'(NVG)', r'(LPC)', r'(OPC)', r'(CHECK)', r'(TRAINING)',
                r'(FIRE)', r'(POLICE)', r'(MOUNTAIN)', r'(MEDEVAC)'
            ]
            extracted = []
            for p in patterns:
                m = re.search(p, route_raw.upper())
                if m:
                    extracted.append(m.group(1))
            
            if extracted:
                mission_prefix = f"[{', '.join(extracted)}]"
                if final_remarks:
                    final_remarks = f"{mission_prefix} {final_remarks}"
                else:
                    final_remarks = mission_prefix
        
        # 3. Required Fields Extraction (Simple)
        def simple_time(val):
            if isinstance(val, (datetime, pd.Timestamp)):
                return val.strftime('%H:%M')
            return str(val) if not pd.isna(val) else ""

        pic_raw = str(get_val('CAPTAIN', '')).strip()
        copilot_raw = str(get_val('COPILOT', '')).strip()
        pic_final = "SELF" if pic_raw.upper() == self.pilot_name.upper() else pic_raw
        copilot_final = "SELF" if copilot_raw.upper() == self.pilot_name.upper() else copilot_raw

        entry = {
            'flight_id': str(get_val('FLT_SN', '')).strip(),
            'date_obj': dep_dt.to_pydatetime() if hasattr(dep_dt, 'to_pydatetime') else dep_dt,
            'date_str': dep_dt.strftime('%b %d') if dep_dt else "",
            'ac_type': "SIM" if is_sim else str(get_val('AC_TYPE', '')).strip(),
            'ac_category': 'HELI' if is_sim else self.get_ac_category(get_val('AC_TYPE', '')),
            'reg': reg_raw if not is_sim else f"GFS01 {reg_raw}",
            'pic': pic_final,
            'copilot': copilot_final,
            'capacity': str(get_val('CAPACITY', '')).strip(),
            'route': final_route,
            'day_p1': self.cad_round_up(get_val('DAY_P1')),
            'day_p1us': self.cad_round_up(get_val('DAY_P1US')),
            'day_p2': self.cad_round_up(get_val('DAY_P2')),
            'day_dual': self.cad_round_up(get_val('DAY_DUAL')),
            'night_p1': self.cad_round_up(get_val('NIGHT_P1')),
            'night_p1us': self.cad_round_up(get_val('NIGHT_P1US')),
            'night_p2': self.cad_round_up(get_val('NIGHT_P2')),
            'night_dual': self.cad_round_up(get_val('NIGHT_DUAL')),
            'inst_flying': self.cad_round_up(get_val('INSTRUMENT')),
            'sim_time': self.cad_round_up(float(get_val('SIM_DAY', 0)) + float(get_val('SIM_NIGHT', 0))) if is_sim else 0.0,
            'remarks': final_remarks,
            'dep_time': simple_time(get_val('ATD')),
            'arr_time': simple_time(get_val('ATA')),
            'total_time': self.cad_round_up(get_val('TOTAL', 0.0)),
            'takeoff': int(float(get_val('TAKEOFF', 0))),
            'landing': int(float(get_val('LANDING', 0))),
            'is_opening': False,
            'is_adjustment': False,
            'operator': operator,
            'label': label,
            'metadata': metadata,
            'id': str(uuid.uuid4())
        }
        return entry
        return entry

    def has_partial_dates(self, df, col_map):
        """Checks if any dates in the DEP column appear to be partial (missing year)."""
        dep_col = col_map.get('DEP')
        if not dep_col or dep_col not in df.columns:
            return False
            
        # Sample the first few rows to check for string-based partial dates
        # e.g., '28-Jan' vs '2024-01-28'
        for val in df[dep_col].dropna().head(20):
            if isinstance(val, str):
                # If it's a string, try standard parsing. If it fails, it's likely partial.
                try:
                    dt = pd.to_datetime(val)
                    if pd.isna(dt):
                        return True
                except:
                    return True
        return False

    def get_paginated_data(self, start_page=1, date_from=None, date_to=None):
        if not self.history:
            print("[PREVIEW] History is empty. Returning empty list.")
            return []
            
        print(f"[PREVIEW] Generating pages for {len(self.history)} entries starting at page {start_page}...")
        
        sorted_data = sorted(self.history, key=lambda x: x['date_obj'])
        
        # Columns to track for totals
        total_cols = ['day_p1', 'day_p1us', 'day_p2', 'day_dual', 
                      'night_p1', 'night_p1us', 'night_p2', 'night_dual', 
                      'inst_flying', 'sim_time']
        
        running_totals = {col: 0.0 for col in total_cols}
        
        filtered_data = []
        for x in sorted_data:
            d = x['date_obj']
            # If before date_from, skip adding to visible rows but accumulate in running_totals
            if date_from and d < date_from:
                for col in total_cols:
                    running_totals[col] += float(x.get(col, 0))
                continue
                
            # If after date_to, completely skip
            if date_to and d > date_to:
                continue
                
            filtered_data.append(x)
            
        # Prepare adjustments: sort by date
        sorted_adjustments = sorted(self.sync_adjustments, key=lambda x: x['date_obj'])
        for adj in sorted_adjustments:
            if isinstance(adj['date_obj'], str):
                adj['date_obj'] = datetime.fromisoformat(adj['date_obj'].replace('Z', '+00:00'))

        # Split adjustments into "Initial" (before date_from) and "Timeline" (after date_from)
        initial_adjustments = []
        timeline_adjustments = []
        if date_from:
            for adj in sorted_adjustments:
                if adj['date_obj'] < date_from:
                    initial_adjustments.append(adj)
                else:
                    timeline_adjustments.append(adj)
        else:
            timeline_adjustments = sorted_adjustments

        # Apply initial adjustments to running totals
        for adj in initial_adjustments:
            for col, offset in adj.get('offsets', {}).items():
                if col in running_totals:
                    running_totals[col] += float(offset)

        pages = []
        
        # Group by Year-Month
        from itertools import groupby
        grouped = groupby(filtered_data, key=lambda x: (x['date_obj'].year, x['date_obj'].month))
        
        current_page_entries = []
        page_brought_forward = running_totals.copy()
        
        # Keep track of which timeline adjustments have been applied
        adj_idx = 0
        
        def start_new_page():
            nonlocal current_page_entries, page_brought_forward
            if not current_page_entries:
                return
                
            page_num = ((start_page + len(pages) - 1) % self.pages_per_book) + 1
            
            # Calculate carried forward for this page
            page_carried_forward = running_totals.copy()
            
            # Determine Year for the page header
            year = ""
            for entry in current_page_entries:
                if 'date_obj' in entry:
                    year = entry['date_obj'].year
                    break
            
            # Find last valid date on page for adjustment check
            last_date = None
            for e in reversed(current_page_entries):
                if 'date_obj' in e:
                    last_date = e['date_obj']
                    break
            
            pages.append({
                'page_number': page_num,
                'year': year,
                'entries': current_page_entries,
                'brought_forward': page_brought_forward.copy(),
                'carried_forward': page_carried_forward,
                'grand_total_1_8': sum(page_carried_forward[col] for col in total_cols[:8]),
                'has_adjustments': any(adj['date_obj'] <= last_date for adj in sorted_adjustments) if last_date else False
            })
            current_page_entries = []
            page_brought_forward = running_totals.copy()

        for (year, month), month_entries in grouped:
            month_entries = list(month_entries)
            month_totals = {col: 0.0 for col in total_cols}
            
            for entry in month_entries:
                # Apply any adjustments that should occur before or on this entry's date
                while adj_idx < len(timeline_adjustments) and timeline_adjustments[adj_idx]['date_obj'] <= entry['date_obj']:
                    for col, offset in timeline_adjustments[adj_idx].get('offsets', {}).items():
                        if col in running_totals:
                            running_totals[col] = round(running_totals[col] + float(offset), 1)
                    adj_idx += 1

                if len(current_page_entries) >= self.lines_per_page:
                    start_new_page()
                
                current_page_entries.append(entry)
                for col in total_cols:
                    val = float(entry.get(col, 0))
                    running_totals[col] = round(running_totals[col] + val, 1)
                    month_totals[col] = round(month_totals[col] + val, 1)
            
            # After month entries, check if any remaining adjustments for this month should be applied
            # (In case there are adjustments on dates with no flights)
            # We'll just let them be picked up by the next month's first entry or at the end
            
            # After month entries, add a Monthly Total row
            if year != 1900:
                month_name = month_entries[0]['date_obj'].strftime('%B').upper()
                monthly_total_entry = {
                    'date_str': f"TOTALS FOR {month_name} {year}",
                    'is_monthly_total': True,
                    **month_totals
                }
                
                if len(current_page_entries) >= self.lines_per_page:
                    start_new_page()
                current_page_entries.append(monthly_total_entry)
            
            start_new_page()

        # Apply any remaining adjustments
        while adj_idx < len(timeline_adjustments):
            for col, offset in timeline_adjustments[adj_idx].get('offsets', {}).items():
                if col in running_totals:
                    running_totals[col] += float(offset)
            adj_idx += 1

        if current_page_entries:
            start_new_page()
            
        return pages