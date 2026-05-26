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
        def encoder(obj):
            try:
                import pandas as pd
                if pd.isna(obj):
                    return None
                if hasattr(obj, 'isoformat'):
                    return obj.isoformat()
            except:
                pass
            # Fallback for anything else
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            return str(obj)
        
        payload = {
            'pilot_name': self.pilot_name,
            'history': self.history,
            'sync_adjustments': self.sync_adjustments
        }
        print(f"[DEBUG] Saving {len(self.history)} entries to {self.storage_file}")
        with open(self.storage_file, "w") as f:
            json.dump(payload, f, default=encoder)

    def get_dashboard_data(self, category=None, query=None):
        """
        Unified method to fetch all logbook data for the UI.
        Ensures dates are serialized and SELF logic is applied.
        """
        from main import get_mvp_data
        # Use the existing MVP data structure
        raw_data = get_mvp_data(self, category=category, query=query)
        
        # Ensure the entire payload is JSON-safe (datetimes -> strings)
        import json
        return json.loads(json.dumps(raw_data, default=str))

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

            # Key Mapping (Manual/Legacy/IAS Entry keys -> Engine/Rendering keys)
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

            # Handle Simulator Time Merging (sim_day + sim_night -> sim_time)
            # This is kept as a fallback for old IAS data
            if 'sim_time' not in entry or entry['sim_time'] == 0:
                s_day = float(entry.get('sim_day', 0))
                s_night = float(entry.get('sim_night', 0))
                if s_day > 0 or s_night > 0:
                    entry['sim_time'] = s_day + s_night

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

    def add_or_update_flight(self, entry):
        """
        Smart Deduplication/Update based on FLT S/N.
        Returns (status, message).
        """
        sn = str(entry.get('flight_id', '')).strip()
        if not sn or sn in ['', 'None', 'nan', 'Unknown']:
            return self.add_entry(entry)
            
        for h in self.history:
            if str(h.get('flight_id', '')).strip() == sn:
                # Compare critical data to see if update is needed
                has_changes = False
                # Fields to potentially update from new Excel data
                update_fields = [
                    'takeoff', 'landing', 'remarks', 'operator', 'label', 'capacity', 
                    'captain', 'copilot', 'crewman_1', 'crewman_2', 'crewman_3', 'crewman_4'
                ]
                for field in update_fields:
                    new_val = entry.get(field)
                    old_val = h.get(field)
                    
                    # Special case for TO/LDG: only update if new data is present
                    if field in ['takeoff', 'landing']:
                        if new_val != '' and new_val != old_val:
                            h[field] = new_val
                            has_changes = True
                    else:
                        if new_val and new_val != old_val:
                            h[field] = new_val
                            has_changes = True
                
                if has_changes:
                    return "UPDATED", f"Flight {sn} updated."
                return "SKIPPED", f"Flight {sn} is identical."
        
        # If not found, add as new
        self.history.append(entry)
        return "ADDED", f"Flight {sn} added."

    def process_ias_files(self, file_005_path=None, file_001_path=None, operator="Default", label="Default", column_map=None):
        """
        IAS standard ingestion engine with Safety Net validation.
        """
        results = {'added': 0, 'updated': 0, 'skipped': 0, 'cautions': []}
        df_005 = None
        df_001 = None

        try:
            if file_005_path:
                df_005 = pd.read_excel(file_005_path)
                
                # --- SMART SAFETY NET (Simplified v1.4.9) ---
                # Only these will STOP the import if missing
                critical_keys = ['DATE', 'FLT S/N', 'AC TYPE', 'AC REG']
                
                # These will be searched for SILENTLY (handling typos like extra spaces)
                breakdown_keys = [
                    'CAPTAIN', 'COPILOT', 'OPERATING CAPACITY', 'ROUTE', 'TOTAL', 
                    'DAY P1', 'DAY P1 (U/S)', 'DAY P2', 'DAY DUAL', 
                    'NIGHT P1', 'NIGHT P1 (U/S)', 'NIGHT P2', 'NIGHT DUAL',
                    'INSTRUMENT', 'REMARKS', 'SIM DAY', 'SIM NIGHT'
                ]
                
                final_map = column_map or {}
                missing_critical = []
                
                # 1. Map everything we can find silently
                for key in (critical_keys + breakdown_keys):
                    if key not in final_map:
                        # Exact match or common typos (like trailing space)
                        synonyms = [key, key + " ", " " + key]
                        found = False
                        for syn in synonyms:
                            if syn in df_005.columns:
                                final_map[key] = syn
                                found = True
                                break
                        if not found and key in critical_keys:
                            missing_critical.append(key)
                
                # 2. Only trigger modal if CRITICAL info is missing
                if missing_critical and not column_map:
                    print(f"[SAFETY NET] Critical columns missing: {missing_critical}. Engaging AI...")
                    suggested_map, _ = self.detect_columns_smart(df_005)
                    return {
                        "status": "CONFIRMATION_REQUIRED",
                        "missing_keys": missing_critical,
                        "suggested_map": suggested_map,
                        "excel_columns": list(df_005.columns)
                    }
                # --------------------------------------------

            if file_001_path:
                df_001 = pd.read_excel(file_001_path)
        except Exception as e:
            raise Exception(f"File format error: {str(e)}")

        # Path 1: AUTH-005 is provided
        if df_005 is not None:
            landing_map = {}
            if df_001 is not None:
                sn_col = 'S/N ' if 'S/N ' in df_001.columns else 'S/N'
                if sn_col in df_001.columns:
                    for _, row in df_001.iterrows():
                        sn = str(row[sn_col]).strip()
                        landing_map[sn] = row.get('No. of Landing')

            for _, row in df_005.iterrows():
                sn_col_005 = final_map.get('FLT S/N', 'FLT S/N')
                sn = str(row.get(sn_col_005, '')).strip()
                if not sn or pd.isna(sn): continue
                
                entry = self.map_005_row_to_metadata(row, operator, label, final_map)
                
                if df_001 is not None and sn in landing_map:
                    ldg = landing_map[sn]
                    if not pd.isna(ldg):
                        entry['takeoff'] = int(ldg)
                        entry['landing'] = int(ldg)

                status, msg = self.add_or_update_flight(entry)
                if status == "ADDED": results['added'] += 1
                elif status == "UPDATED": results['updated'] += 1
                elif status == "SKIPPED": results['skipped'] += 1

        # Path 2: ONLY AUTH-001 is provided (Enrichment Mode)
        elif df_001 is not None:
            sn_col = 'S/N ' if 'S/N ' in df_001.columns else 'S/N'
            for _, row in df_001.iterrows():
                sn = str(row.get(sn_col, '')).strip()
                if not sn or pd.isna(sn): continue
                
                ldg = row.get('No. of Landing')
                if pd.isna(ldg): continue
                
                found = False
                for h in self.history:
                    # Match by native flight_id key
                    if str(h.get('flight_id', '')).strip() == sn:
                        if h.get('landing') != ldg or h.get('takeoff') != ldg:
                            h['takeoff'] = int(ldg)
                            h['landing'] = int(ldg)
                            results['updated'] += 1
                        else:
                            results['skipped'] += 1
                        found = True
                        break
                
                if not found:
                    results['cautions'].append(f"Flight {sn}: Landings found in AUTH-001 but flight not found in Logbook. Please upload AUTH-005 first.")

        self.save_data()
        return results

    def map_005_row_to_metadata(self, row, operator, label, col_map=None):
        """Maps an AUTH-005 row to the standardized CAD 407 JSON structure."""
        if not col_map:
            # Default fallback for IAS standard headers
            col_map = {
                'DATE': 'DATE', 'FLT S/N': 'FLT S/N', 'AC TYPE': 'AC TYPE', 'AC REG': 'AC REG',
                'CAPTAIN': 'CAPTAIN', 'COPILOT': 'COPILOT', 'OPERATING CAPACITY': 'OPERATING CAPACITY',
                'ROUTE': 'ROUTE', 'TOTAL': 'TOTAL', 'DAY P1': 'DAY P1', 'DAY P2': 'DAY P2',
                'DAY DUAL': 'DAY DUAL', 'NIGHT P1': 'NIGHT P1', 'NIGHT P2': 'NIGHT P2', 'NIGHT DUAL': 'NIGHT DUAL',
                'INSTRUMENT': 'INSTRUMENT', 'REMARKS': 'REMARKS'
            }

        # Helper to safely format timestamps for JSON serialization
        def fmt_dt_json(val):
            if pd.isna(val): return None
            if isinstance(val, (datetime, pd.Timestamp)):
                return val.isoformat()
            return str(val)

        # Map according to user's finalized CAD 407 order
        raw_date = row.get(col_map.get('DATE', 'DATE'))
        if hasattr(raw_date, 'to_pydatetime'):
            raw_date = raw_date.to_pydatetime()
        elif pd.isna(raw_date):
            raw_date = datetime.now()
            
        # Helper to safely format strings and handle NaN
        def fmt_str(val):
            if pd.isna(val): return ""
            return str(val).strip()

        metadata = {
            'id': str(uuid.uuid4()),
            'date_obj': raw_date.isoformat(), # Store as ISO String for JSON safety
            'date_str': raw_date.strftime('%b %d'),
            'flight_id': fmt_str(row.get(col_map.get('FLT S/N', 'FLT S/N'))),
            'ac_type': fmt_str(row.get(col_map.get('AC TYPE', 'AC TYPE'))),
            'reg': fmt_str(row.get(col_map.get('AC REG', 'AC REG'))),
            'pic': fmt_str(row.get(col_map.get('CAPTAIN', 'CAPTAIN'))),
            'copilot': fmt_str(row.get(col_map.get('COPILOT', 'COPILOT'))),
            'crewman_1': fmt_str(row.get(col_map.get('CREWMAN 1', 'CREWMAN 1'))),
            'crewman_2': fmt_str(row.get(col_map.get('CREWMAN 2', 'CREWMAN 2'))),
            'crewman_3': fmt_str(row.get(col_map.get('CREWMAN 3', 'CREWMAN 3'))),
            'crewman_4': fmt_str(row.get(col_map.get('CREWMAN 4', 'CREWMAN 4'))),
            'capacity': fmt_str(row.get(col_map.get('OPERATING CAPACITY', 'OPERATING CAPACITY'))),
            'route': fmt_str(row.get(col_map.get('ROUTE', 'ROUTE'))),
            'takeoff': 0, 
            'landing': 0, 
            'dep_time': fmt_dt_json(row.get('DEP')),
            'arr_time': fmt_dt_json(row.get('ARR')),
            'total': self.cad_round_up(row.get(col_map.get('TOTAL', 'TOTAL'))),
            'day_p1': self.cad_round_up(row.get(col_map.get('DAY P1', 'DAY P1'))),
            'day_p1us': self.cad_round_up(row.get(col_map.get('DAY P1 (U/S)', 'DAY P1 (U/S)'))),
            'day_p2': self.cad_round_up(row.get(col_map.get('DAY P2', 'DAY P2'))),
            'day_dual': self.cad_round_up(row.get(col_map.get('DAY DUAL', 'DAY DUAL'))),
            'night_p1': self.cad_round_up(row.get(col_map.get('NIGHT P1', 'NIGHT P1'))),
            'night_p1us': self.cad_round_up(row.get(col_map.get('NIGHT P1 (U/S)', 'NIGHT P1 (U/S)'))),
            'night_p2': self.cad_round_up(row.get(col_map.get('NIGHT P2', 'NIGHT P2'))),
            'night_dual': self.cad_round_up(row.get(col_map.get('NIGHT DUAL', 'NIGHT DUAL'))),
            'inst_flying': self.cad_round_up(row.get(col_map.get('INSTRUMENT', 'INSTRUMENT'))),
            'sim_time': self.cad_round_up(row.get(col_map.get('SIM DAY', 'SIM DAY'), 0)) + self.cad_round_up(row.get(col_map.get('SIM NIGHT', 'SIM NIGHT'), 0)),
            'remarks': fmt_str(row.get(col_map.get('REMARKS', 'REMARKS'))),
            'operator': operator,
            'label': label,
            'ac_category': self.get_ac_category(fmt_str(row.get(col_map.get('AC TYPE', 'AC TYPE'))))
        }
        return metadata

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

    def add_sync_adjustment(self, page_number, offsets, remarks="Sync with Paper", page_index=None):
        """
        Adds a carried-forward adjustment point keyed to a logbook page number.
        The adjustment is applied to the brought_forward totals of that page and all subsequent pages.
        offsets: dict like {'day_p1': 0.5, 'night_p1': -0.2}
        """
        # Round offsets to 1 decimal place
        rounded_offsets = {k: round(float(v), 1) for k, v in offsets.items() if abs(float(v)) > 0.001}

        adjustment = {
            'id': str(uuid.uuid4()),
            'page_number': int(page_number),
            'page_index': int(page_index) if page_index is not None else None,
            'offsets': rounded_offsets,
            'remarks': remarks
        }
        self.sync_adjustments.append(adjustment)
        # Sort by page index if present, otherwise page number
        self.sync_adjustments.sort(key=lambda x: x.get('page_index') if x.get('page_index') is not None else x.get('page_number', 0))
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
        # Store real names — SELF substitution happens at render time in get_paginated_data()
        pic_final = pic_raw
        copilot_final = copilot_raw

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

        # Render-time SELF substitution: replace the user's own pilot name with "SELF"
        # in the PIC and Copilot columns. Real names are stored in the database;
        # this substitution only affects data returned for display/preview/PDF.
        def resolve_self(name):
            """Returns 'SELF' if name matches the logbook owner's pilot_name (case-insensitive)."""
            if not name or not self.pilot_name:
                return name
            if str(name).strip().upper() == self.pilot_name.strip().upper():
                return "SELF"
            return name

        sorted_data = sorted(self.history, key=lambda x: x['date_obj'])
        
        # Columns to track for totals
        total_cols = ['day_p1', 'day_p1us', 'day_p2', 'day_dual', 
                      'night_p1', 'night_p1us', 'night_p2', 'night_dual', 
                      'inst_flying', 'sim_time', 'takeoff', 'landing']
        
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
            
        # Prepare adjustments sorted by page number (support legacy date-based entries as page 1)
        sorted_adjustments = sorted(
            self.sync_adjustments,
            key=lambda x: x.get('page_number', 0)
        )

        pages = []
        
        # Group by Year-Month
        from itertools import groupby
        grouped = groupby(filtered_data, key=lambda x: (x['date_obj'].year, x['date_obj'].month))
        
        current_page_entries = []
        
        def apply_adjustments_for_page(page_idx, page_num):
            """Apply any sync adjustments whose page_index matches page_idx (or page_number matches page_num for legacy)."""
            for adj in sorted_adjustments:
                if 'page_index' in adj and adj.get('page_index') is not None:
                    if adj.get('page_index') == page_idx:
                        for col, offset in adj.get('offsets', {}).items():
                            if col in running_totals:
                                running_totals[col] = round(running_totals[col] + float(offset), 1)
                else:
                    if adj.get('page_number') == page_num:
                        for col, offset in adj.get('offsets', {}).items():
                            if col in running_totals:
                                running_totals[col] = round(running_totals[col] + float(offset), 1)
        
        # Apply adjustments for the first page upfront (index 0)
        apply_adjustments_for_page(0, start_page)
        page_brought_forward = running_totals.copy()
        
        def start_new_page():
            nonlocal current_page_entries, page_brought_forward
            if not current_page_entries:
                return
                
            page_num = ((start_page + len(pages) - 1) % self.pages_per_book) + 1
            
            # Apply any adjustments that target the NEXT page's brought_forward
            # (i.e., they are applied before we snapshot page_brought_forward for the next page)
            next_page_num = ((start_page + len(pages)) % self.pages_per_book) + 1
            
            # Calculate carried forward for this page
            page_carried_forward = running_totals.copy()
            
            # Determine Year for the page header
            year = ""
            for entry in current_page_entries:
                if 'date_obj' in entry:
                    year = entry['date_obj'].year
                    break
            
            pages.append({
                'page_number': page_num,
                'year': year,
                'entries': current_page_entries,
                'brought_forward': page_brought_forward.copy(),
                'carried_forward': page_carried_forward,
                'grand_total_1_8': sum(page_carried_forward[col] for col in total_cols[:8]),
                'has_adjustments': any(
                    (adj.get('page_index') is not None and adj.get('page_index') <= len(pages)) or
                    (adj.get('page_index') is None and adj.get('page_number', 0) <= page_num)
                    for adj in sorted_adjustments
                )
            })
            current_page_entries = []
            # Apply adjustments targeting the next page before snapshotting brought_forward
            next_page_idx = len(pages)
            apply_adjustments_for_page(next_page_idx, next_page_num)
            page_brought_forward = running_totals.copy()


        for (year, month), month_entries in grouped:
            month_entries = list(month_entries)
            month_totals = {col: 0.0 for col in total_cols}
            
            for entry in month_entries:
                if len(current_page_entries) >= self.lines_per_page:
                    start_new_page()
                
                # Apply SELF substitution at render time (non-destructive copy)
                display_entry = dict(entry)
                display_entry['pic'] = resolve_self(display_entry.get('pic', ''))
                display_entry['copilot'] = resolve_self(display_entry.get('copilot', ''))
                current_page_entries.append(display_entry)
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

        # Apply any remaining adjustments (targeting pages beyond the last generated page)
        # These are no-ops for display but kept for consistency

        if current_page_entries:
            start_new_page()

        # Apply page-1 adjustments upfront if no pages have been generated yet
        # (edge case: adjustments exist but no data)

        return pages