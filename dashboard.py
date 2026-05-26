import pandas as pd
from datetime import datetime

class LogbookDashboard:
    @staticmethod
    def get_summary(history, start_date=None, category=None, query=None, sync_adjustments=None):
        if not history:
            # Still apply adjustments even if history is empty (for opening balances only cases)
            df = pd.DataFrame(columns=['day_p1', 'day_p1us', 'day_p2', 'day_dual', 'night_p1', 
                                     'night_p1us', 'night_p2', 'night_dual', 'inst_flying', 'sim_time'])
        else:
            df = pd.DataFrame(history)
            df['date_obj'] = pd.to_datetime(df['date_obj'])
            
            if start_date:
                df = df[df['date_obj'] >= start_date]
            
            if category and category != 'ALL':
                df = df[df['ac_category'] == category]

            if query:
                query = str(query).lower()
                df = df[df['label'].str.lower().str.contains(query, na=False)]

        cols = ['day_p1', 'day_p1us', 'day_p2', 'day_dual', 'night_p1', 
                'night_p1us', 'night_p2', 'night_dual', 'inst_flying', 'sim_time']
        
        # Ensure all columns exist to avoid KeyError
        for col in cols:
            if col not in df.columns:
                df[col] = 0.0

        totals = df[cols].sum().to_dict()
        
        # Apply sync adjustments
        if sync_adjustments:
            for adj in sync_adjustments:
                raw_date = adj.get('date_obj') or adj.get('date')
                if not raw_date:
                    continue
                adj_date = pd.to_datetime(raw_date)
                if pd.isna(adj_date):
                    continue
                # Apply if after start_date (or if no start_date)
                if not start_date or adj_date >= pd.to_datetime(start_date):
                    offsets = adj.get('offsets', {})
                    for col, val in offsets.items():
                        if col in totals:
                            totals[col] += float(val)

        # Round final totals
        for col in totals:
            totals[col] = round(totals[col], 1)

        totals['grand_total'] = sum([totals.get(c, 0) for c in cols[:8]])
        return totals

    @staticmethod
    def get_ytd_summary(history, category=None, query=None, sync_adjustments=None):
        current_year = datetime.now().year
        ytd_start = datetime(current_year, 1, 1)
        return LogbookDashboard.get_summary(history, start_date=ytd_start, category=category, query=query, sync_adjustments=sync_adjustments)

    @staticmethod
    def get_summary_by_type(history, category=None, query=None):
        if not history:
            return []
        df = pd.DataFrame(history)
        
        # Merge simulator types into their real aircraft equivalents
        if 'ac_type' in df.columns:
            df['ac_type'] = df['ac_type'].replace({'SIM': 'EC175'})
        
        if category and category != 'ALL':
            df = df[df['ac_category'] == category]
            
        if query:
            query = str(query).lower()
            df = df[df['label'].str.lower().str.contains(query, na=False)]
        cols = ['day_p1', 'day_p1us', 'day_p2', 'day_dual', 'night_p1', 
                'night_p1us', 'night_p2', 'night_dual', 'inst_flying', 'sim_time']
        
        type_group = df.groupby('ac_type')[cols].sum().reset_index()
        return type_group.to_dict('records')