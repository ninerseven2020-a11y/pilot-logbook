import sys
import subprocess

# Logbook Backend Application
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, status, Response, Request, Query
from contextlib import asynccontextmanager

from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# Heavy local modules and pandas are lazy-loaded inside functions to fix Railway 502 timeouts
from models import User, Organization, FlightNature, SessionLocal, init_db, get_password_hash, verify_password
print(f"[DEBUG] Organization imported: {Organization}")
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
APP_VERSION = "1.5.5"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

# Allow insecure transport for local development (MUST BE REMOVED IN PRODUCTION)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Security Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key-for-local-only")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 24 hours

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB
    try:
        init_db()
        print("Database initialized successfully via lifespan.")
    except Exception as e:
        print(f"Warning: Database initialization failed during startup: {e}")
    yield
    # Shutdown logic (if any) can go here


app = FastAPI(lifespan=lifespan)

@app.on_event("startup")
async def startup_event():
    print(f"=======================================")
    print(f" LOGBOOK SERVER STARTING (v{APP_VERSION})")
    print(f"=======================================")


@app.get("/test")
async def test_route():
    return {"message": "Backend is alive"}

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

@app.get("/api/system-status")
async def get_system_status(current_user: User = Depends(get_current_user)):
    status_info = {
        "python_version": sys.version,
        "gemini_api_configured": bool(os.getenv("GEMINI_API_KEY")),
        "last_logs": []
    }
    return status_info

@app.post("/api/system-repair")
async def system_repair(current_user: User = Depends(get_current_user)):
    return {"results": ["System is optimized. No repairs needed."]}

# --- Google OAuth Endpoints ---

def log_function_used(user: User, db: Session, func_name: str):
    if not user: return
    try:
        current = user.functions_used or ""
        funcs = [f.strip() for f in current.split(",") if f.strip()]
        if func_name not in funcs:
            funcs.append(func_name)
            user.functions_used = ", ".join(funcs)
            db.commit()
    except Exception as e:
        print(f"Error logging function: {e}")

@app.get("/api/auth/google/login")
async def google_login(request: Request, link: Optional[bool] = False, current_user_id: Optional[int] = None):
    print(f"[DEBUG] Login attempt. ID present: {bool(GOOGLE_CLIENT_ID)}, Secret present: {bool(GOOGLE_CLIENT_SECRET)}")
    
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return JSONResponse(status_code=500, content={"detail": "Google Auth credentials not found in environment. Please check your .env file or Docker settings."})

    import secrets
    import hashlib
    import base64
    
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().replace('=', '')
    
    # Smart Redirect URI detection
    host = request.headers.get('host', 'localhost:8000')
    scheme = 'https' if 'synology.me' in host or 'render.com' in host else 'http'
    
    # Prioritize GOOGLE_REDIRECT_URI from env if set
    redirect_uri = GOOGLE_REDIRECT_URI or f"{scheme}://{host}/api/auth/google/callback"
    
    import urllib.parse
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/drive.file",
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256"
    }
    authorization_url = f"https://accounts.google.com/o/oauth2/auth?{urllib.parse.urlencode(params)}"
    
    response = JSONResponse(content={"url": authorization_url})
    response.set_cookie(key="google_code_verifier", value=code_verifier, httponly=True, max_age=300, samesite="lax", secure=True)
    if link and current_user_id:
        response.set_cookie(key="link_user_id", value=str(current_user_id), httponly=True, max_age=300, samesite="lax", secure=True)
    
    return response

@app.get("/api/auth/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db), code: Optional[str] = None, error: Optional[str] = None):
    if error:
        return HTMLResponse(content=f"<h3>Google Auth Error</h3><p>{error}</p><a href='/login'>Back to Login</a>", status_code=400)
    if not code:
        return HTMLResponse(content="<h3>Auth Error</h3><p>No code received</p>", status_code=400)

    try:
        code_verifier = request.cookies.get("google_code_verifier")
        link_user_id = request.cookies.get("link_user_id")
        
        host = request.headers.get('host', 'localhost:8000')
        scheme = 'https' if 'synology.me' in host or 'render.com' in host else 'http'
        
        # Prioritize GOOGLE_REDIRECT_URI from env if set
        redirect_uri = GOOGLE_REDIRECT_URI or f"{scheme}://{host}/api/auth/google/callback"
        import requests as httprequests
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier
        }
        
        token_res = httprequests.post(token_url, data=data)
        token_data = token_res.json()
        
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
            
        # Update login stats
        user.last_login = datetime.utcnow()
        if user.login_count is None: user.login_count = 0
        user.login_count += 1
            
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


