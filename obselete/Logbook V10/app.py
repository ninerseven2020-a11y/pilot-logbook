from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, status, Response, Request, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
import pandas as pd
import os
import io
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session

from main import get_mvp_data, add_adjustment, get_logbook_preview
from engine import CAD407Logbook
from pdf_engine import CAD407Renderer
from models import User, get_password_hash, verify_password, SessionLocal, init_db, Organization, FlightNature

# Security Configuration
SECRET_KEY = "3bf3dcec3423b9b40d911ca20f5f63b66efe78bc201ed5880b5755b4f162d6ed"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 24 hours

app = FastAPI()
templates = Jinja2Templates(directory="static") # We'll use static as templates dir for simplicity

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=False)

async def get_current_user(request: Request, token: str = Depends(oauth2_scheme), db = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Check query params if header is missing
    if not token:
        token = request.query_params.get("token")
        
    if not token:
        raise credentials_exception
        
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_root():
    return FileResponse('static/dashboard.html')

@app.get("/login")
async def login_page():
    return FileResponse('static/login.html')

@app.get("/register")
async def register_page():
    return FileResponse('static/register.html')

@app.get("/dashboard")
async def read_dashboard():
    return FileResponse('static/dashboard.html')

@app.get("/preview")
async def read_preview():
    return FileResponse('static/preview.html')

@app.get("/print_view")
async def print_view(
    request: Request,
    start_page: int = Query(1),
    end_page: int = Query(None),
    current_user: User = Depends(get_current_user)
):
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    all_pages = logbook.get_paginated_data(start_page=1)
    
    if end_page is None:
        end_page = len(all_pages)
        
    selected_pages = all_pages[start_page-1 : end_page]
    
    return templates.TemplateResponse("print_logbook.html", {
        "request": request,
        "pages": selected_pages,
        "pilot_name": current_user.pilot_name
    })

# --- Auth APIs ---

@app.post("/api/register")
async def register(
    username: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    pilot_name: str = Form(...),
    age: int = Form(...),
    email: str = Form(...),
    license_type: str = Form(...),
    aircraft_type: str = Form(...),
    db = Depends(get_db)
):
    db_user = db.query(User).filter(User.username == username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = get_password_hash(password)
    new_user = User(
        username=username,
        password_hash=hashed_password,
        full_name=full_name,
        pilot_name=pilot_name,
        age=age,
        email=email,
        license_type=license_type,
        aircraft_type=aircraft_type
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User registered successfully"}

@app.post("/api/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "username": current_user.username,
        "full_name": current_user.full_name,
        "pilot_name": current_user.pilot_name,
        "age": current_user.age,
        "email": current_user.email,
        "license_type": current_user.license_type,
        "aircraft_type": current_user.aircraft_type
    }

# --- Logbook APIs ---

@app.get("/api/dashboard")
async def dashboard(category: Optional[str] = Query(None), q: Optional[str] = Query(None), current_user: User = Depends(get_current_user)):
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    return get_mvp_data(logbook, category=category, query=q)

@app.post("/api/adjustment")
async def adjustment(
    column: str = Form(...), 
    value: float = Form(...), 
    reason: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    try:
        logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
        msg = add_adjustment(logbook, column, value, reason)
        return {"message": msg, "data": get_mvp_data(logbook)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/sync_adjustments")
async def get_sync_adjustments(current_user: User = Depends(get_current_user)):
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    return {"adjustments": logbook.sync_adjustments}

@app.post("/api/sync_adjustments")
async def add_sync_adjustment(request: Request, current_user: User = Depends(get_current_user)):
    data = await request.json()
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    adj = logbook.add_sync_adjustment(
        date_str=data.get('date'),
        offsets=data.get('offsets', {}),
        remarks=data.get('remarks', "Sync with Paper")
    )
    # Strip date_obj for JSON serialization
    adj_out = {k: v for k, v in adj.items() if k != 'date_obj'}
    return {"message": "Sync adjustment added", "adjustment": adj_out}

@app.delete("/api/sync_adjustments/{adj_id}")
async def delete_sync_adjustment(adj_id: str, current_user: User = Depends(get_current_user)):
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    logbook.delete_sync_adjustment(adj_id)
    return {"message": "Sync adjustment deleted"}

@app.get("/api/preview")
async def preview(
    page: int = 1, 
    date_from: Optional[str] = Query(None), 
    date_to: Optional[str] = Query(None), 
    current_user: User = Depends(get_current_user)
):
    try:
        logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
        
        # Parse dates
        dt_from = datetime.strptime(date_from, "%Y-%m-%d") if date_from else None
        
        # Parse end date and set to end of day
        if date_to:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d")
            dt_to = dt_to.replace(hour=23, minute=59, second=59)
        else:
            dt_to = None
            
        return get_logbook_preview(logbook, page, date_from=dt_from, date_to=dt_to)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/upload_metadata")
async def get_upload_metadata(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orgs = db.query(Organization).filter(Organization.user_id == current_user.id).all()
    natures = db.query(FlightNature).filter(FlightNature.user_id == current_user.id).all()
    
    return {
        "operators": list(set([o.name for o in orgs])),
        "labels": list(set([n.name for n in natures]))
    }

@app.get("/upload")
async def read_upload():
    return FileResponse('static/upload.html')

@app.get("/manage")
async def read_manage():
    return FileResponse('static/manage.html')

@app.get("/api/history")
async def get_history(current_user: User = Depends(get_current_user)):
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    # Sort history by date descending for management view
    sorted_history = sorted(logbook.history, key=lambda x: x.get('date_obj', datetime(1900,1,1)), reverse=True)
    return {"history": sorted_history}

@app.delete("/api/entry/{entry_id}")
async def delete_entry(entry_id: str, category: Optional[str] = Query(None), q: Optional[str] = Query(None), current_user: User = Depends(get_current_user)):
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    logbook.delete_entry(entry_id)
    return {"message": "Entry deleted", "data": get_mvp_data(logbook, category=category, query=q)}

@app.post("/api/entries/batch-delete")
async def batch_delete_entries(request: Request, current_user: User = Depends(get_current_user)):
    data = await request.json()
    ids = data.get('ids', [])
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    for entry_id in ids:
        logbook.delete_entry(entry_id)
    return {"message": f"{len(ids)} entries deleted"}

@app.post("/api/entries/batch-edit")
async def batch_edit_entries(request: Request, current_user: User = Depends(get_current_user)):
    try:
        data = await request.json()
        ids = data.get('ids', [])
        updates = data.get('updates', {})
        if not ids:
            return {"message": "No entries selected"}
            
        logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
        count = logbook.batch_update_entries(ids, updates)
        
        # Persist new labels to DB
        db = SessionLocal()
        try:
            if 'operator' in updates and updates['operator'] != "Default":
                org_name = updates['operator']
                if not db.query(Organization).filter(Organization.user_id == current_user.id, Organization.name == org_name).first():
                    db.add(Organization(user_id=current_user.id, name=org_name))
            if 'label' in updates and updates['label'] != "Default":
                nature_name = updates['label']
                if not db.query(FlightNature).filter(FlightNature.user_id == current_user.id, FlightNature.name == nature_name).first():
                    db.add(FlightNature(user_id=current_user.id, name=nature_name))
            db.commit()
        finally:
            db.close()
            
        return {"message": f"{count} entries updated"}
    except Exception as e:
        print(f"[BATCH EDIT ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/entry/{entry_id}")
async def update_entry(entry_id: str, request: Request, category: Optional[str] = Query(None), q: Optional[str] = Query(None), current_user: User = Depends(get_current_user)):
    data = await request.json()
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    logbook.update_entry(entry_id, data)
    
    # Persist new labels to DB
    db = SessionLocal()
    try:
        if 'operator' in data and data['operator'] != "Default":
            org_name = data['operator']
            if not db.query(Organization).filter(Organization.user_id == current_user.id, Organization.name == org_name).first():
                db.add(Organization(user_id=current_user.id, name=org_name))
        if 'label' in data and data['label'] != "Default":
            nature_name = data['label']
            if not db.query(FlightNature).filter(FlightNature.user_id == current_user.id, FlightNature.name == nature_name).first():
                db.add(FlightNature(user_id=current_user.id, name=nature_name))
        db.commit()
    finally:
        db.close()
        
    return {"message": "Entry updated", "data": get_mvp_data(logbook, category=category, query=q)}

@app.post("/api/opening_totals")
async def add_opening_totals(request: Request, category: Optional[str] = Query(None), q: Optional[str] = Query(None), current_user: User = Depends(get_current_user)):
    data = await request.json()
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    
    logbook.add_opening_balance(
        year=data.get('year', 1900),
        ac_type=data.get('ac_type'),
        day_p1=data.get('day_p1', 0),
        day_p1us=data.get('day_p1us', 0),
        day_p2=data.get('day_p2', 0),
        day_dual=data.get('day_put', 0),
        night_p1=data.get('night_p1', 0),
        night_p1us=data.get('night_p1us', 0),
        night_p2=data.get('night_p2', 0),
        night_dual=data.get('night_put', 0),
        inst=data.get('inst', 0),
        sim=data.get('sim', 0),
        label=data.get('label', "Opening Balance"),
        operator=data.get('operator', "Default")
    )
    return {"message": "Opening balance added", "data": get_mvp_data(logbook, category=category, query=q)}

@app.post("/api/import")
async def import_excel(
    file: UploadFile = File(None), 
    is_manual: bool = Form(False),
    operator: str = Form("Default"),
    label: str = Form("Default"),
    confirm_year: bool = Form(False),
    # Manual entry fields
    date: Optional[str] = Form(None),
    ac_type: Optional[str] = Form(None),
    ac_reg: Optional[str] = Form(None),
    pic: Optional[str] = Form(None),
    copilot: Optional[str] = Form(None),
    capacity: Optional[str] = Form(None),
    route: Optional[str] = Form(None),
    dep: Optional[str] = Form(None),
    arr: Optional[str] = Form(None),
    total: float = Form(0.0),
    day_p1: float = Form(0.0),
    day_p1us: float = Form(0.0),
    day_p2: float = Form(0.0),
    day_put: float = Form(0.0),
    night_p1: float = Form(0.0),
    night_p1us: float = Form(0.0),
    night_p2: float = Form(0.0),
    night_put: float = Form(0.0),
    instr: float = Form(0.0),
    sim: float = Form(0.0),
    remarks: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Save new organization if it doesn't exist
    if operator and operator != "Default":
        existing_org = db.query(Organization).filter(Organization.user_id == current_user.id, Organization.name == operator).first()
        if not existing_org:
            new_org = Organization(user_id=current_user.id, name=operator)
            db.add(new_org)
    
    # Save new flight nature if it doesn't exist
    if label and label != "Default":
        existing_nature = db.query(FlightNature).filter(FlightNature.user_id == current_user.id, FlightNature.name == label).first()
        if not existing_nature:
            new_nature = FlightNature(user_id=current_user.id, name=label)
            db.add(new_nature)
    
    db.commit()

    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)

    if is_manual:
        # Date object for internal processing
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
        except:
            date_obj = datetime.now()

        # Construct entry from manual fields, aligned with engine.py/LogbookDashboard keys
        entry = {
            "date_obj": date_obj,
            "date_str": date_obj.strftime('%b %d'),
            "ac_type": ac_type,
            "reg": ac_reg,
            "pic": "SELF" if pic and pic.strip().upper() == (current_user.pilot_name or "").upper() else pic,
            "copilot": "SELF" if copilot and copilot.strip().upper() == (current_user.pilot_name or "").upper() else copilot,
            "capacity": capacity,
            "route": route,
            "dep": dep,
            "arr": arr,
            "day_p1": day_p1,
            "day_p1us": day_p1us,
            "day_p2": day_p2,
            "day_dual": day_put,   # P U/T mapped to dual
            "night_p1": night_p1,
            "night_p1us": night_p1us,
            "night_p2": night_p2,
            "night_dual": night_put, # P U/T mapped to dual
            "inst_flying": instr,
            "sim_time": sim,
            "remarks": remarks,
            "operator": operator,
            "label": label,
            "is_opening": False,
            "is_adjustment": False,
            "timestamp": datetime.now().isoformat()
        }

        logbook.history.append(entry)
        logbook.save_data()
        return {"message": "Manual entry added successfully.", "data": get_mvp_data(logbook)}

    if not file:
        raise HTTPException(status_code=400, detail="No file or manual entry provided.")

    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload an Excel file.")
    
    try:
        contents = await file.read()
        # Read without header first to find the correct header row
        df_raw = pd.read_excel(io.BytesIO(contents), header=None)
        
        # Find the row that contains 'Month/Date' or 'DEP' or other known headers
        header_row_index = 0
        for i, row in df_raw.iterrows():
            row_values = [str(v).strip().upper() for v in row.values if not pd.isna(v)]
            if any(h in row_values for h in ['MONTH/DATE', 'DEP', 'DATE', 'DEPARTURE']):
                header_row_index = i
                break
        
        # Re-read with the correct header row
        df = pd.read_excel(io.BytesIO(contents), header=header_row_index)
        
        logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
        col_map = logbook.detect_columns(df.columns)
        
        print(f"[IMPORT] Header Row Index: {header_row_index}")
        
        print(f"[IMPORT] Detected Columns: {col_map}")
        print(f"[IMPORT] Raw Columns: {list(df.columns)}")
        print(f"[IMPORT] First 2 rows of data: \n{df.head(2)}")
        
        # Check for partial dates if not already confirmed
        if not confirm_year and logbook.has_partial_dates(df, col_map):
            current_year = datetime.now().year
            return JSONResponse(
                status_code=409,
                content={
                    "requires_confirmation": True,
                    "message": f"Some dates in your Excel file are missing the year (e.g., '28-Jan'). Would you like to import them using the current year ({current_year})?"
                }
            )
        
        added_count = 0
        duplicate_count = 0
        for i, row in df.iterrows():
            entry = logbook.parse_ias_row(row, operator=operator, label=label, col_map=col_map)
            if entry:
                if logbook.is_duplicate(entry):
                    duplicate_count += 1
                else:
                    logbook.history.append(entry)
                    added_count += 1
            else:
                if i < 5: # Log first few failures
                    print(f"[IMPORT] Row {i} failed to parse. DEP value: {row.get(col_map.get('DEP'))}")
        
        logbook.save_data()
        msg = f"Successfully imported {added_count} flights for {operator} ({label})."
        if duplicate_count > 0:
            msg += f" {duplicate_count} duplicates skipped."
            
        return {"message": msg, "data": get_mvp_data(logbook)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing Excel: {str(e)}")

@app.post("/api/profile")
async def update_profile(
    pilot_name: str = Form(...),
    full_name: str = Form(None),
    age: int = Form(None),
    license_type: str = Form(None),
    aircraft_type: str = Form(None),
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    current_user.pilot_name = pilot_name
    if full_name: current_user.full_name = full_name
    if age: current_user.age = age
    if license_type: current_user.license_type = license_type
    if aircraft_type: current_user.aircraft_type = aircraft_type
    
    db.commit()
    
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=pilot_name)
    logbook.save_data()
    
    return {"message": f"Profile updated for {pilot_name}", "data": get_mvp_data(logbook)}

@app.get("/api/export_pdf")
async def export_pdf(
    token: str = Query(...), 
    start_page: int = Query(1), 
    end_page: int = Query(None)
):
    try:
        from playwright.async_api import async_playwright
        from PIL import Image
        import os
        import io
        
        base_url = "http://localhost:8000" 
        
        # Save directly to User's Downloads folder
        downloads_path = os.path.expanduser("~/Downloads")
        output_filename = f"Logbook_Export_{start_page}_to_{end_page}.pdf"
        output_path = os.path.join(downloads_path, output_filename)
        
        images = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                viewport={'width': 1800, 'height': 1200},
                device_scale_factor=2
            )
            
            page = await context.new_page()
            
            # 1. Login/Auth
            await page.goto(f"{base_url}/login")
            await page.evaluate(f"localStorage.setItem('logbook_auth_token', '{token}')")
            
            # 2. Preview
            await page.goto(f"{base_url}/preview", wait_until="networkidle")
            await page.wait_for_function("document.querySelectorAll('#page-select option').length > 0", timeout=20000)
            
            # 3. Style cleanup
            await page.add_style_tag(content=".sync-indicator { display: none !important; }")
            
            total_pages = await page.evaluate("document.querySelectorAll('#page-select option').length")
            if end_page is None or end_page > total_pages:
                end_page = total_pages
                
            for p_num in range(start_page, end_page + 1):
                await page.select_option("#page-select", str(p_num - 1))
                await page.wait_for_timeout(800)
                
                element = await page.query_selector("#logbook-printable-area")
                if element:
                    img_data = await element.screenshot(type="png")
                    img = Image.open(io.BytesIO(img_data))
                    if img.mode == 'RGBA':
                        img = img.convert('RGB')
                    images.append(img)
                
            await browser.close()
            
        if not images:
            raise HTTPException(status_code=500, detail="Failed to capture any pages")

        images[0].save(
            output_path, 
            "PDF", 
            save_all=True, 
            append_images=images[1:] if len(images) > 1 else []
        )
            
        return {"status": "success", "message": f"Exported to Downloads folder: {output_filename}", "path": output_path}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8000)
