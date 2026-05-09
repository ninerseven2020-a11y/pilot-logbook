from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, status, Response, Request, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
import pandas as pd
import os
import io
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
import json
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from main import get_mvp_data, add_adjustment, get_logbook_preview
from engine import CAD407Logbook
from pdf_ssr import render_logbook_html
from models import User, SessionLocal, init_db
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

# Allow insecure transport for local development (MUST BE REMOVED IN PRODUCTION)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Security Configuration
SECRET_KEY = "3bf3dcec3423b9b40d911ca20f5f63b66efe78bc201ed5880b5755b4f162d6ed"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 24 hours

app = FastAPI()
try:
    init_db()
    print("Database initialized successfully.")
except Exception as e:
    print(f"Warning: Database initialization failed: {e}")

templates = Jinja2Templates(directory="static")

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

# --- Google OAuth Endpoints ---

@app.get("/api/auth/google/login")
async def google_login(link: Optional[bool] = False, current_user_id: Optional[int] = None):
    print(f"[DEBUG] /api/auth/google/login hit! link={link}, current_user_id={current_user_id}")
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth configuration missing")
    
    # Generate PKCE verifier and challenge
    import secrets
    import hashlib
    import base64
    
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().replace('=', '')
    
    import urllib.parse
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/drive.file",
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256"
    }
    authorization_url = f"https://accounts.google.com/o/oauth2/auth?{urllib.parse.urlencode(params)}"
    
    response = JSONResponse(content={"url": authorization_url})
    # Store verifier and link intent in a secure cookie
    response.set_cookie(key="google_code_verifier", value=code_verifier, httponly=True, max_age=300)
    if link and current_user_id:
        response.set_cookie(key="link_user_id", value=str(current_user_id), httponly=True, max_age=300)
    
    return response

