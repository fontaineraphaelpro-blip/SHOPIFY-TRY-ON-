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
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN") 
HOST = os.getenv("HOST", "https://ton-app.onrender.com").rstrip('/')
SCOPES = ['read_products', 'write_products', 'read_themes', 'write_themes']
API_VERSION = "2024-10"
MODEL_ID = "cuuupid/idm-vton:c871bb9b0466074280c2aec71dc6746146c6374507d3b0704332973e44075193"

app = FastAPI()
templates = Jinja2Templates(directory=".")
RATE_LIMIT_DB: Dict[str, Dict] = {} 

# --- 1. BASE DE DONNEES ---
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

# --- 2. SHOPIFY UTILS ---
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
            return val
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
    except Exception as e: print(f"⚠️ Metafield Error: {e}")

def clean_shop_url(url):
    return url.replace("https://", "").replace("http://", "").strip("/") if url else ""

# --- MIDDLEWARE ---
@app.middleware("http")
async def add_csp_header(request: Request, call_next):
    response = await call_next(request)
    shop = request.query_params.get("shop", "")
    if shop:
        response.headers["Content-Security-Policy"] = f"frame-ancestors https://{shop} https://admin.shopify.com;"
    return response

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- ROUTES DASHBOARD / INSTALL ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    shop = request.query_params.get("shop")
    return templates.TemplateResponse("index.html", { "request": request, "shop": shop, "api_key": SHOPIFY_API_KEY })

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

# --- API DONNEES & BILLING ---
@app.get("/api/get-data")
def get_data_route(shop: str):
    shop = clean_shop_url(shop)
    token = get_token_db(shop)
    if not token: raise HTTPException(status_code=401, detail="Refresh required")
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
    except Exception as e: return {"credits": 0}

@app.post("/api/save-settings")
def save_settings(req: dict):
    # Simplifié pour l'exemple (utiliser pydantic en prod)
    shop = clean_shop_url(req.get('shop'))
    token = get_token_db(shop)
    if not token: return JSONResponse({"error": "No token"}, status_code=401)
    get_shopify_session(shop, token)
    set_metafield("vton_widget", "btn_text", req.get('text'), "single_line_text_field")
    set_metafield("vton_widget", "btn_bg", req.get('bg'), "color")
    set_metafield("vton_widget", "btn_text_color", req.get('color'), "color")
    set_metafield("vton_security", "max_tries_per_user", int(req.get('max_tries')), "integer")
    return {"ok": True}

# --- GENERATION (CRITIQUE : URL SUPPORT) ---
@app.post("/api/generate")
async def generate(
    request: Request,
    shop: str = Form(...),
    person_image: UploadFile = File(...),
    clothing_file: Optional[UploadFile] = File(None),
    clothing_url: Optional[str] = Form(None),
    category: str = Form("upper_body")
):
    print(f"📥 GEN REQUEST: Shop={shop}")
    
    # 1. Check Shop & Token
    shop = clean_shop_url(shop)
    token = get_token_db(shop)
    if not token:
        return JSONResponse({"error": "Shop verification failed"}, status_code=403)

    try:
        get_shopify_session(shop, token)
        
        # 2. Check Credits
        credits = get_metafield("virtual_try_on", "wallet", 0)
        if credits < 1:
            return JSONResponse({"error": "Store has no credits left."}, status_code=402)

        # 3. Rate Limit (IP)
        client_ip = request.client.host
        max_tries = int(get_metafield("vton_security", "max_tries_per_user", 5))
        user_stats = RATE_LIMIT_DB.get(client_ip, {"count": 0, "reset": time.time()})
        if time.time() - user_stats["reset"] > 86400: user_stats = {"count": 0, "reset": time.time()}
        if user_stats["count"] >= max_tries:
            return JSONResponse({"error": "Daily limit reached for this user."}, status_code=429)

        # 4. Prepare Inputs for Replicate
        # Person image is bytes
        person_bytes = await person_image.read()
        person_file = io.BytesIO(person_bytes)

        # Clothing: URL (Priority) OR File
        garment_input = None
        
        if clothing_url and len(clothing_url) > 5:
            # Replicate accepts URL directly
            garment_input = clothing_url.strip()
            if garment_input.startswith("//"): 
                garment_input = "https:" + garment_input
            print(f"👕 Clothing via URL: {garment_input}")
            
        elif clothing_file:
            g_bytes = await clothing_file.read()
            garment_input = io.BytesIO(g_bytes)
            print("👕 Clothing via File Upload")
        else:
            return JSONResponse({"error": "No clothing provided"}, status_code=400)

        # 5. Call Replicate
        print("🚀 Sending to Replicate...")
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": person_file,
                "garm_img": garment_input,
                "garment_des": category,
                "category": "upper_body",
                "crop": False,
                "seed": 42
            }
        )
        print(f"✅ Success: {output}")
        result_url = str(output[0]) if isinstance(output, list) else str(output)

        # 6. Deduct Credits & Update Stats
        set_metafield("virtual_try_on", "wallet", credits - 1, "integer")
        total = get_metafield("virtual_try_on", "total_tryons", 0)
        set_metafield("virtual_try_on", "total_tryons", total + 1, "integer")
        
        user_stats["count"] += 1
        RATE_LIMIT_DB[client_ip] = user_stats

        return {"result_image_url": result_url}

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)
