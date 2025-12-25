import os
import hmac
import hashlib
import shopify
import requests
import replicate
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# --- BASE DE DONNÉES (SQLAlchemy) ---
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 
SCOPES = ['read_products', 'write_products', 'read_themes', 'write_themes']
API_VERSION = "2024-01"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

# Configuration DB
DATABASE_URL = os.getenv("DATABASE_URL")
# Fallback pour le local (si pas de DB configurée, crée un fichier local)
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./local_shops.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Modèle de la table Shops
class ShopSession(Base):
    __tablename__ = "shops"
    shop_url = Column(String, primary_key=True, index=True)
    access_token = Column(String)
    credits = Column(Integer, default=10) # On stocke aussi les crédits ici pour être sûr !

# Création des tables
Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory=".")

# --- FONCTIONS DB ---
def get_shop_session(shop_url):
    db = SessionLocal()
    try:
        return db.query(ShopSession).filter(ShopSession.shop_url == shop_url).first()
    finally:
        db.close()

def save_shop_session(shop_url, token):
    db = SessionLocal()
    try:
        shop = db.query(ShopSession).filter(ShopSession.shop_url == shop_url).first()
        if shop:
            shop.access_token = token
        else:
            shop = ShopSession(shop_url=shop_url, access_token=token, credits=10)
            db.add(shop)
        db.commit()
    finally:
        db.close()

def update_credits(shop_url, amount):
    db = SessionLocal()
    try:
        shop = db.query(ShopSession).filter(ShopSession.shop_url == shop_url).first()
        if shop:
            shop.credits = amount
            db.commit()
    finally:
        db.close()

# --- MIDDLEWARE SÉCURITÉ ---
@app.middleware("http")
async def add_csp_header(request: Request, call_next):
    response = await call_next(request)
    shop = request.query_params.get("shop", "")
    policy = f"frame-ancestors https://{shop} https://admin.shopify.com;"
    if shop:
        response.headers["Content-Security-Policy"] = policy
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- UTILS ---
def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

def verify_shopify_hmac(query_dict: dict) -> bool:
    if "hmac" not in query_dict: return False
    hmac_received = query_dict["hmac"]
    data = {k: v for k, v in query_dict.items() if k != "hmac"}
    msg = "&".join([f"{key}={value}" for key, value in sorted(data.items())])
    digest = hmac.new(SHOPIFY_API_SECRET.encode('utf-8'), msg.encode('utf-8'), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, hmac_received)

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    shop = request.query_params.get("shop")
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "shop": shop, 
        "api_key": SHOPIFY_API_KEY 
    })

@app.get("/styles.css")
def styles(): return FileResponse('styles.css', media_type='text/css')

@app.get("/app.js")
def javascript(): return FileResponse('app.js', media_type='application/javascript')