@app.get("/api/auth/google/callback")
async def google_callback(request: Request, code: str, db: Session = Depends(get_db)):
    print("[DEBUG] /api/auth/google/callback hit!")
    try:
        # Retrieve the verifier and linking intent from the cookie
        code_verifier = request.cookies.get("google_code_verifier")
        link_user_id = request.cookies.get("link_user_id")
        
        if not code_verifier:
            raise Exception("Security session expired. Please try logging in again.")

        # Manually exchange the code for tokens
        import requests as httprequests
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier
        }
        
        token_response = httprequests.post(token_url, data=data)
        token_data = token_response.json()
        
        if "error" in token_data:
            raise Exception(f"Google Token Error: {token_data.get('error_description', token_data['error'])}")
            
        access_token = token_data.get("access_token")
        id_token_str = token_data.get("id_token")
        refresh_token = token_data.get("refresh_token")
        
        id_info = id_token.verify_oauth2_token(
            id_token_str, google_requests.Request(), GOOGLE_CLIENT_ID
        )
        
        google_id = id_info.get("sub")
        email = id_info.get("email").lower().strip()
        full_name = id_info.get("name")
        
        user = None
        
        # Scenario A: We are explicitly LINKING an existing logged-in user
        if link_user_id:
            user = db.query(User).filter(User.id == int(link_user_id)).first()
            if user:
                print(f"[DEBUG] Explicitly linking Google ID {google_id} to user {user.username}")
                user.google_id = google_id
                if not user.email: user.email = email
        
        # Scenario B: Standard Login
        if not user:
            user = db.query(User).filter(User.google_id == google_id).first()
            if not user:
                # Fallback check by email (case-insensitive and trimmed)
                user = db.query(User).filter(User.email.ilike(email)).first()
                if user:
                    print(f"[DEBUG] Auto-linking Google ID {google_id} to user {user.username} by email {email}")
                    user.google_id = google_id
                else:
                    print(f"[DEBUG] Creating NEW user for Google email {email}")
                    user = User(
                        username=email,
                        email=email,
                        full_name=full_name,
                        pilot_name=full_name.upper() if full_name else "NEW PILOT",
                        google_id=google_id
                    )
                    db.add(user)
        
        if refresh_token:
            user.google_refresh_token = refresh_token
            
        if email == "ninerseven2020@gmail.com":
            user.is_admin = True
            
        db.commit()
        db.refresh(user)
        
        # Create app JWT
        app_access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        app_access_token = create_access_token(
            data={"sub": user.username}, expires_delta=app_access_token_expires
        )
        
        # Clear the linking cookie
        res = templates.TemplateResponse("google_callback_handler.html", {
            "request": {}, 
            "token": app_access_token
        })
        res.delete_cookie("link_user_id")
        return res
        
    except Exception as e:
        print(f"[GOOGLE CALLBACK ERROR] {str(e)}")
        return HTMLResponse(content=f"<h3>Authentication Error</h3><p>{str(e)}</p><a href='/login'>Back to Login</a>", status_code=400)


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
@app.post("/api/restore")
async def restore_logbook(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    try:
        contents = await file.read()
        data = json.loads(contents)
        
        # Simple validation: Check if it looks like a logbook
        if "history" not in data or "sync_adjustments" not in data:
            raise Exception("Invalid logbook format. Missing history or sync_adjustments.")
            
        logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
        
        # Replace current data with uploaded data
        logbook.history = data["history"]
        logbook.sync_adjustments = data["sync_adjustments"]
        
        # Preserve aircraft DB if present
        if "COLUMN_MAP" in data:
            logbook.COLUMN_MAP = data["COLUMN_MAP"]
            
        logbook.save_data()
        
        return {"message": "Logbook restored successfully", "data": get_mvp_data(logbook)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/export_json")
async def export_json(current_user: User = Depends(get_current_user)):
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    if os.path.exists(logbook.storage_file):
        return FileResponse(logbook.storage_file, media_type="application/json", filename=f"logbook_backup_{datetime.now().strftime('%Y%m%d')}.json")
    raise HTTPException(status_code=404, detail="No logbook file found.")

@app.post("/api/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/admin")
async def read_admin():
    return FileResponse('static/admin.html')

@app.get("/api/admin/users")
async def get_admin_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    users = db.query(User).all()
    user_list = []
    for u in users:
        # Check flight count from their logbook JSON
        pilot_logbook = CAD407Logbook(user_id=u.id, pilot_name=u.pilot_name)
        flight_count = len(pilot_logbook.history)
        
        user_list.append({
            "id": u.id,
            "username": u.username,
            "pilot_name": u.pilot_name,
            "email": u.email,
            "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "flight_count": flight_count
        })
    return user_list

from pydantic import BaseModel
class MergeRequest(BaseModel):
    source_id: int
    target_id: int

@app.post("/api/admin/merge_users")
async def merge_users(req: MergeRequest, admin_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not admin_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    source = db.query(User).filter(User.id == req.source_id).first()
    target = db.query(User).filter(User.id == req.target_id).first()
    
    if not source or not target:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 1. Merge Logbooks (Physical Syncs + Flight History)
    source_lb = CAD407Logbook(user_id=source.id, pilot_name=source.pilot_name)
    target_lb = CAD407Logbook(user_id=target.id, pilot_name=target.pilot_name)
    
    # Append history and sync adjustments (Paper Syncs)
    target_lb.history.extend(source_lb.history)
    target_lb.sync_adjustments.extend(source_lb.sync_adjustments)
    target_lb.save_data()
    
    # 2. Transfer Database Relationships (Organizations + Flight Natures)
    db.query(Organization).filter(Organization.user_id == source.id).update({"user_id": target.id})
    db.query(FlightNature).filter(FlightNature.user_id == source.id).update({"user_id": target.id})
    
    # 4. Clean up source files and record
    if os.path.exists(source_lb.storage_file):
        os.remove(source_lb.storage_file)
        
    db.delete(source)
    db.commit()
    
    return {"status": "success", "message": f"Merged {source.username} into {target.username}"}
@app.get("/api/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "pilot_name": current_user.pilot_name,
        "age": current_user.age,
        "email": current_user.email,
        "license_type": current_user.license_type,
        "aircraft_type": current_user.aircraft_type,
        "is_google_user": current_user.google_id is not None,
        "is_admin": current_user.is_admin
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

@app.get("/api/synonyms")
async def get_synonyms(user: User = Depends(get_current_user)):
    logbook = CAD407Logbook(user_id=user.id, pilot_name=user.pilot_name)
    return logbook.COLUMN_MAP

@app.post("/api/synonyms")
async def update_synonyms(new_map: dict, user: User = Depends(get_current_user)):
    logbook = CAD407Logbook(user_id=user.id, pilot_name=user.pilot_name)
    logbook.update_synonyms(new_map)
    return {"message": "Synonyms updated successfully"}

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
            "dep_time": dep,
            "arr_time": arr,
            "flight_id": "", # Added for consistency
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
        # Dynamic header detection using DEP synonyms
        logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
        dep_synonyms = [s.upper() for s in logbook.COLUMN_MAP.get('DEP', [])]
        
        header_row_index = 0
        for i, row in df_raw.iterrows():
            row_values = [str(v).strip().upper() for v in row.values if not pd.isna(v)]
            if any(h in row_values for h in dep_synonyms):
                header_row_index = i
                break
        
        # Re-read with the correct header row
        df = pd.read_excel(io.BytesIO(contents), header=header_row_index)
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
        updated_count = 0
        for i, row in df.iterrows():
            entry = logbook.parse_ias_row(row, operator=operator, label=label, col_map=col_map)
            if entry:
                # SMART UPDATE: Find existing entry by flight ID
                existing = next((h for h in logbook.history if h.get('flight_id') == entry['flight_id']), None)
                if existing:
                    # Refresh with new parser logic (metadata, cleaned route/remarks, and specific times)
                    existing['metadata'] = entry.get('metadata', {})
                    existing['remarks'] = entry.get('remarks', '')
                    existing['route'] = entry.get('route', '')
                    existing['dep_time'] = entry.get('dep_time', '')
                    existing['arr_time'] = entry.get('arr_time', '')
                    
                    # Refresh flying hours (to fix rounding or data changes)
                    for h_col in ['day_p1', 'day_p1us', 'day_p2', 'day_dual', 'night_p1', 'night_p1us', 'night_p2', 'night_dual', 'inst_flying', 'sim_time']:
                        existing[h_col] = entry.get(h_col, 0.0)
                else:
                    logbook.history.append(entry)
                    added_count += 1
            else:
                if i < 5:
                    print(f"[IMPORT] Row {i} failed to parse.")
        
        logbook.save_data()
        msg = f"Import complete: {added_count} new flights, {updated_count} records refreshed."
            
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
    email: str = Form(None),
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    print(f"[DEBUG] Profile update request: pilot_name={pilot_name}, email={email}")
    current_user.pilot_name = pilot_name
    if full_name: current_user.full_name = full_name
    if age: current_user.age = age
    if license_type: current_user.license_type = license_type
    if aircraft_type: current_user.aircraft_type = aircraft_type
    if email: 
        current_user.email = email
        print(f"[DEBUG] Saving email to DB: {email}")
    
    db.commit()
    print(f"[DEBUG] DB commit successful for user {current_user.username}")
    
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=pilot_name)
    logbook.save_data()
    
    return {"message": f"Profile updated for {pilot_name}", "data": get_mvp_data(logbook)}

@app.get("/api/export_pdf")
async def export_pdf(
    token: str = Query(...),
    current_user: User = Depends(get_current_user),
    start_page: int = Query(1), 
    end_page: int = Query(None)
):
    try:
        from pdf_ssr import render_logbook_html, render_pdf_local
        
        # 1. Generate the HTML content
        html_content = render_logbook_html(current_user, start_page=start_page, end_page=end_page)
        
        # 2. Define path
        filename = f"Logbook_Export_{start_page}.pdf"
        output_path = os.path.join("/tmp", filename)
        
        # 3. Render locally via Playwright (V10 screenshot style)
        port = int(os.getenv("PORT", 8000))
        # Get the token from query params or auth header
        auth_token = token
        
        await render_pdf_local(html_content, output_path, auth_token, port=port)
        
        return FileResponse(
            path=output_path,
            media_type="application/pdf",
            filename=filename
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF Generation Failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8000)
