import os
import io
import time
import sqlite3
import shopify
import requests
import replicate
from typing import Optional, Dict
from fastapi import FastAPI, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# --- CONFIG ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
REPLICATE_TOKEN_CHECK = os.getenv("REPLICATE_API_TOKEN")
HOST = os.getenv("HOST", "https://stylelab-vtonn.onrender.com").rstrip('/')
SCOPES = ['read_products', 'write_products', 'read_themes', 'write_themes']
API_VERSION = "2024-10"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()
templates = Jinja2Templates(directory=".")
RATE_LIMIT_DB: Dict[str, Dict] = {}

# --- CORS MIDDLEWARE (PRIORITAIRE) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, spécifier les domaines Shopify
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# --- 1. COFFRE-FORT LOCAL (SQLite) ---
def init_db():
    with sqlite3.connect("database.db") as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS shops (domain TEXT PRIMARY KEY, token TEXT)")
        conn.commit()
init_db()

def save_token_db(shop, token):
    with sqlite3.connect("database.db") as conn:
        conn.execute("INSERT OR REPLACE INTO shops (domain, token) VALUES (?, ?)", (shop, token))
        conn.commit()

def get_token_db(shop):
    try:
        with sqlite3.connect("database.db") as conn:
            cur = conn.cursor()
            cur.execute("SELECT token FROM shops WHERE domain = ?", (shop,))
            row = cur.fetchone()
            return row[0] if row else None
    except:
        return None

# --- 2. SHOPIFY ---
def get_shopify_session(shop, token):
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(shop, API_VERSION, token)
    shopify.ShopifyResource.activate_session(session)

def get_metafield(namespace, key, default=0):
    try:
        metafields = shopify.Metafield.find(namespace=namespace, key=key)
        if metafields:
            val = metafields[0].value
            if isinstance(default, int): return int(float(val))
            if isinstance(default, str): return str(val)
            return val
    except: 
        pass
    return default

def set_metafield(namespace, key, value, type_val):
    try:
        metafield = shopify.Metafield()
        metafield.namespace = namespace
        metafield.key = key
        metafield.value = value
        metafield.type = type_val
        metafield.save()
    except Exception as e: 
        print(f"⚠️ Erreur Metafield: {e}")

def clean_shop_url(url):
    return url.replace("https://", "").replace("http://", "").strip("/") if url else ""

# --- MIDDLEWARE CSP ---
@app.middleware("http")
async def csp_middleware(request: Request, call_next):
    print(f"🔥 [{request.method}] {request.url.path}")
    print(f"   Origin: {request.headers.get('origin', 'N/A')}")
    
    response = await call_next(request)
    
    # CSP pour permettre l'embedding Shopify
    shop = request.query_params.get("shop", "")
    if shop:
        response.headers["Content-Security-Policy"] = f"frame-ancestors https://{shop} https://admin.shopify.com https://*.myshopify.com;"
    else:
        response.headers["Content-Security-Policy"] = "frame-ancestors https://*.myshopify.com https://admin.shopify.com;"
    
    return response

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
    try:
        url = f"https://{shop}/admin/oauth/access_token"
        payload = {"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code}
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            token = res.json().get('access_token')
            save_token_db(shop, token)
            target_url = f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}"
            return RedirectResponse(target_url)
        return HTMLResponse(f"Token Error: {res.text}", status_code=400)
    except Exception as e: return HTMLResponse(content=f"Auth Error: {str(e)}", status_code=500)

# --- API DATA ---
@app.get("/api/get-data")
def get_data_route(shop: str):
    shop = clean_shop_url(shop)
    token = get_token_db(shop)
    if not token: 
        raise HTTPException(status_code=401, detail="Refresh required")
    try:
        get_shopify_session(shop, token)
        credits = get_metafield("virtual_try_on", "wallet", 0)
        total_tryons = get_metafield("virtual_try_on", "total_tryons", 0)
        total_atc = get_metafield("virtual_try_on", "total_atc", 0)
        lifetime = get_metafield("virtual_try_on", "lifetime_credits", 0)

        w_text = get_metafield("vton_widget", "btn_text", "Try It On Now ✨")
        w_bg = get_metafield("vton_widget", "btn_bg", "#000000")
        w_color = get_metafield("vton_widget", "btn_text_color", "#ffffff")
        max_tries = get_metafield("vton_security", "max_tries_per_user", 5)

        return {
            "credits": credits, "lifetime": lifetime, "usage": total_tryons, "atc": total_atc,
            "widget": {"text": w_text, "bg": w_bg, "color": w_color}, "security": {"max_tries": max_tries}
        }
    except Exception as e: 
        print(f"⚠️ API Get-Data Error: {e}")
        return {"credits": 0}

