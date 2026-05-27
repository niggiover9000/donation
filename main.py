from fastapi import FastAPI, Depends, Request, Form, Response, Cookie, HTTPException, status
from contextlib import asynccontextmanager
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import uuid
from typing import Optional
import os
from datetime import datetime

import models
from database import engine, get_db

from sqlalchemy import text

# Create DB tables
models.Base.metadata.create_all(bind=engine)

# Auto-migrate database (adds columns if they don't exist yet, useful for Docker deployments)
with engine.begin() as conn:
    for col in ["org1", "org2", "org3", "deadline"]:
        try:
            conn.execute(text(f"ALTER TABLE settings ADD COLUMN {col} VARCHAR DEFAULT ''"))
        except Exception:
            pass
    for col in ["feature_ticker", "feature_leaderboard", "feature_goal"]:
        try:
            conn.execute(text(f"ALTER TABLE settings ADD COLUMN {col} BOOLEAN DEFAULT 0"))
        except Exception:
            pass
    try:
        conn.execute(text("ALTER TABLE settings ADD COLUMN goal_amount FLOAT DEFAULT 1000.0"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE settings ADD COLUMN paypal_link VARCHAR DEFAULT 'https://paypal.me/'"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE bids ADD COLUMN organization VARCHAR DEFAULT ''"))
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE bids ADD COLUMN bonus_points FLOAT DEFAULT 0.0"))
    except Exception:
        pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize settings if not exists
    db = next(get_db())
    settings = db.query(models.Settings).first()
    if not settings:
        settings = models.Settings(min_bid=10.0)
        db.add(settings)
        db.commit()
    yield

app = FastAPI(lifespan=lifespan)

# Mount static files (CSS, JS)
os.makedirs(os.path.join("static", "sounds"), exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

def get_sounds():
    try:
        return [f for f in os.listdir(os.path.join("static", "sounds")) if f.endswith((".mp3", ".wav", ".ogg"))]
    except FileNotFoundError:
        return []

def get_social_features_context(db: Session, settings: models.Settings):
    context = {
        "recent_bids": [],
        "top_bids": [],
        "total_amount": 0.0,
        "donor_count": 0
    }
    if settings:
        if settings.feature_ticker:
            context["recent_bids"] = db.query(models.Bid).order_by(models.Bid.id.desc()).limit(5).all()
        if settings.feature_leaderboard:
            all_bids = db.query(models.Bid).all()
            sorted_bids = sorted(all_bids, key=lambda b: b.amount + (b.bonus_points or 0.0), reverse=True)
            context["top_bids"] = sorted_bids[:3]
        if settings.feature_goal:
            all_bids = db.query(models.Bid).all()
            context["total_amount"] = sum(b.amount + (b.bonus_points or 0.0) for b in all_bids)
            context["donor_count"] = len(all_bids)
    return context

# Templates
templates = Jinja2Templates(directory="templates")

# Admin Password (from environment variable or default)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

@app.get("/", response_class=HTMLResponse)
def index(request: Request, bid_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    settings = db.query(models.Settings).first()
    min_bid = settings.min_bid if settings else 10.0
    
    existing_bid = None
    if bid_token:
        existing_bid = db.query(models.Bid).filter(models.Bid.token == bid_token).first()
        
    context = {
        "request": request, 
        "min_bid": min_bid,
        "settings": settings,
        "existing_bid": existing_bid,
        "sounds": get_sounds()
    }
    context.update(get_social_features_context(db, settings))
        
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=context
    )

@app.post("/bid")
def submit_bid(
    request: Request,
    response: Response,
    name: str = Form(...),
    amount: float = Form(...),
    commitment: Optional[str] = Form(None),
    organization: Optional[str] = Form(None),
    bid_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    settings = db.query(models.Settings).first()
    min_bid = settings.min_bid if settings else 10.0
    
    existing_bid = None
    if bid_token:
        existing_bid = db.query(models.Bid).filter(models.Bid.token == bid_token).first()

    if settings and settings.deadline:
        try:
            deadline_dt = datetime.fromisoformat(settings.deadline)
            if datetime.now() > deadline_dt:
                context = {
                    "request": request,
                    "min_bid": min_bid,
                    "settings": settings,
                    "error": "Die Frist für Gebote ist bereits abgelaufen.",
                    "existing_bid": existing_bid,
                    "sounds": get_sounds()
                }
                context.update(get_social_features_context(db, settings))
                return templates.TemplateResponse(request=request, name="index.html", context=context)
        except ValueError:
            pass

    if amount < min_bid:
        context = {
            "request": request,
            "min_bid": min_bid,
            "settings": settings,
            "error": f"Das Gebot muss mindestens {min_bid} betragen.",
            "existing_bid": existing_bid,
            "sounds": get_sounds()
        }
        context.update(get_social_features_context(db, settings))
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=context
        )

    if not commitment:
        context = {
            "request": request,
            "min_bid": min_bid,
            "settings": settings,
            "error": "Bitte bestätige, dass dein Gebot verbindlich ist.",
            "existing_bid": existing_bid,
            "sounds": get_sounds()
        }
        context.update(get_social_features_context(db, settings))
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=context
        )

    available_orgs = []
    if settings:
        if settings.org1: available_orgs.append(settings.org1)
        if settings.org2: available_orgs.append(settings.org2)
        if settings.org3: available_orgs.append(settings.org3)
    
    if available_orgs and not organization:
        context = {
            "request": request,
            "min_bid": min_bid,
            "settings": settings,
            "error": "Bitte wähle eine Spendenorganisation aus.",
            "existing_bid": existing_bid,
            "sounds": get_sounds()
        }
        context.update(get_social_features_context(db, settings))
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=context
        )

    if existing_bid:
        existing_bid.name = name
        existing_bid.amount = amount
        if organization:
            existing_bid.organization = organization
        db.commit()
        return RedirectResponse(url="/?success=updated", status_code=status.HTTP_303_SEE_OTHER)

    # New bid
    new_token = str(uuid.uuid4())
    new_bid = models.Bid(name=name, amount=amount, token=new_token, organization=organization or "")
    db.add(new_bid)
    db.commit()
    
    res = RedirectResponse(url="/?success=created", status_code=status.HTTP_303_SEE_OTHER)
    res.set_cookie(key="bid_token", value=new_token, max_age=60*60*24*365) # 1 year
    return res

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request})

