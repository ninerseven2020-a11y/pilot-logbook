import math
import pandas as pd
import json
import os
from datetime import datetime, time
import uuid
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

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
            'DEP': ['DEP', 'DATE', 'DEPARTURE', 'FLIGHT DATE', 'UTC DATE', 'MONTH/DATE', 'MONTH', 'DAY', 'DEP TIME', 'DEP_TIME', 'DEPARTURE TIME'],
            'FLT_SN': ['FLT S/N', 'SERIAL', 'S/N', 'FLIGHT NO', 'FLT NO', 'FLIGHT SN', 'FLT_SN', 'FLIGHT ID', 'FLIGHT_ID'],
            'AC_TYPE': ['AC TYPE', 'AIRCRAFT TYPE', 'TYPE', 'MODEL', 'A/C TYPE', 'AIRCRAFT MODEL'],
            'AC_REG': ['AC REG', 'REGISTRATION', 'REG', 'TAIL NO', 'AIRCRAFT REG', 'A/C REG', 'A/C_REG', 'REG NO', 'REGISTRATION NO', 'REG.'],
            'CAPTAIN': ['CAPTAIN', 'PIC', 'COMMANDER', 'PILOT IN COMMAND', 'P1 NAME', 'PILOT-IN-COMMAND', 'CAPT'],
            'COPILOT': ['COPILOT', 'FO', 'CO-PILOT', 'SIC', 'P2 NAME', 'CO-PILOT OR STUDENT', 'COPILOT NAME'],
            'CAPACITY': ['OPERATING CAPACITY', 'CAPACITY', 'ROLE', 'FUNCTION', "HOLDER'S OPERATING CAPACITY"],
            'ROUTE': ['ROUTE', 'FROM-TO', 'FROM/TO', 'SECTOR', 'JOURNEY'],
            'DAY_P1': ['DAY P1', 'P1 DAY', 'DAY PIC', 'P1', 'DAY_P1'],
            'DAY_P1US': ['DAY P1 (U/S)', 'DAY P1US', 'DAY P1 US', 'DAY PICUS', 'P1(U/S)', 'DAY_P1US'],
            'DAY_P2': ['DAY P2', 'P2 DAY', 'DAY SIC', 'DAY CO-PILOT', 'P2/P2X', 'P2', 'DAY_P2'],
            'DAY_DUAL': ['DAY DUAL', 'DUAL DAY', 'INSTRUCTION DAY', 'P/UT', 'DUAL', 'DAY_DUAL', 'DAY P/UT'],
            'NIGHT_P1': ['NIGHT P1', 'P1 NIGHT', 'NIGHT PIC', 'P1.1', 'NIGHT_P1'],
            'NIGHT_P1US': ['NIGHT P1 (U/S)', 'NIGHT P1US', 'NIGHT P1 US', 'NIGHT PICUS', 'P1(U/S).1', 'NIGHT_P1US'],
            'NIGHT_P2': ['NIGHT P2', 'P2 NIGHT', 'NIGHT SIC', 'NIGHT CO-PILOT', 'P2/P2X.1', 'P2.1', 'NIGHT_P2'],
            'NIGHT_DUAL': ['NIGHT DUAL', 'DUAL NIGHT', 'INSTRUCTION NIGHT', 'P/UT.1', 'DUAL.1', 'NIGHT_DUAL', 'NIGHT P/UT'],
            'INSTRUMENT': ['INSTRUMENT', 'IFR', 'IF', 'INSTRUMENT TIME', 'INST FLYING', 'INST_FLYING'],
            'SIM_DAY': ['SIM DAY', 'SIMULATOR DAY', 'SIM P1 DAY'],
            'SIM_NIGHT': ['SIM NIGHT', 'SIMULATOR NIGHT', 'SIM P1 NIGHT'],
            'REMARKS': ['REMARKS', 'NOTES', 'COMMENTS', 'FLIGHT DETAILS'],
            'ARR': ['ARR', 'ARRIVAL', 'ARR TIME', 'ARRIVAL TIME', 'ARR_TIME'],
            'TOTAL': ['TOTAL', 'TOTAL TIME', 'TOTAL HOURS', 'BLOCK TIME', 'TOTAL_TIME']
        }
        if os.path.exists(self.synonyms_file):
            try:
                with open(self.synonyms_file, 'r') as f:
                    return json.load(f)
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
        with open(self.storage_file, "w") as f:
            json.dump(payload, f, default=encoder)

    def detect_columns_smart(self, df):
        """
        Tries standard detection first. If low confidence, tries LLM.
        """
        # Get standard mapping
        standard_map = self.detect_columns(df.columns)
        
        # Check if critical columns were found
        critical_keys = ['DEP', 'AC_TYPE', 'AC_REG', 'TOTAL']
        found_critical = sum(1 for k in critical_keys if k in standard_map and standard_map[k] in df.columns)
        
        if found_critical >= 3:
            print(f"[SMART ENGINE] Standard detection successful ({found_critical}/{len(critical_keys)} critical keys).")
            return standard_map
            
        print(f"[SMART ENGINE] Standard detection low confidence ({found_critical}/4). Attempting LLM mapping...")
        try:
            llm_map = self.detect_columns_llm(df)
            if llm_map:
                # Merge: Use LLM results to override/fill standard map
                for k, v in llm_map.items():
                    if v in df.columns:
                        standard_map[k] = v
                return standard_map
        except Exception as e:
            print(f"[SMART ENGINE] LLM mapping error: {e}")
            
        return standard_map

    def detect_columns_llm(self, df):
        """
        Uses an LLM to map Excel columns to internal keys.
        """
        # Prepare sample data for the LLM
        # We take the header and first 5 rows
        sample_data = df.head(5).to_string()
        columns_list = list(df.columns)
        
        prompt = f"""
        You are an aviation logbook data expert. I have an Excel file with the following columns:
        {columns_list}

        Here is a sample of the data:
        {sample_data}

        Please map these columns to my internal keys:
        - DEP: Flight Date / Month / Day
        - FLT_SN: Flight Serial Number / S/N
        - AC_TYPE: Aircraft Type / Model
        - AC_REG: Aircraft Registration / Reg
        - CAPTAIN: Pilot in Command / Captain name
        - COPILOT: Co-pilot / Student name
        - CAPACITY: Operating Capacity (P1, P2, P/UT, etc.)
        - ROUTE: Route / From-To
        - DAY_P1: Day P1 / PIC hours
        - DAY_P1US: Day P1 (U/S) hours
        - DAY_P2: Day P2 / SIC hours
        - DAY_DUAL: Day Dual / P/UT hours
        - NIGHT_P1: Night P1 / PIC hours
        - NIGHT_P1US: Night P1 (U/S) hours
        - NIGHT_P2: Night P2 / SIC hours
        - NIGHT_DUAL: Night Dual / P/UT hours
        - INSTRUMENT: Instrument Flying (IF) hours
        - SIM_DAY: Simulator hours
        - REMARKS: Remarks / Details
        - ARR: Arrival time / Arrival airport
        - TOTAL: Total flight hours

        Return ONLY a JSON object where keys are my internal keys and values are the EXACT column names from the list above. 
        If you are unsure or a column doesn't exist, omit it.
        """

        # 1. Try Gemini first (Production / Live App)
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key and HAS_GENAI:
            print("[SMART ENGINE] Using Google Gemini API...")
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(prompt)
                # Extract JSON from response (handling potential markdown blocks)
                text = response.text
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0]
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0]
                return json.loads(text.strip())
            except Exception as e:
                print(f"[SMART ENGINE] Gemini error: {e}")

        # 2. Try Local Ollama (Development / Aberdeen)
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "gemma4")
        
        print(f"[SMART ENGINE] Attempting local Ollama ({ollama_model})...")
        try:
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
        """Loads history and profile from JSON."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.pilot_name = data.get('pilot_name', self.pilot_name)
                        self.history = data.get('history', [])
                        self.sync_adjustments = data.get('sync_adjustments', [])
                        # Ensure all entries have an ID and save if we added any
                        ids_added = False
                        for entry in self.history:
                            if 'id' not in entry:
                                entry['id'] = str(uuid.uuid4())
                                ids_added = True
                        
                        if ids_added:
                            self.save_data()
                        self.normalize_history()
                    else:
                        # Handle legacy format where history was the root list
                        self.history = data
                        ids_added = False
                        for entry in self.history:
                            if 'id' not in entry:
                                entry['id'] = str(uuid.uuid4())
                                ids_added = True
                        if ids_added:
                            self.save_data()
                        self.normalize_history()
                        
                    for adj in self.sync_adjustments:
                        if 'date' in adj and isinstance(adj.get('date'), str):
                            try:
                                adj['date_obj'] = datetime.strptime(adj['date'], "%Y-%m-%d")
                            except:
                                adj['date_obj'] = datetime.now()

                    for entry in self.history:
                        if 'date_obj' in entry and isinstance(entry['date_obj'], str):
                            entry['date_obj'] = datetime.fromisoformat(entry['date_obj'].replace('Z', '+00:00'))
                        elif 'date_obj' not in entry:
                            # Default to 1900 if missing
                            entry['date_obj'] = datetime(1900, 1, 1)
            except Exception as e:
                print(f"Error loading logbook data for user {self.user_id}: {e}")
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
            if 'date_str' not in entry and 'date_obj' in entry:
                try:
                    dt_str = entry['date_obj']
                    if isinstance(dt_str, str):
                        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                    else:
                        dt = dt_str
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

    def is_duplicate(self, entry):
        """Checks if a flight serial number already exists in history."""
        if not entry or not entry.get('flt_sn'):
            return False
        return any(h.get('flt_sn') == entry['flt_sn'] for h in self.history)

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

    def detect_columns(self, df_columns):
        """
        Scans dataframe columns and maps them to internal keys based on synonyms.
        Returns a dictionary mapping internal keys to actual column names found in the file.
        """
        detected_map = {}
        # Convert all columns to uppercase and stripped for comparison
        # Store as a list to handle potential duplicates (pandas renames them with .1, .2)
        all_cols = [str(col).strip() for col in df_columns]
        cleaned_cols_map = {col.upper(): col for col in all_cols}
        
        # Track used columns to avoid double mapping
        used_cols = set()

        # Priority 1: Exact or synonym match
        for key, synonyms in self.COLUMN_MAP.items():
            match_found = False
            for syn in synonyms:
                syn_upper = syn.upper()
                # Check if this exact synonym exists in the cleaned columns
                if syn_upper in cleaned_cols_map:
                    col_name = cleaned_cols_map[syn_upper]
                    # Check if this specific column instance is already used
                    # (This helps distinguish between P1 and P1.1 if they are both in synonyms)
                    if col_name not in used_cols:
                        detected_map[key] = col_name
                        used_cols.add(col_name)
                        match_found = True
                        break
            
            if match_found:
                continue

            # Priority 2: Partial matches as a fallback
            for original_col in all_cols:
                if original_col in used_cols:
                    continue
                col_upper = original_col.upper()
                if any(syn.upper() in col_upper or col_upper in syn.upper() for syn in synonyms):
                    detected_map[key] = original_col
                    used_cols.add(original_col)
                    match_found = True
                    break
            
            # Default to None if nothing found (don't guess, let SMART engine handle it)
            if not match_found:
                detected_map[key] = None
                
        return detected_map

    def parse_ias_row(self, row, operator="Default", label="Default", col_map=None):
        if not col_map:
            col_map = {k: v[0] for k, v in self.COLUMN_MAP.items()}

        def get_val(key, default=0.0):
            col_name = col_map.get(key)
            if not col_name:
                return default
            val = row.get(col_name)
            if pd.isna(val):
                if isinstance(col_name, str):
                    for alt in [col_name + " ", col_name.strip()]:
                        if alt in row:
                            val = row.get(alt)
                            if not pd.isna(val):
                                break
            return default if pd.isna(val) else val

        dep_val = row.get(col_map.get('DEP'))
        if pd.isna(dep_val):
            return None

        try:
            if isinstance(dep_val, datetime):
                dep_dt = dep_val
            else:
                try:
                    dep_dt = pd.to_datetime(dep_val).to_pydatetime()
                    if pd.isna(dep_dt):
                        raise ValueError("NaT")
                except:
                    try:
                        current_year = datetime.now().year
                        dep_dt = pd.to_datetime(f"{dep_val}-{current_year}").to_pydatetime()
                    except:
                        return None
        except (ValueError, TypeError):
            return None

        # --- Capture raw metadata (exclude ALL standard-matching columns) ---
        metadata = {}
        # Get all column names that match ANY standard synonym to minimize duplication
        all_standard_synonyms = set()
        for syn_list in self.COLUMN_MAP.values():
            for s in syn_list:
                all_standard_synonyms.add(s.upper())
        
        # Explicit scrub list for common headers that shouldn't be in metadata
        SCRUB_LIST = {
            'ID', 'FLIGHT_ID', 'FLT_SN', 'AIRCRAFT_CATEGORY', 'AC_CATEGORY', 'LABEL', 'OPERATOR',
            'IS_OPENING', 'IS_ADJUSTMENT', 'DATE_OBJ', 'DATE_STR', 'TOTAL', 'TOTAL_TIME', 'TOTAL TIME'
        }
        all_standard_synonyms.update(SCRUB_LIST)
        
        for k, v in row.items():
            k_clean = str(k).strip()
            k_upper = k_clean.upper()
            
            # Skip if this column name (stripped/upper) matches any of our standard synonyms or scrub list
            if k_upper in all_standard_synonyms:
                continue
            
            if not pd.isna(v):
                # Convert timestamps to string for JSON compatibility
                if isinstance(v, (datetime, pd.Timestamp)):
                    metadata[str(k)] = v.isoformat()
                else:
                    metadata[str(k)] = v

        raw_route = str(get_val('ROUTE', '')).strip()
        remarks = str(get_val('REMARKS', "")).strip()
        
        # --- Lesson Extraction Logic (e.g. MCC1, ITR2) ---
        # Patterns to look for in the route column that are actually lessons
        lesson_patterns = ['MCC', 'ITR', 'LVL', 'BASE TRG', 'BASE', 'CHECK', 'TEST', 'RENEWAL']
        extracted_lesson = ""
        clean_route = raw_route
        
        import re
        for pattern in lesson_patterns:
            # Look for the pattern followed by optional space and numbers (e.g. "MCC 1" or "MCC1")
            match = re.search(rf'({pattern}\s?\d*)', raw_route, re.IGNORECASE)
            if match:
                extracted_lesson = match.group(1).upper()
                # Remove the lesson from the route
                clean_route = re.sub(rf'\s?{pattern}\s?\d*', '', raw_route, flags=re.IGNORECASE).strip()
                break
        
        # If we found a lesson, prepend it to remarks
        if extracted_lesson:
            if remarks:
                remarks = f"{extracted_lesson} - {remarks}"
            else:
                remarks = extracted_lesson

        is_sim = str(get_val('AC_REG', '')).strip() == "B-LVZ"
        
        # Extract times for top-level access
        dep_time_raw = get_val('DEP', '')
        arr_time_raw = get_val('ARR', '')
        
        def format_time(val):
            if isinstance(val, (datetime, pd.Timestamp)):
                return val.strftime('%H:%M')
            if isinstance(val, str) and 'T' in val:
                try:
                    return datetime.fromisoformat(val).strftime('%H:%M')
                except:
                    pass
            return str(val)

        entry = {
            'flight_id': get_val('FLT_SN', ''), # Standardized primary ID
            'date_obj': dep_dt,
            'date_str': dep_dt.strftime('%b %d'),
            'ac_type': "SIM" if is_sim else get_val('AC_TYPE', ''),
            'ac_category': 'HELI' if is_sim else self.get_ac_category(get_val('AC_TYPE', '')),
            'reg': f"GFS01 {get_val('AC_REG', '')}" if is_sim else get_val('AC_REG', ''),
            'pic': "SELF" if str(get_val('CAPTAIN', '')).upper() == self.pilot_name.upper() else get_val('CAPTAIN', ''),
            'copilot': "SELF" if str(get_val('COPILOT', '')).upper() == self.pilot_name.upper() else get_val('COPILOT', ''),
            'capacity': get_val('CAPACITY', ''),
            'route': clean_route,
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
            'remarks': remarks,
            'dep_time': format_time(dep_time_raw),
            'arr_time': format_time(arr_time_raw),
            'is_opening': False,
            'is_adjustment': False,
            'operator': operator,
            'label': label,
            'metadata': metadata, # Store everything else here
            'id': str(uuid.uuid4())
        }
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