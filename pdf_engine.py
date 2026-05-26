from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch

class CAD407Renderer:
    def __init__(self, output_filename="CAD407_Export.pdf"):
        self.filename = output_filename
        self.width, self.height = landscape(A4)
        
        # Margins and layout
        self.left_margin = 25
        self.right_margin = 25
        self.top_margin = 530
        self.bottom_margin = 40
        self.available_width = self.width - self.left_margin - self.right_margin
        
        self.row_height = 23
        self.num_rows = 18
        
        # Column widths (scaled from preview.html widths)
        # Total units = 1240
        raw_widths = [70, 55, 80, 100, 100, 65, 220, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45, 75, 75, 120]
        total_units = sum(raw_widths)
        self.col_widths = [(w / total_units) * self.available_width for w in raw_widths]

    def draw_table_structure(self, c, page_num):
        # 1. Background Table Area (White)
        c.setFillColor(colors.white)
        table_height = (self.num_rows * self.row_height) + 50 # +50 for headers
        c.rect(self.left_margin, self.top_margin - (self.num_rows * self.row_height) - 10, self.available_width, table_height, fill=1, stroke=0)

        # 2. Page Title and Number
        c.setFillColorRGB(0.1, 0.1, 0.3)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(self.left_margin, self.height - 35, "CIVIL AVIATION DEPARTMENT - PILOT'S LOG BOOK")
        c.setFont("Helvetica", 10)
        c.drawRightString(self.width - self.right_margin, self.height - 35, f"Page {page_num}")

        # 3. Header Styling (Matching Preview)
        y_h = self.top_margin
        h_height = 40
        
        # Header background (Dark Blue/Grey)
        c.setFillColorRGB(0.12, 0.16, 0.23) # var(--bg-card) approx
        c.rect(self.left_margin, y_h - 10, self.available_width, h_height + 10, fill=1, stroke=0)
        
        # Draw Nested Headers
        c.setStrokeColor(colors.white)
        c.setLineWidth(0.3)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 6.5)
        
        x = self.left_margin
        
        # Column Grouping (Day/Night)
        # Day columns: 9, 10, 11, 12
        # Night columns: 13, 14, 15, 16
        
        # Label common columns
        labels = ["Month / Date", "Type", "Registration", "P.I.C", "Co-Pilot", "Cap", "Journey / Nature", "T/O", "Lnd"]
        for i in range(9):
            w = self.col_widths[i]
            c.drawCentredString(x + w/2, y_h + 5, labels[i])
            c.line(x, y_h + 40, x, y_h - 10 - (self.num_rows * self.row_height))
            x += w
            
        # Day Flying Header
        day_w = sum(self.col_widths[9:13])
        c.drawCentredString(x + day_w/2, y_h + 20, "DAY FLYING")
        c.line(x, y_h + 15, x + day_w, y_h + 15)
        c.drawCentredString(x + self.col_widths[9]/2, y_h + 2, "P1")
        c.drawCentredString(x + self.col_widths[9] + self.col_widths[10]/2, y_h + 2, "P1(U/S)")
        c.drawCentredString(x + sum(self.col_widths[9:11]) + self.col_widths[11]/2, y_h + 2, "P2/P2X")
        c.drawCentredString(x + sum(self.col_widths[9:12]) + self.col_widths[12]/2, y_h + 2, "P/UT")
        for i in range(9, 13):
            c.line(x, y_h + 15, x, y_h - 10 - (self.num_rows * self.row_height))
            x += self.col_widths[i]

        # Night Flying Header
        night_w = sum(self.col_widths[13:17])
        c.drawCentredString(x + night_w/2, y_h + 20, "NIGHT FLYING")
        c.line(x, y_h + 15, x + night_w, y_h + 15)
        c.drawCentredString(x + self.col_widths[13]/2, y_h + 2, "P1")
        c.drawCentredString(x + self.col_widths[13] + self.col_widths[14]/2, y_h + 2, "P1(U/S)")
        c.drawCentredString(x + sum(self.col_widths[13:15]) + self.col_widths[15]/2, y_h + 2, "P2/P2X")
        c.drawCentredString(x + sum(self.col_widths[13:16]) + self.col_widths[16]/2, y_h + 2, "P/UT")
        for i in range(13, 17):
            c.line(x, y_h + 15, x, y_h - 10 - (self.num_rows * self.row_height))
            x += self.col_widths[i]

        # Remaining Columns
        rem_labels = ["Instrument", "Simulator", "Remarks"]
        for i in range(17, 20):
            w = self.col_widths[i]
            c.drawCentredString(x + w/2, y_h + 5, rem_labels[i-17])
            c.line(x, y_h + 40, x, y_h - 10 - (self.num_rows * self.row_height))
            x += w
            
        # Final edge line
        c.line(self.width - self.right_margin, y_h + 40, self.width - self.right_margin, y_h - 10 - (self.num_rows * self.row_height))
        # Top and Bottom header borders
        c.line(self.left_margin, y_h + 40, self.width - self.right_margin, y_h + 40)
        c.line(self.left_margin, y_h - 10, self.width - self.right_margin, y_h - 10)

    def draw_striped_rows(self, c):
        for i in range(self.num_rows):
            if (i + 1) % 2 == 0:
                c.setFillColorRGB(0.97, 0.98, 1.0) # Light subtle blue
                y = self.top_margin - 10 - ((i + 1) * self.row_height)
                c.rect(self.left_margin, y, self.available_width, self.row_height, fill=1, stroke=0)

    def render_pages(self, all_pages_data):
        c = canvas.Canvas(self.filename, pagesize=landscape(A4))
        
        for page_data in all_pages_data:
            # Table container and Stripes
            self.draw_striped_rows(c)
            self.draw_table_structure(c, page_data['page_number'])
            
            # Entries
            c.setFont("Helvetica", 8)
            c.setFillColor(colors.black)
            
            y_base = self.top_margin - 10
            for row_idx, entry in enumerate(page_data['entries']):
                y = y_base - (row_idx * self.row_height) - 16
                x = self.left_margin
                
                fields = [
                    entry.get('date_str', ''), entry.get('ac_type', ''), entry.get('reg', ''),
                    entry.get('pic', ''), entry.get('copilot', ''), entry.get('capacity', ''),
                    entry.get('route', ''), entry.get('takeoff', ''), entry.get('landing', ''),
                    entry.get('day_p1', ''), entry.get('day_p1us', ''), entry.get('day_p2', ''), entry.get('day_dual', ''),
                    entry.get('night_p1', ''), entry.get('night_p1us', ''), entry.get('night_p2', ''), entry.get('night_dual', ''),
                    entry.get('inst_flying', ''), entry.get('sim_time', ''), entry.get('remarks', '')
                ]
                
                for i, val in enumerate(fields):
                    w = self.col_widths[i]
                    text = str(val) if val is not None and val != 0 and val != 0.0 else ""
                    if text:
                        # Truncate if long
                        if i in [3, 4, 6, 19]:
                            max_w = w - 4
                            if c.stringWidth(text, "Helvetica", 8) > max_w:
                                while c.stringWidth(text + "...", "Helvetica", 8) > max_w and len(text) > 0:
                                    text = text[:-1]
                                text += "..."
                        c.drawCentredString(x + w/2, y, text)
                    x += w

            # Footer: Carried Forward and Grand Total
            y_footer = self.bottom_margin + 15
            c.setStrokeColor(colors.black)
            c.setLineWidth(1)
            c.line(self.left_margin, y_footer + 15, self.width - self.right_margin, y_footer + 15)
            
            c.setFont("Helvetica-Bold", 8)
            c.drawString(self.left_margin + 5, y_footer, "CARRIED FORWARD TOTALS:")
            
            # Totals alignment
            cf = page_data.get('carried_forward', {})
            total_keys = [
                None, None, None, None, None, None, None, None, None,
                'day_p1', 'day_p1us', 'day_p2', 'day_dual', 
                'night_p1', 'night_p1us', 'night_p2', 'night_dual', 
                'inst_flying', 'sim_time'
            ]
            
            x = self.left_margin
            for i, key in enumerate(total_keys):
                w = self.col_widths[i]
                if key and key in cf:
                    val = cf[key]
                    if val != 0:
                        c.drawCentredString(x + w/2, y_footer, f"{val:.1f}")
                x += w
                
            # Grand Total Line (1)-(8)
            gt_1_8 = page_data.get('grand_total_1_8', 0)
            c.drawRightString(self.width - self.right_margin - 100, y_footer - 15, f"Grand total column (1) to (8):    {gt_1_8:.1f}")
            
            c.showPage()
            
        c.save()