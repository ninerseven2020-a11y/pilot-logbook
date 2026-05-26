import os
from datetime import datetime
from engine import CAD407Logbook

def render_logbook_html(user, start_page=1, end_page=None):
    """
    Generates a static, data-injected HTML string of the CAD 407 logbook.
    This HTML is ready to be sent to Browserless.io for PDF generation.
    """
    logbook = CAD407Logbook(user_id=user.id, pilot_name=user.pilot_name)
    
    # Use the existing engine logic to get fully calculated and paginated data
    all_pages = logbook.get_paginated_data(start_page=1)
    
    if not all_pages:
        # Create at least one empty page if no data
        all_pages = [{
            'page_number': 1,
            'year': datetime.now().year,
            'entries': [],
            'brought_forward': {col: 0.0 for col in ['day_p1', 'day_p1us', 'day_p2', 'day_dual', 'night_p1', 'night_p1us', 'night_p2', 'night_dual', 'inst_flying', 'sim_time']},
            'carried_forward': {col: 0.0 for col in ['day_p1', 'day_p1us', 'day_p2', 'day_dual', 'night_p1', 'night_p1us', 'night_p2', 'night_dual', 'inst_flying', 'sim_time']},
            'grand_total_1_8': 0.0
        }]

    if end_page is None:
        end_page = len(all_pages)
    
    # Slice requested pages (start_page is 1-indexed)
    requested_pages = all_pages[start_page-1 : end_page]
    
    # Build HTML string
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
        <style>
            :root {{
                --primary-bg: #0f172a;
                --secondary-bg: #1e293b;
                --accent-color: #f59e0b;
                --text-main: #f8fafc;
                --text-muted: #94a3b8;
                --bg-white: #ffffff;
                --bg-grey: #f3f4f6;
            }}
            body {{
                font-family: 'Inter', sans-serif;
                background: white;
                color: #1e293b;
                margin: 0;
                padding: 0;
            }}
            .print-page {{
                width: 1650px;
                padding: 40px;
                page-break-after: always;
                box-sizing: border-box;
                background: white;
            }}
            .cad407-table {{
                width: 100%;
                border-collapse: collapse;
                border: 2px solid #1e293b;
                font-size: 11.5px;
                table-layout: fixed;
            }}
            .cad407-table th, .cad407-table td {{
                border: 1px solid #94a3b8;
                padding: 6px 4px;
                text-align: center;
                height: 23px;
                overflow: hidden;
                white-space: nowrap;
                text-overflow: ellipsis;
            }}
            .cad407-table thead th {{
                background: #1e293b;
                color: white;
                font-weight: 700;
                font-size: 10px;
                padding: 4px 2px;
            }}
            .row-striped {{ background-color: #f8fafc; }}
            .grand-total-row {{
                background-color: #f1f5f9 !important;
                font-weight: 800;
            }}
            h2 {{ font-size: 1.25rem; margin: 0; font-weight: 800; }}
            .header-row {{ display: flex; justify-content: space-between; margin-bottom: 20px; align-items: center; }}
        </style>
    </head>
    <body>
    """

    for page_data in requested_pages:
        page_num = page_data['page_number']
        page_entries = page_data['entries']
        cf = page_data['carried_forward']
        
        # Build Table rows
        rows_html = ""
        entries_per_page = 18
        for i in range(entries_per_page):
            if i < len(page_entries):
                e = page_entries[i]
                striped = "row-striped" if i % 2 != 0 else ""
                
                # Format values
                def fmt(val):
                    if val is None or val == 0: return ""
                    return f"{val:.1f}" if isinstance(val, (int, float)) else str(val)

                if e.get('is_monthly_total'):
                    rows_html += f"""
                    <tr class="grand-total-row">
                        <td colspan="9" style="text-align: left; padding-left: 10px;">{e.get('date_str', '')}</td>
                        <td>{fmt(e.get('day_p1'))}</td>
                        <td>{fmt(e.get('day_p1us'))}</td>
                        <td>{fmt(e.get('day_p2'))}</td>
                        <td>{fmt(e.get('day_dual'))}</td>
                        <td>{fmt(e.get('night_p1'))}</td>
                        <td>{fmt(e.get('night_p1us'))}</td>
                        <td>{fmt(e.get('night_p2'))}</td>
                        <td>{fmt(e.get('night_dual'))}</td>
                        <td>{fmt(e.get('inst_flying'))}</td>
                        <td>{fmt(e.get('sim_time'))}</td>
                        <td></td>
                    </tr>
                    """
                else:
                    rows_html += f"""
                    <tr class="{striped}">
                        <td>{e.get('date_str', '')}</td>
                        <td>{e.get('ac_type', '')}</td>
                        <td>{e.get('reg', '')}</td>
                        <td>{e.get('pic', '')}</td>
                        <td>{e.get('copilot', '')}</td>
                        <td>{e.get('capacity', '')}</td>
                        <td style="text-align: left;">{e.get('route', '')}</td>
                        <td>{e.get('takeoff', '') or ''}</td>
                        <td>{e.get('landing', '') or ''}</td>
                        <td>{fmt(e.get('day_p1'))}</td>
                        <td>{fmt(e.get('day_p1us'))}</td>
                        <td>{fmt(e.get('day_p2'))}</td>
                        <td>{fmt(e.get('day_dual'))}</td>
                        <td>{fmt(e.get('night_p1'))}</td>
                        <td>{fmt(e.get('night_p1us'))}</td>
                        <td>{fmt(e.get('night_p2'))}</td>
                        <td>{fmt(e.get('night_dual'))}</td>
                        <td>{fmt(e.get('inst_flying'))}</td>
                        <td>{fmt(e.get('sim_time'))}</td>
                        <td style="text-align: left;">{e.get('remarks', '')}</td>
                    </tr>
                    """
            else:
                # Empty rows
                rows_html += "<tr>" + "<td></td>"*20 + "</tr>"

        html += f"""
        <div class="print-page">
            <div class="header-row">
                <h2>CIVIL AVIATION DEPARTMENT - PILOT'S LOG BOOK</h2>
                <div style="font-weight: 800; font-size: 1.2rem;">Page {page_num}</div>
            </div>
            <table class="cad407-table">
                <colgroup>
                    <col style="width: 70px;"> <col style="width: 55px;"> <col style="width: 80px;"> <col style="width: 100px;">
                    <col style="width: 100px;"> <col style="width: 65px;"> <col style="width: 220px;"> <col style="width: 45px;">
                    <col style="width: 45px;"> <col style="width: 45px;"> <col style="width: 45px;"> <col style="width: 45px;">
                    <col style="width: 45px;"> <col style="width: 45px;"> <col style="width: 45px;"> <col style="width: 45px;">
                    <col style="width: 45px;"> <col style="width: 75px;"> <col style="width: 75px;"> <col style="width: 140px;">
                </colgroup>
                <thead>
                    <tr>
                        <th style="border-bottom: 1px solid #94a3b8;">Year / ---</th>
                        <th colspan="2">Aircraft / Simulator</th>
                        <th rowspan="2">Pilot-in-command</th>
                        <th rowspan="2">Co-pilot or student</th>
                        <th rowspan="2">Holder's operating capacity</th>
                        <th rowspan="2">Journey or nature of flight</th>
                        <th colspan="2">No. of</th>
                        <th colspan="4">Day flying</th>
                        <th colspan="4">Night flying</th>
                        <th rowspan="2">Instrument Flying</th>
                        <th rowspan="2">Simulator Time</th>
                        <th rowspan="2">Remarks</th>
                    </tr>
                    <tr>
                        <th style="border-top: none;">Month / Date</th>
                        <th>Type</th>
                        <th>Registration</th>
                        <th>Take-offs</th>
                        <th>Landings</th>
                        <th>P1</th><th>P1(U/S)</th><th>P2/P2X</th><th>P/UT</th>
                        <th>P1</th><th>P1(U/S)</th><th>P2/P2X</th><th>P/UT</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
                <tfoot>
                    <tr class="grand-total-row">
                        <td colspan="7" style="text-align: left;">CARRIED FORWARD TOTALS:</td>
                        <td>{int(cf.get('takeoff', 0)) if cf.get('takeoff', 0) > 0 else ''}</td>
                        <td>{int(cf.get('landing', 0)) if cf.get('landing', 0) > 0 else ''}</td>
                        <td>{cf.get('day_p1', 0):.1f}</td>
                        <td>{cf.get('day_p1us', 0):.1f}</td>
                        <td>{cf.get('day_p2', 0):.1f}</td>
                        <td>{cf.get('day_dual', 0):.1f}</td>
                        <td>{cf.get('night_p1', 0):.1f}</td>
                        <td>{cf.get('night_p1us', 0):.1f}</td>
                        <td>{cf.get('night_p2', 0):.1f}</td>
                        <td>{cf.get('night_dual', 0):.1f}</td>
                        <td>{cf.get('inst_flying', 0):.1f}</td>
                        <td>{cf.get('sim_time', 0):.1f}</td>
                        <td></td>
                    </tr>
                </tfoot>
            </table>
        </div>
        """

    html += "</body></html>"
    return html

async def render_pdf_local(html_content, output_path, token, port=8000):
    """
    Renders the logbook using the V10 screenshot-to-image-PDF method.
    This ensures pixel-perfect "screenshot" style by capturing the live UI.
    """
    from playwright.async_api import async_playwright
    from PIL import Image
    import io
    import os

    base_url = f"http://127.0.0.1:{port}"
    images = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Device scale factor 2 for high-resolution "Retina" style screenshots
        context = await browser.new_context(
            viewport={'width': 1800, 'height': 1200},
            device_scale_factor=2
        )
        page = await context.new_page()

        try:
            # 1. Login/Auth by injecting token into localStorage
            await page.goto(f"{base_url}/login")
            await page.evaluate(f"localStorage.setItem('logbook_auth_token', '{token}')")

            # 2. Go to Preview and wait for data to load
            await page.goto(f"{base_url}/preview", wait_until="networkidle")
            # Wait for the page selector to be populated (indicates data is ready)
            await page.wait_for_function("document.querySelectorAll('#page-select option').length > 0", timeout=20000)

            # 3. Hide ALL page chrome so only the logbook table is captured
            await page.add_style_tag(content="""
                header,
                .preview-header,
                #sync-status-panel,
                #no-sync-panel,
                .version-label,
                .sync-indicator,
                #pdf-modal,
                #sync-modal {
                    display: none !important;
                }
                /* Remove container padding so the printable area is flush */
                .container {
                    padding-top: 0 !important;
                    padding-bottom: 0 !important;
                }
                #preview.card-section {
                    margin: 0 !important;
                    padding: 0 !important;
                }
                /* Ensure the printable area has a clean white background */
                #logbook-printable-area {
                    border-radius: 0 !important;
                    box-shadow: none !important;
                }
            """)

            # 4. Scroll to very top so the element is fully in view without header overlap
            await page.evaluate("window.scrollTo(0, 0)")

            # 5. Capture the logbook printable area only
            element = await page.query_selector("#logbook-printable-area")
            if element:
                img_data = await element.screenshot(type="png")
                img = Image.open(io.BytesIO(img_data))
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                images.append(img)
            
            if not images:
                raise Exception("Failed to capture logbook area")


            # 5. Save as Image-based PDF
            images[0].save(
                output_path,
                "PDF",
                save_all=True,
                append_images=images[1:] if len(images) > 1 else []
            )
            
        finally:
            await browser.close()
            
    return output_path
