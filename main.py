import os
import io
import time
import shopify
import requests
import replicate
from typing import Optional, Dict
from fastapi import FastAPI, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
# --- IMPORT CRUCIAL AJOUTÉ ---
from pydantic import BaseModel
# -----------------------------
from sqlalchemy import create_engine, Column, String, MetaData, Table, select
from sqlalchemy.pool import QueuePool

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST", "https://ton-app.onrender.com").rstrip('/')
SCOPES = ['read_products', 'write_products', 'read_themes', 'write_themes']
API_VERSION = "2024-10"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()
templates = Jinja2Templates(directory=".")
RATE_LIMIT_DB: Dict[str, Dict] = {} 

# --- BASE DE DONNÉES (POSTGRESQL) ---
DATABASE_URL = os.getenv("DATABASE_URL")

# Fix pour Render (postgres:// -> postgresql://)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Fallback SQLite (Dev local)
if not DATABASE_URL:
    print("⚠️  DEV: Utilisation SQLite (Données volatiles)")
    DATABASE_URL = "sqlite:///./local_storage.db"
else:
    print("✅  PROD: PostgreSQL connecté")

# Moteur DB
engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
metadata = MetaData()

# Table 'shops'
shops_table = Table(
    "shops", metadata,
    Column("domain", String, primary_key=True),
    Column("token", String)
)

# Création des tables
metadata.create_all(engine)

def save_token_db(shop, token):
    try:
        with engine.connect() as conn:
            result = conn.execute(shops_table.update().where(shops_table.c.domain == shop).values(token=token))
            if result.rowcount == 0:
                conn.execute(shops_table.insert().values(domain=shop, token=token))
            conn.commit()
            print(f"💾 Token sauvegardé pour: {shop}")
    except Exception as e: print(f"❌ Erreur DB Save: {e}")

def get_token_db(shop):
    try:
        with engine.connect() as conn:
            stmt = select(shops_table.c.token).where(shops_table.c.domain == shop)
            result = conn.execute(stmt).fetchone()
            return result[0] if result else None
    except Exception as e: 
        print(f"❌ Erreur DB Get: {e}")
        return None

# --- MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- HELPERS ---
def activate_shop_session(shop):
    token = get_token_db(shop)
    if not token: return False
    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        return True
    except: return False

def get_metafield(namespace, key, default=0):
    try:
        metafields = shopify.Metafield.find(namespace=namespace, key=key)
        if metafields: return metafields[0].value
    except: pass
    return default

def set_metafield(namespace, key, value, type_val):
    try:
        metafield = shopify.Metafield()
        metafield.namespace = namespace
        metafield.key = key
        metafield.value = value
        metafield.type = type_val
        metafield.save()
    except Exception as e: print(f"Metafield Error: {e}")

def clean_shop_url(url):
    return url.replace("https://", "").replace("http://", "").strip("/") if url else ""

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    shop = request.query_params.get("shop")
    return templates.TemplateResponse("index.html", { "request": request, "shop": shop, "api_key": SHOPIFY_API_KEY })

@app.get("/styles.css")
def styles(): return FileResponse('styles.css', media_type='text/css')
@app.get("/app.js")
def javascript(): return FileResponse('app.js', media_type='application/javascript')

# --- AUTH ---
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
    url = f"https://{shop}/admin/oauth/access_token"
    payload = {"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code}
    
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            token = res.json().get('access_token')
            save_token_db(shop, token) # SAUVEGARDE EN DB
            return RedirectResponse(f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
        return HTMLResponse(f"Erreur Token: {res.text}", status_code=400)
    except Exception as e: return HTMLResponse(f"Crash: {str(e)}", status_code=500)

# --- API ---
@app.options("/api/generate")
async def options_generate():
    return JSONResponse(content={"ok":True}, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"})

@app.post("/api/generate")
async def generate(
    shop: str = Form(...),
    person_image: UploadFile = File(...),
    clothing_url: Optional[str] = Form(None),
    clothing_file: Optional[UploadFile] = File(None)
):
    shop = clean_shop_url(shop)
    if not activate_shop_session(shop):
        return JSONResponse({"error": "Shop non autorisé/installé."}, status_code=403)

    try:
        credits = int(float(get_metafield("virtual_try_on", "wallet", 0)))
        if credits < 1: return JSONResponse({"error": "Plus de crédits"}, status_code=402)
    except: return JSONResponse({"error": "Erreur crédits"}, status_code=500)

    try:
        person_bytes = await person_image.read()
        person_file = io.BytesIO(person_bytes)
        garment_input = None
        
        if clothing_url:
            garment_input = str(clothing_url)
            if garment_input.startswith("//"): garment_input = "https:" + garment_input
        elif clothing_file:
            garment_bytes = await clothing_file.read()
            garment_input = io.BytesIO(garment_bytes)
        
        output = replicate.run(MODEL_ID, input={"human_img": person_file, "garm_img": garment_input, "category": "upper_body"})
        result_url = str(output[0]) if isinstance(output, list) else str(output)
        
        set_metafield("virtual_try_on", "wallet", credits - 1, "integer")
        return {"result_image_url": result_url}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/get-data")
def get_data(shop: str):
    if activate_shop_session(clean_shop_url(shop)):
        w = get_metafield("virtual_try_on", "wallet", 0)
        u = get_metafield("virtual_try_on", "total_tryons", 0)
        return {"credits": int(float(w)), "usage": int(float(u))}
    return JSONResponse({"error": "Auth Failed"}, status_code=401)

# --- BILLING ---
class BuyRequest(BaseModel): shop: str; pack_id: str; custom_amount: int = 0

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    shop = clean_shop_url(req.shop)
    if not activate_shop_session(shop): raise HTTPException(status_code=401)
    
    price, name, credits = 0, "", 0
    if req.pack_id == 'pack_10': price, name, credits = 4.99, "10 Credits", 10
    elif req.pack_id == 'pack_30': price, name, credits = 12.99, "30 Credits", 30
    elif req.pack_id == 'pack_100': price, name, credits = 29.99, "100 Credits", 100
    elif req.pack_id == 'pack_custom':
        credits = req.custom_amount
        price, name = round(credits * 0.25, 2), f"{credits} Credits"

    try:
        charge = shopify.ApplicationCharge.create({
            "name": name, 
            "price": price, 
            "test": True, 
            "return_url": f"{HOST}/billing/callback?shop={shop}&amt={credits}"
        })
        return {"confirmation_url": charge.confirmation_url}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/billing/callback")
def billing_callback(shop: str, amt: int, charge_id: str):
    shop = clean_shop_url(shop)
    if not activate_shop_session(shop): return RedirectResponse(f"/login?shop={shop}")
    try:
        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status != 'active': charge.activate()
        current = int(float(get_metafield("virtual_try_on", "wallet", 0)))
        set_metafield("virtual_try_on", "wallet", current + amt, "integer")
        return HTMLResponse(f"<script>window.top.location.href='https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}';</script>")
    except: return HTMLResponse("Billing Error")