@app.post("/login")
def login(password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        res = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        res.set_cookie(key="admin_token", value="authenticated", httponly=True)
        return res
    return RedirectResponse(url="/login?error=1", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
def logout():
    res = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    res.delete_cookie("admin_token")
    return res

def verify_admin(admin_token: Optional[str] = Cookie(None)):
    if admin_token != "authenticated":
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return True

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db), admin: bool = Depends(verify_admin)):
    bids = db.query(models.Bid).all()
    total = sum(b.amount + (b.bonus_points or 0.0) for b in bids)
    settings = db.query(models.Settings).first()
    
    org_totals = {}
    if settings:
        if settings.org1: org_totals[settings.org1] = 0
        if settings.org2: org_totals[settings.org2] = 0
        if settings.org3: org_totals[settings.org3] = 0
        
    for b in bids:
        if b.organization:
            if b.organization not in org_totals:
                org_totals[b.organization] = 0
            org_totals[b.organization] += b.amount + (b.bonus_points or 0.0)

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "request": request, 
            "bids": bids, 
            "total": total,
            "min_bid": settings.min_bid if settings else 10.0,
            "settings": settings,
            "org_totals": org_totals
        }
    )

@app.post("/admin/settings")
def update_settings(
    min_bid: float = Form(...), 
    org1: Optional[str] = Form(""),
    org2: Optional[str] = Form(""),
    org3: Optional[str] = Form(""),
    deadline: Optional[str] = Form(""),
    feature_ticker: Optional[bool] = Form(False),
    feature_leaderboard: Optional[bool] = Form(False),
    feature_goal: Optional[bool] = Form(False),
    goal_amount: float = Form(1000.0),
    paypal_link: Optional[str] = Form("https://paypal.me/"),
    db: Session = Depends(get_db), 
    admin: bool = Depends(verify_admin)
):
    settings = db.query(models.Settings).first()
    if settings:
        settings.min_bid = min_bid
        settings.org1 = org1 or ""
        settings.org2 = org2 or ""
        settings.org3 = org3 or ""
        settings.deadline = deadline or ""
        settings.feature_ticker = feature_ticker
        settings.feature_leaderboard = feature_leaderboard
        settings.feature_goal = feature_goal
        settings.goal_amount = goal_amount
        settings.paypal_link = paypal_link or ""
        db.commit()
    return RedirectResponse(url="/admin?success=1", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/delete_bid/{bid_id}")
def delete_bid(bid_id: int, db: Session = Depends(get_db), admin: bool = Depends(verify_admin)):
    bid = db.query(models.Bid).filter(models.Bid.id == bid_id).first()
    if bid:
        db.delete(bid)
        db.commit()
    return RedirectResponse(url="/admin?success=deleted", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/adjust_points/{bid_id}")
def adjust_points(bid_id: int, bonus_points: float = Form(...), db: Session = Depends(get_db), admin: bool = Depends(verify_admin)):
    bid = db.query(models.Bid).filter(models.Bid.id == bid_id).first()
    if bid:
        bid.bonus_points = bonus_points
        db.commit()
    return RedirectResponse(url="/admin?success=points_adjusted", status_code=status.HTTP_303_SEE_OTHER)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