# --- TRACK ATC ---
class TrackRequest(BaseModel): shop: str
@app.post("/api/track-atc")
def track_atc(req: TrackRequest):
    shop = clean_shop_url(req.shop)
    token = get_token_db(shop)
    if not token: return JSONResponse({"error": "No token"}, status_code=401)
    try:
        get_shopify_session(shop, token)
        current_atc = get_metafield("virtual_try_on", "total_atc", 0)
        set_metafield("virtual_try_on", "total_atc", current_atc + 1, "integer")
        return {"ok": True}
    except Exception as e: 
        print(f"⚠️ ATC Error: {e}")
        return JSONResponse({"error": "Failed"}, status_code=500)

# --- SETTINGS ---
class SettingsRequest(BaseModel): shop: str; text: str; bg: str; color: str; max_tries: int
@app.post("/api/save-settings")
def save_settings(req: SettingsRequest):
    shop = clean_shop_url(req.shop)
    token = get_token_db(shop)
    if not token: return JSONResponse({"error": "No token"}, status_code=401)
    try:
        get_shopify_session(shop, token)
        set_metafield("vton_widget", "btn_text", req.text, "single_line_text_field")
        set_metafield("vton_widget", "btn_bg", req.bg, "color")
        set_metafield("vton_widget", "btn_text_color", req.color, "color")
        set_metafield("vton_security", "max_tries_per_user", req.max_tries, "integer")
        return {"ok": True}
    except Exception as e:
        print(f"⚠️ Save Settings Error: {e}")
        return JSONResponse({"error": "Failed"}, status_code=500)

# --- BILLING ---
class BuyRequest(BaseModel): shop: str; pack_id: str; custom_amount: int = 0
@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    shop = clean_shop_url(req.shop)
    token = get_token_db(shop)
    if not token: raise HTTPException(status_code=401, detail="Session expired")

    price, name, credits = 0, "", 0
    if req.pack_id == 'pack_10': price, name, credits = 4.99, "10 Credits", 10
    elif req.pack_id == 'pack_30': price, name, credits = 12.99, "30 Credits", 30
    elif req.pack_id == 'pack_100': price, name, credits = 29.99, "100 Credits", 100
    elif req.pack_id == 'pack_custom':
        credits = req.custom_amount
        price, name = round(credits * 0.25, 2), f"{credits} Credits"

    try:
        get_shopify_session(shop, token)
        return_url = f"{HOST}/billing/callback?shop={shop}&amt={credits}"
        charge = shopify.ApplicationCharge.create({"name": name, "price": price, "test": True, "return_url": return_url})
        return {"confirmation_url": charge.confirmation_url}
    except Exception as e: 
        print(f"⚠️ Billing Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/billing/callback")
def billing_callback(shop: str, amt: int, charge_id: str):
    shop = clean_shop_url(shop)
    token = get_token_db(shop)
    if not token: return RedirectResponse(f"/login?shop={shop}")
    try:
        get_shopify_session(shop, token)
        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status != 'active': charge.activate()
        current = get_metafield("virtual_try_on", "wallet", 0)
        set_metafield("virtual_try_on", "wallet", current + amt, "integer")
        lifetime = get_metafield("virtual_try_on", "lifetime_credits", 0)
        set_metafield("virtual_try_on", "lifetime_credits", lifetime + amt, "integer")
        admin_url = f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}"
        return HTMLResponse(f"<script>window.top.location.href='{admin_url}';</script>")
    except: 
        return HTMLResponse("Billing Error")

