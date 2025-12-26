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
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, MetaData, Table, select
from sqlalchemy.pool import QueuePool

# --- CONFIG ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST", "https://ton-app.onrender.com").rstrip('/')
SCOPES = ['read_products', 'write_products', 'read_themes', 'write_themes']
API_VERSION = "2024-10"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()
templates = Jinja2Templates(directory=".")

# --- DB SETUP ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./local_storage.db"

engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
metadata = MetaData()
shops_table = Table("shops", metadata, Column("domain", String, primary_key=True), Column("token", String))
metadata.create_all(engine)

# --- MIDDLEWARE SÉCURITÉ (LE FIX PAGE BLANCHE EST ICI) ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # Autorise l'affichage dans l'iframe Shopify
    response.headers["Content-Security-Policy"] = "frame-ancestors https://*.myshopify.com https://admin.shopify.com;"
    return response

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- HELPERS ---
def get_token_db(shop):
    try:
        with engine.connect() as conn:
            stmt = select(shops_table.c.token).where(shops_table.c.domain == shop)
            res = conn.execute(stmt).fetchone()
            return res[0] if res else None
    except: return None

def save_token_db(shop, token):
    try:
        with engine.connect() as conn:
            res = conn.execute(shops_table.update().where(shops_table.c.domain == shop).values(token=token))
            if res.rowcount == 0: conn.execute(shops_table.insert().values(domain=shop, token=token))
            conn.commit()
    except: pass

def activate_shop_session(shop):
    token = get_token_db(shop)
    if not token: return False
    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        return True
    except: return False

def get_metafield(ns, k, d=0):
    try: 
        m = shopify.Metafield.find(namespace=ns, key=k)
        if m: return m[0].value
    except: pass
    return d

def set_metafield(ns, k, v, t):
    try:
        m = shopify.Metafield()
        m.namespace = ns; m.key = k; m.value = v; m.type = t; m.save()
    except: pass

def clean_shop_url(url): return url.replace("https://", "").replace("http://", "").strip("/") if url else ""

# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", { "request": request, "shop": request.query_params.get("shop"), "api_key": SHOPIFY_API_KEY })

@app.get("/styles.css")
def styles(): return FileResponse('styles.css', media_type='text/css')
@app.get("/app.js")
def javascript(): return FileResponse('app.js', media_type='application/javascript')

@app.get("/login")
def login(shop: str):
    s = clean_shop_url(shop)
    return RedirectResponse(f"https://{s}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={','.join(SCOPES)}&redirect_uri={HOST}/auth/callback")

@app.get("/auth/callback")
def auth_callback(request: Request):
    p = dict(request.query_params)
    s = clean_shop_url(p.get("shop"))
    url = f"https://{s}/admin/oauth/access_token"
    try:
        r = requests.post(url, json={"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": p.get("code")})
        if r.status_code == 200:
            save_token_db(s, r.json().get('access_token'))
            return RedirectResponse(f"https://admin.shopify.com/store/{s.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
    except: pass
    return HTMLResponse("Auth Error")

# --- GENERATE (LOGIQUE ROBUSTE) ---
@app.post("/api/generate")
async def generate(
    shop: str = Form(...),
    person_image: UploadFile = File(...),
    clothing_url: Optional[str] = Form(None),
    clothing_file: Optional[UploadFile] = File(None)
):
    print(f"🔄 [1] REÇU: Demande pour {shop}")
    s = clean_shop_url(shop)
    
    if not activate_shop_session(s):
        print("❌ [Auth] Token manquant")
        return JSONResponse({"error": "Auth Failed"}, status_code=403)

    try:
        credits = int(float(get_metafield("virtual_try_on", "wallet", 0)))
        if credits < 1: 
            print("❌ [Credit] Solde insuffisant")
            return JSONResponse({"error": "No credits"}, status_code=402)
    except: return JSONResponse({"error": "DB Error"}, status_code=500)

    try:
        person_bytes = await person_image.read()
        person_file = io.BytesIO(person_bytes)
        garment_file = None
        
        if clothing_url and len(str(clothing_url)) > 5:
            c_url = str(clothing_url)
            if c_url.startswith("//"): c_url = "https:" + c_url
            print(f"📥 [Image] Téléchargement URL: {c_url}")
            resp = requests.get(c_url, timeout=10)
            if resp.status_code == 200: garment_file = io.BytesIO(resp.content)
            else: return JSONResponse({"error": "Impossible de lire l'image"}, status_code=400)
        elif clothing_file:
            print("📥 [Image] Vêtement uploadé")
            g_bytes = await clothing_file.read()
            garment_file = io.BytesIO(g_bytes)
        else: return JSONResponse({"error": "Aucun vêtement"}, status_code=400)

        print("🚀 [AI] Envoi Replicate...")
        output = replicate.run(MODEL_ID, input={"human_img": person_file, "garm_img": garment_file, "category": "upper_body"})
        
        if not output: return JSONResponse({"error": "L'IA a échoué (Image trop complexe ?)"}, status_code=500)
        
        result_url = str(output[0]) if isinstance(output, list) else str(output)
        print(f"✅ [AI] Succès: {result_url}")
        
        set_metafield("virtual_try_on", "wallet", credits - 1, "integer")
        return {"result_image_url": result_url}

    except Exception as e:
        print(f"❌ [CRASH] {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# --- BILLING ---
class BuyRequest(BaseModel): shop: str; pack_id: str; custom_amount: int = 0
@app.post("/api/buy-credits")
def buy(r: BuyRequest):
    s = clean_shop_url(r.shop)
    if not activate_shop_session(s): raise HTTPException(status_code=401)
    p, n, c = 0, "", 0
    if r.pack_id == 'pack_10': p, n, c = 4.99, "10 Credits", 10
    elif r.pack_id == 'pack_30': p, n, c = 12.99, "30 Credits", 30
    elif r.pack_id == 'pack_100': p, n, c = 29.99, "100 Credits", 100
    elif r.pack_id == 'pack_custom': c = r.custom_amount; p = round(c*0.25, 2); n = f"{c} Credits"
    try:
        ch = shopify.ApplicationCharge.create({"name": n, "price": p, "test": True, "return_url": f"{HOST}/billing/callback?shop={s}&amt={c}"})
        return {"confirmation_url": ch.confirmation_url}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/billing/callback")
def b_call(shop: str, amt: int, charge_id: str):
    s = clean_shop_url(shop)
    if not activate_shop_session(s): return RedirectResponse(f"/login?shop={s}")
    try:
        c = shopify.ApplicationCharge.find(charge_id)
        if c.status != 'active': c.activate()
        cur = int(float(get_metafield("virtual_try_on", "wallet", 0)))
        set_metafield("virtual_try_on", "wallet", cur + amt, "integer")
        return HTMLResponse(f"<script>window.top.location.href='https://admin.shopify.com/store/{s.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}';</script>")
    except: return HTMLResponse("Error")
@app.get("/api/get-data")
def g_data(shop: str):
    if activate_shop_session(clean_shop_url(shop)): return {"credits": int(float(get_metafield("virtual_try_on", "wallet", 0))), "usage": 0}
    return JSONResponse({"error": "Auth"}, status_code=401)
@app.post("/api/save-settings")
def s_set(r: Request): return {"ok": True}
@app.options("/api/generate")
async def opt_gen(): return JSONResponse({"ok":True}, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"})