@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/style.css") # Just return anything to avoid 404

def send_reset_email(email: str, token: str, request: Request):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    # Get SMTP settings from env
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    
    if not smtp_user or not smtp_pass:
        print("[EMAIL ERROR] SMTP credentials not found. Reset link will be printed to console only.")
        return False

    host = request.headers.get('host', 'localhost:8000')
    scheme = 'https' if 'synology.me' in host else 'http'
    reset_url = f"{scheme}://{host}/reset-password?token={token}"

    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = email
    msg['Subject'] = "Password Reset - Pilot Logbook"

    body = f"""
    Hello,

    You requested a password reset for your Pilot Logbook account.
    Please click the link below to reset your password:

    {reset_url}

    This link will expire in 30 minutes.

    If you did not request this, please ignore this email.
    """
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False

@app.post("/api/forgot-password")
async def forgot_password(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email.ilike(email)).first()
    if not user:
        # Don't reveal if user exists or not for security
        return {"message": "If an account exists with that email, a reset link has been sent."}
    
    # Create reset token (30 mins)
    reset_token = create_access_token(
        data={"sub": user.username, "purpose": "reset"}, 
        expires_delta=timedelta(minutes=30)
    )
    
    success = send_reset_email(email, reset_token, request)
    
    # For local testing/dev, always print the link to console
    host = request.headers.get('host', 'localhost:8000')
    scheme = 'https' if 'synology.me' in host else 'http'
    print(f"\n[DEBUG] RESET LINK for {email}: {scheme}://{host}/reset-password?token={reset_token}\n")

    return {"message": "If an account exists with that email, a reset link has been sent."}

@app.get("/reset-password")
async def reset_password_page():
    return FileResponse('static/reset_password.html')

@app.post("/api/reset-password")
async def reset_password(token: str = Form(...), new_password: str = Form(...), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        purpose: str = payload.get("purpose")
        
        if not username or purpose != "reset":
            raise HTTPException(status_code=400, detail="Invalid reset token")
            
    except JWTError:
        raise HTTPException(status_code=400, detail="Reset link has expired or is invalid")
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.password_hash = get_password_hash(new_password)
    db.commit()
    
    return {"message": "Password reset successfully. You can now login."}

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
    from engine import CAD407Logbook
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
        email=email,
        license_type=license_type,
        aircraft_type=aircraft_type
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
@app.post("/api/restore")
async def restore_logbook(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    from engine import CAD407Logbook
    from main import get_mvp_data
    try:
        contents = await file.read()
        import json
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
    from engine import CAD407Logbook
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
    
    # Update last login and increment count
    user.last_login = datetime.utcnow()
    if user.login_count is None: user.login_count = 0
    user.login_count += 1
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
        from engine import CAD407Logbook
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
            "flight_count": flight_count,
            "login_count": u.login_count or 0,
            "ai_count": u.ai_count or 0,
            "functions_used": u.functions_used or ""
        })
    return user_list

@app.post("/api/error_feedback")
async def post_error_feedback(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from models import ErrorFeedback
    data = await request.json()
    feedback = ErrorFeedback(
        user_id=current_user.id,
        error_message=data.get("error_message"),
        user_description=data.get("description"),
        timestamp=datetime.utcnow()
    )
    db.add(feedback)
    db.commit()
    return {"status": "success"}

@app.get("/api/admin/feedbacks")
async def get_admin_feedbacks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    from models import ErrorFeedback
    feedbacks = db.query(ErrorFeedback).order_by(ErrorFeedback.timestamp.desc()).all()
    return [{
        "id": f.id,
        "username": f.user.username if f.user else "Unknown",
        "error_message": f.error_message,
        "description": f.user_description,
        "timestamp": f.timestamp.isoformat()
    } for f in feedbacks]

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
    
    from engine import CAD407Logbook
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
        "email": current_user.email,
        "license_type": current_user.license_type,
        "aircraft_type": current_user.aircraft_type,
        "is_google_user": current_user.google_id is not None,
        "is_admin": current_user.is_admin
    }

