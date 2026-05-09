# 🚁 HKCAD 407 Digital Logbook Engine

## 1. Project Goal
To provide a specialized tool for GFS/NHV pilots to manage flight records. The system automates the transition from GFS IAS Excel exports and manual entries into a perfectly formatted HKCAD CAD 407 PDF.

## 2. Structure & Language
- **Language:** Python 3.x (Optimized for Antigravity/Browser environments).
- **Frontend:** Antigravity UI (Responsive Web/Mobile).
- **Backend Modules:**
    - `Profile Manager`: Handles opening balances and user identity.
    - `Data Parser`: Standardizes disparate data sources (IAS vs. Manual).
    - `Logic Engine`: Applies rounding, "SELF" naming, and "SIM" aircraft rules.
    - `Pagination Manager`: Manages 18-line pages and 78-page books.
    - `PDF Renderer`: Generates an identical copy of the physical CAD 407 logbook.

## 3. Core Logic Rules
- **Rounding:** All decimal hours are forced to the next 0.1 increment (e.g., 0.21 -> 0.3).
- **B-LVZ Rule:** Registration B-LVZ is automatically treated as a Simulator (Type: SIM, Reg: GFS01 B-LVZ).
- **Identity Rule:** Matches user name to "SELF" in PIC/Copilot columns.
- **Chronology:** Sorts all entries by `DEP` timestamp (DD/MM/YYYY HH:MM).
- **PDF Layout:** 18 lines per page, alternating grey/white stripes, includes "Totals Brought Forward" and "Grand Totals".

## 4. Usage Instructions
1. Input Opening Balances via the Profile interface.
2. Upload IAS Excel files or enter NHV data manually.
3. Select the starting page number for the physical logbook.
4. Preview the Dashboard for total hour breakdowns.
5. Export the PDF for manual transcription.