# --- ROUTE GENERATE (CRITIQUE) ---
@app.options("/api/generate")
async def generate_options():
    """Preflight CORS"""
    return JSONResponse({"ok": True})

@app.post("/api/generate")
async def generate(
    request: Request,
    shop: str = Form(...),
    person_image: UploadFile = File(...),
    clothing_file: Optional[UploadFile] = File(None),
    clothing_url: Optional[str] = Form(None),
    category: str = Form("upper_body")
):
    """Route unifiée pour admin ET clients"""
    print(f"🚀 [GENERATE] Requête reçue")
    print(f"   - Shop: {shop}")
    print(f"   - Client IP: {request.client.host}")
    print(f"   - Origin: {request.headers.get('origin', 'N/A')}")
    
    shop = clean_shop_url(shop)
    
    if not shop:
        print("❌ [ERROR] Shop manquant")
        return JSONResponse({"error": "Shop parameter missing"}, status_code=400)
    
    # 1. Vérification Token
    token = get_token_db(shop)
    if not token:
        print(f"❌ [ERROR] Pas de token pour {shop}")
        return JSONResponse({"error": "Shop not authenticated"}, status_code=401)
    
    try:
        # 2. Vérification Crédits
        get_shopify_session(shop, token)
        current_credits = get_metafield("virtual_try_on", "wallet", 0)
        max_tries = get_metafield("vton_security", "max_tries_per_user", 5)
        
        print(f"💰 Crédits: {current_credits}")
        
        if current_credits < 1:
            return JSONResponse({"error": "Insufficient credits"}, status_code=402)
        
        # 3. Rate Limiting
        client_ip = request.client.host
        rate_key = f"{shop}_{client_ip}"
        today = time.strftime("%Y-%m-%d")
        
        if rate_key not in RATE_LIMIT_DB:
            RATE_LIMIT_DB[rate_key] = {"date": today, "count": 0}
        
        if RATE_LIMIT_DB[rate_key]["date"] != today:
            RATE_LIMIT_DB[rate_key] = {"date": today, "count": 0}
        
        if RATE_LIMIT_DB[rate_key]["count"] >= max_tries:
            print(f"⚠️ [RATE LIMIT] IP {client_ip}")
            return JSONResponse({"error": "Daily limit reached"}, status_code=429)
        
        # 4. Traitement Images
        print("📸 Lecture images...")
        person_bytes = await person_image.read()
        person_file = io.BytesIO(person_bytes)
        
        garment_input = None
        if clothing_file:
            garment_bytes = await clothing_file.read()
            garment_input = io.BytesIO(garment_bytes)
            print("👕 Fichier vêtement chargé")
        elif clothing_url:
            garment_input = clothing_url
            if garment_input.startswith("//"):
                garment_input = "https:" + garment_input
            print(f"🔗 URL vêtement: {garment_input}")
        else:
            return JSONResponse({"error": "No garment provided"}, status_code=400)
        
        print("🤖 Appel Replicate...")
        
        # 5. Appel Replicate
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": person_file,
                "garm_img": garment_input,
                "garment_des": category,
                "category": "upper_body"
            }
        )
        
        result_url = str(output[0]) if isinstance(output, list) else str(output)
        
        print(f"✅ Résultat: {result_url}")
        
        # 6. Mise à jour Stats
        set_metafield("virtual_try_on", "wallet", current_credits - 1, "integer")
        total_tryons = get_metafield("virtual_try_on", "total_tryons", 0)
        set_metafield("virtual_try_on", "total_tryons", total_tryons + 1, "integer")
        
        RATE_LIMIT_DB[rate_key]["count"] += 1
        
        print(f"📊 Crédits restants: {current_credits - 1}")
        
        return JSONResponse({"result_image_url": result_url})
        
    except Exception as e:
        print(f"🔥 [ERROR]: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

# --- WEBHOOKS GDPR ---
@app.post("/webhooks/customers/data_request")
def w1(): return {"ok": True}
@app.post("/webhooks/customers/redact")
def w2(): return {"ok": True}
@app.post("/webhooks/shop/redact")
def w3(): return {"ok": True}
@app.post("/webhooks/gdpr")
def w4(): return {"ok": True}