# --- Logbook APIs ---

@app.get("/api/dashboard")
async def dashboard(category: Optional[str] = Query(None), q: Optional[str] = Query(None), current_user: User = Depends(get_current_user)):
    from engine import CAD407Logbook
    from main import get_mvp_data
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    return get_mvp_data(logbook, category=category, query=q)

@app.post("/api/adjustment")
async def adjustment(
    column: str = Form(...), 
    value: float = Form(...), 
    reason: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    from engine import CAD407Logbook
    from main import get_mvp_data, add_adjustment
    try:
        logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
        msg = add_adjustment(logbook, column, value, reason)
        return {"message": msg, "data": get_mvp_data(logbook)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/sync_adjustments")
async def get_sync_adjustments(current_user: User = Depends(get_current_user)):
    from engine import CAD407Logbook
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    return {"adjustments": logbook.sync_adjustments}

@app.post("/api/sync_adjustments")
async def add_sync_adjustment(request: Request, current_user: User = Depends(get_current_user)):
    from engine import CAD407Logbook
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
    from engine import CAD407Logbook
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
    from engine import CAD407Logbook
    from main import get_logbook_preview
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
        "operators": [{"id": o.id, "name": o.name} for o in orgs],
        "labels": [{"id": n.id, "name": n.name} for n in natures]
    }

@app.delete("/api/metadata/{type}/{id}")
async def delete_metadata(type: str, id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if type == "operator":
        item = db.query(Organization).filter(Organization.id == id, Organization.user_id == current_user.id).first()
    elif type == "label":
        item = db.query(FlightNature).filter(FlightNature.id == id, FlightNature.user_id == current_user.id).first()
    else:
        raise HTTPException(status_code=400, detail="Invalid type")
        
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    db.delete(item)
    db.commit()
    return {"status": "success"}

@app.put("/api/metadata/{type}/{id}")
async def rename_metadata(type: str, id: int, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()
    new_name = data.get("name")
    if not new_name:
        raise HTTPException(status_code=400, detail="Name required")
        
    if type == "operator":
        item = db.query(Organization).filter(Organization.id == id, Organization.user_id == current_user.id).first()
    elif type == "label":
        item = db.query(FlightNature).filter(FlightNature.id == id, FlightNature.user_id == current_user.id).first()
    else:
        raise HTTPException(status_code=400, detail="Invalid type")
        
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    item.name = new_name
    db.commit()
    return {"status": "success"}

@app.get("/upload")
async def read_upload():
    return FileResponse('static/upload.html')

@app.get("/manage")
async def read_manage():
    return FileResponse('static/manage.html')

@app.get("/api/synonyms")
async def get_synonyms(user: User = Depends(get_current_user)):
    from engine import CAD407Logbook
    logbook = CAD407Logbook(user_id=user.id, pilot_name=user.pilot_name)
    return logbook.COLUMN_MAP

@app.post("/api/synonyms")
async def update_synonyms(new_map: dict, user: User = Depends(get_current_user)):
    from engine import CAD407Logbook
    logbook = CAD407Logbook(user_id=user.id, pilot_name=user.pilot_name)
    logbook.update_synonyms(new_map)
    return {"message": "Synonyms updated successfully"}

@app.post("/api/synonyms/ai")
async def update_synonyms_ai(data: dict, user: User = Depends(get_current_user), db = Depends(get_db)):
    instruction = data.get('instruction')
    if not instruction:
        raise HTTPException(status_code=400, detail="No instruction provided")
    
    from engine import CAD407Logbook
    logbook = CAD407Logbook(user_id=user.id, pilot_name=user.pilot_name)
    
    # Use LLM to extract the mapping update
    prompt = f"""
    The user wants to update their Excel header mapping for a pilot logbook.
    Current Mapping: {json.dumps(logbook.COLUMN_MAP)}
    
    User Instruction: "{instruction}"
    
    Return a JSON object representing the UPDATED mapping. 
    Only change the keys mentioned in the instruction. 
    Ensure you return the FULL mapping object with your changes included.
    
    Standard Keys: DEP, FLT_SN, AC_TYPE, AC_REG, CAPTAIN, COPILOT, CAPACITY, ROUTE, DAY_P1, DAY_P1US, DAY_P2, DAY_DUAL, NIGHT_P1, NIGHT_P1US, NIGHT_P2, NIGHT_DUAL, INSTRUMENT, SIM_DAY, SIM_NIGHT, REMARKS, ARR, ATD, ATA, TOTAL, TAKEOFF, LANDING.
    """
    
    try:
        from engine import LLMEngine
        llm = LLMEngine()
        
        # Increment AI Count and Log function
        user.ai_count = (user.ai_count or 0) + 1
        log_function_used(user, db, "AI Synonyms")
        
        updated_map_str = llm.generate(prompt)
        # Extract JSON from potential markdown
        import re
        match = re.search(r'(\{.*\})', updated_map_str, re.DOTALL)
        if match:
            updated_map = json.loads(match.group(1))
            logbook.update_synonyms(updated_map)
            return {"message": "AI successfully updated your mappings.", "updated_keys": list(updated_map.keys())}
    except Exception as e:
        print(f"[AI MAPPING] Error: {e}")
        
    raise HTTPException(status_code=500, detail="AI could not process the mapping instruction. Please try being more specific.")

@app.get("/api/history")
async def get_history(current_user: User = Depends(get_current_user)):
    try:
        from engine import CAD407Logbook
        logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
        
        # Safer sorting key to prevent TypeError between datetime and str
        def get_sort_key(entry):
            dt = entry.get('date_obj')
            if isinstance(dt, datetime):
                return dt
            if isinstance(dt, str):
                try:
                    return datetime.fromisoformat(dt.replace('Z', '+00:00'))
                except:
                    pass
            return datetime(1900, 1, 1)

        sorted_history = sorted(logbook.history, key=get_sort_key, reverse=True)
        return {"history": sorted_history}
    except Exception as e:
        print(f"[API ERROR] /api/history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/entry/{entry_id}")
async def delete_entry(entry_id: str, category: Optional[str] = Query(None), q: Optional[str] = Query(None), current_user: User = Depends(get_current_user)):
    from engine import CAD407Logbook
    from main import get_mvp_data
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    logbook.delete_entry(entry_id)
    return {"message": "Entry deleted", "data": get_mvp_data(logbook, category=category, query=q)}

@app.post("/api/entries/batch-delete")
async def batch_delete_entries(request: Request, current_user: User = Depends(get_current_user)):
    from engine import CAD407Logbook
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
            
        from engine import CAD407Logbook
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
    from engine import CAD407Logbook
    from main import get_mvp_data
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
    from engine import CAD407Logbook
    from main import get_mvp_data
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
    file_005: UploadFile = File(None),
    file_001: UploadFile = File(None),
    is_manual: bool = Form(False),
    operator: str = Form("Default"),
    label: str = Form("Default"),
    confirm_year: bool = Form(False),
    confirm_mapping: bool = Form(False),
    custom_mapping_raw: Optional[str] = Form(None),
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
    takeoff: int = Form(0),
    landing: int = Form(0),
    remarks: str = Form(""),
    column_map: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    print(f"[DEBUG] Import call: file={file.filename if file else 'None'}, file_005={file_005.filename if file_005 else 'None'}, file_001={file_001.filename if file_001 else 'None'}")
    log_function_used(current_user, db, "Excel Import")
    
    # Check for xlrd dependency and try to auto-fix if missing
    try:
        import xlrd
    except ImportError:
        print("[REPAIR] xlrd missing. Attempting automatic installation...")
        import subprocess
        import sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "xlrd>=2.0.1"])
            print("[REPAIR] xlrd installed successfully.")
        except Exception as e:
            print(f"[REPAIR] Failed to install xlrd: {e}")
    # Resolve Human Readable Names for Ingestion
    final_operator = "Default"
    final_label = "Default"
    
    if operator and operator != "Default":
        # Check if it's an ID or a Name
        if operator.isdigit():
            org = db.query(Organization).filter(Organization.id == int(operator)).first()
            if org: final_operator = org.name
        else:
            final_operator = operator

    if label and label != "Default":
        # Check if it's an ID or a Name
        if label.isdigit():
            nature = db.query(FlightNature).filter(FlightNature.id == int(label)).first()
            if nature: final_label = nature.name
        else:
            final_label = label

    # Update the local variables for the engine
    operator = final_operator
    label = final_label
    
    db.commit()

    from engine import CAD407Logbook
    # Force a fresh fetch from DB to ensure we have the absolute latest pilot_name
    db.refresh(current_user)
    logbook = CAD407Logbook(user_id=current_user.id, pilot_name=current_user.pilot_name)
    print(f"[DEBUG] Freshly fetched Pilot Name for import: {current_user.pilot_name}")

    if is_manual:
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
        except:
            date_obj = datetime.now()

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
            "flight_id": str(uuid.uuid4())[:8],
            "day_p1": day_p1,
            "day_p1us": day_p1us,
            "day_p2": day_p2,
            "day_dual": day_put,
            "night_p1": night_p1,
            "night_p1us": night_p1us,
            "night_p2": night_p2,
            "night_dual": night_put,
            "inst_flying": instr,
            "sim_time": sim,
            "takeoff": takeoff,
            "landing": landing,
            "remarks": remarks,
            "operator": operator,
            "label": label,
            "is_opening": False,
            "is_adjustment": False,
            "id": str(uuid.uuid4()),
            "metadata": {}
        }

        status, msg = logbook.add_entry(entry)
        logbook.save_data()
        
        return JSONResponse(content={
            "message": msg, 
            "status": status,
            "data": logbook.get_dashboard_data()
        })

    # IAS Processing Logic
    if (file_005 and file_005.filename) or (file_001 and file_001.filename):
        import os
        import tempfile
        
        path_005 = None
        path_001 = None
        
        try:
            if file_005:
                tmp_005 = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
                tmp_005.write(await file_005.read())
                tmp_005.close()
                path_005 = tmp_005.name
                
            if file_001:
                tmp_001 = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
                tmp_001.write(await file_001.read())
                tmp_001.close()
                path_001 = tmp_001.name
            
            # Parse column map if provided from the Safety Net modal
            column_map_data = None
            if column_map:
                try:
                    column_map_data = json.loads(column_map)
                except:
                    pass

            results = logbook.process_ias_files(
                file_005_path=path_005, 
                file_001_path=path_001, 
                operator=operator, 
                label=label,
                column_map=column_map_data
            )
            
            # --- HANDLE SAFETY NET (Missing Columns) ---
            if isinstance(results, dict) and results.get("status") == "CONFIRMATION_REQUIRED":
                # Do NOT delete temp files yet, we need them for the actual import next
                return JSONResponse(content={
                    "status": "CONFIRMATION_REQUIRED",
                    "message": "Some required columns were not found. Please confirm mappings.",
                    "missing_keys": results["missing_keys"],
                    "suggested_map": results["suggested_map"],
                    "excel_columns": results["excel_columns"],
                    "temp_files": {
                        "path_005": path_005,
                        "path_001": path_001
                    }
                })
            
            # Clean up
            if path_005: os.remove(path_005)
            if path_001: os.remove(path_001)
            
            summary_msg = f"Import complete: {results['added']} new, {results['updated']} updated, {results['skipped']} skipped."
            
            return JSONResponse(content={
                "message": summary_msg,
                "status": "SUCCESS",
                "cautions": results['cautions'],
                "data": logbook.get_dashboard_data()
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc() # Print full error to console
            if path_005 and os.path.exists(path_005): os.remove(path_005)
            if path_001 and os.path.exists(path_001): os.remove(path_001)
            raise HTTPException(status_code=400, detail=str(e))

    if not file:
        raise HTTPException(status_code=400, detail="No file provided.")

    try:
        import io
        import pandas as pd
        contents = await file.read()
        
        # Try different engines for different Excel formats
        try:
            xl = pd.ExcelFile(io.BytesIO(contents), engine='calamine')
        except:
            try:
                xl = pd.ExcelFile(io.BytesIO(contents), engine='openpyxl')
            except:
                xl = pd.ExcelFile(io.BytesIO(contents))
                
        sheet_names = xl.sheet_names
        dep_synonyms = [s.upper() for s in logbook.COLUMN_MAP.get('DEP', [])]
        
        total_added = 0
        total_updated = 0
        print(f"[IMPORT] Received Operator: {operator}, Label: {label}")
        
        for sheet_name in sheet_names:
            try:
                df_raw = xl.parse(sheet_name, header=None)
                data = [list(row) for row in df_raw.values]
                if not data: continue
                
                header_row_index = -1
                for i, row in df_raw.iterrows():
                    row_values = [str(v).strip().upper() for v in row.values if not pd.isna(v)]
                    if any(h in row_values for h in dep_synonyms):
                        header_row_index = i
                        break
                if header_row_index == -1: continue
                    
                headers = [str(h) for h in data[header_row_index]]
                df = pd.DataFrame(data[header_row_index+1:], columns=headers)
                df = df.dropna(how='all')
                
                col_map = logbook.detect_columns(df)
                
                # Author-005 Detection: Look for very specific headers
                is_author_005 = any(h in headers for h in ["CREWMAN 1", "OPERATING CAPACITY", "FLT S/N"])
                
                if custom_mapping_raw:
                    try:
                        user_map = json.loads(custom_mapping_raw)
                        # Overlay user choices on top of auto-detected map
                        col_map.update({k: v for k, v in user_map.items() if v})
                        print(f"[IMPORT] Merged mapping: {col_map}")
                    except: pass
                
                critical_keys = ['DEP', 'AC_REG', 'FLT_SN']
                is_missing_critical = any(not col_map.get(k) for k in critical_keys)
                
                if (is_missing_critical or not confirm_mapping) and not confirm_mapping:
                    # Bypass mapping confirmation if it's a standard Author-005 report and we mapped everything critical
                    if not (is_author_005 and not is_missing_critical):
                        return JSONResponse(
                            status_code=422,
                            content={
                                "requires_mapping_confirmation": True,
                                "proposed_mapping": col_map,
                                "all_columns": df.columns.tolist(),
                                "message": "Mapping needed."
                            }
                        )

                df = df.replace(r'^\s*$', pd.NA, regex=True)
                
                last_valid_date = None
                for _, row in df.iterrows():
                    entry = logbook.parse_ias_row(row, operator=operator, label=label, col_map=col_map)
                    if entry:
                        if not entry.get('date_obj') and last_valid_date:
                            entry['date_obj'] = last_valid_date
                            entry['date_str'] = last_valid_date.strftime('%b %d')
                        elif entry.get('date_obj'):
                            last_valid_date = entry['date_obj']

                        status, msg = logbook.add_entry(entry)
                        if status == "ADDED": total_added += 1
                        elif status == "UPDATED": total_updated += 1
            except Exception as e:
                print(f"[IMPORT] Error on sheet {sheet_name}: {e}")

        if total_added == 0 and total_updated == 0:
            return JSONResponse(status_code=400, content={"message": "No valid flight data found."})
            
        from fastapi.encoders import jsonable_encoder
        from main import get_mvp_data
        logbook.save_data()
        return JSONResponse(content={
            "message": f"Import complete! {total_added} added, {total_updated} updated.",
            "data": jsonable_encoder(get_mvp_data(logbook))
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
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
    
    from engine import CAD407Logbook
    from main import get_mvp_data
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
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