@app.get("/login")
def login(shop: str):
    shop = clean_shop_url(shop)
    auth_url = f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={','.join(SCOPES)}&redirect_uri={HOST}/auth/callback"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(request: Request):
    params = dict(request.query_params)
    shop = clean_shop_url(params.get("shop"))
    code = params.get("code")
    host = params.get("host")

    try:
        url = f"https://{shop}/admin/oauth/access_token"
        payload = {"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code}
        res = requests.post(url, json=payload)
        
        if res.status_code == 200:
            token = res.json().get('access_token')
            
            # SAUVEGARDE EN BASE DE DONNÉES (Durable !)
            save_shop_session(shop, token)
            
            target_url = f"https://admin.shopify.com/store/{shop.replace('.myshopify.com', '')}/apps/{SHOPIFY_API_KEY}"
            if host: target_url += f"?host={host}"
            return RedirectResponse(target_url)
        
        return HTMLResponse(f"Token Error: {res.text}", status_code=400)
    except Exception as e:
        return HTMLResponse(content=f"Auth Error: {str(e)}", status_code=500)

# --- HELPERS API SHOPIFY ---
def get_shopify_session(shop, token):
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(shop, API_VERSION, token)
    shopify.ShopifyResource.activate_session(session)

# --- API ENDPOINTS ---

@app.get("/api/get-credits")
def get_credits_route(shop: str):
    shop = clean_shop_url(shop)
    
    # Lecture depuis la DB
    session_data = get_shop_session(shop)
    if not session_data or not session_data.access_token:
        raise HTTPException(status_code=401, detail="Session expired")
    
    # On peut récupérer les crédits directement depuis notre DB (plus rapide et fiable)
    # Ou depuis Shopify Metafields. Ici on utilise notre DB pour éviter les erreurs Metafield
    return {"credits": session_data.credits}

class BuyRequest(BaseModel):
    shop: str
    pack_id: str
    custom_amount: int = 0

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    shop = clean_shop_url(req.shop)
    session_data = get_shop_session(shop)
    
    if not session_data: raise HTTPException(status_code=401, detail="Session expired")
    token = session_data.access_token

    price, name, credits = 0, "", 0
    if req.pack_id == 'pack_10': price, name, credits = 4.99, "10 Credits", 10
    elif req.pack_id == 'pack_30': price, name, credits = 12.99, "30 Credits", 30
    elif req.pack_id == 'pack_100': price, name, credits = 29.99, "100 Credits", 100
    elif req.pack_id == 'pack_custom':
        credits = req.custom_amount
        if credits < 200: return JSONResponse({"error": "Min 200 credits"}, status_code=400)
        price = round(credits * 0.25, 2)
        name = f"{credits} Credits (Custom)"
    else: return JSONResponse({"error": "Invalid Pack"}, status_code=400)

    try:
        get_shopify_session(shop, token)
        return_url = f"{HOST}/billing/callback?shop={shop}&amt={credits}"
        charge = shopify.ApplicationCharge.create({
            "name": name, "price": price, "test": True, "return_url": return_url
        })
        return {"confirmation_url": charge.confirmation_url}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/billing/callback")
def billing_callback(shop: str, amt: int, charge_id: str):
    shop = clean_shop_url(shop)
    session_data = get_shop_session(shop)
    if not session_data: return RedirectResponse(f"/login?shop={shop}")
    token = session_data.access_token

    try:
        get_shopify_session(shop, token)
        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status != 'active': charge.activate()

        # Mise à jour Crédits dans NOTRE DB
        new_total = session_data.credits + amt
        update_credits(shop, new_total)

        # (Optionnel) Sync avec Shopify Metafields si tu veux
        # ...

        admin_url = f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}"
        return HTMLResponse(f"<script>window.top.location.href='{admin_url}';</script>")
    except Exception as e:
        return HTMLResponse(f"Billing Error: {e}")

@app.post("/api/generate")
async def generate(
    request: Request,
    shop: str = Form(...),
    person_image: UploadFile = File(...),
    clothing_file: Optional[UploadFile] = File(None),
    clothing_url: Optional[str] = Form(None),
    category: str = Form("upper_body")
):
    shop = clean_shop_url(shop)
    session_data = get_shop_session(shop)
    
    if not session_data: raise HTTPException(status_code=401, detail="Session expired")

    if session_data.credits < 1:
        return JSONResponse({"error": "Not enough credits."}, status_code=402)

    try:
        person_bytes = await person_image.read()
        garment_input = None
        if clothing_file:
            garment_input = await clothing_file.read()
        elif clothing_url:
            garment_input = clothing_url
            if garment_input.startswith("//"): garment_input = "https:" + garment_input
        else:
            return JSONResponse({"error": "No garment provided"}, status_code=400)

        output = replicate.run(MODEL_ID, input={
            "human_img": person_bytes, "garm_img": garment_input,
            "garment_des": category, "category": "upper_body"
        })

        # Débit Crédit en DB
        new_total = session_data.credits - 1
        update_credits(shop, new_total)

        result_url = str(output[0]) if isinstance(output, list) else str(output)
        return {"result_image_url": result_url, "new_credits": new_total}

    except Exception as e:
        print(f"❌ AI Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# --- WEBHOOKS ---
@app.post("/webhooks/customers/data_request")
def w1(): return {"ok": True}
@app.post("/webhooks/customers/redact")
def w2(): return {"ok": True}
@app.post("/webhooks/shop/redact")
def w3(): return {"ok": True}
