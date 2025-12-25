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

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
HOST = os.getenv("HOST", "").rstrip('/')
SCOPES = ['read_products', 'write_products', 'read_themes', 'write_themes']
API_VERSION = "2024-10"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()
templates = Jinja2Templates(directory=".")
RATE_LIMIT_DB: Dict[str, Dict] = {}

# --- 1. BASE DE DONNÉES (POUR LE TOKEN) ---
def init_db():
    conn = sqlite3.connect("database.db")
    conn.execute("CREATE TABLE IF NOT EXISTS shops (domain TEXT PRIMARY KEY, token TEXT)")
    conn.commit()
    conn.close()
init_db()

def save_token_db(shop, token):
    conn = sqlite3.connect("database.db")
    conn.execute("INSERT OR REPLACE INTO shops (domain, token) VALUES (?, ?)", (shop, token))
    conn.commit()
    conn.close()

def get_token_db(shop):
    try:
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        cur.execute("SELECT token FROM shops WHERE domain = ?", (shop,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except: return None

# --- 2. LOGIQUE SHOPIFY (METAFIELDS) ---
def get_shopify_session(shop, token):
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(shop, API_VERSION, token)
    shopify.ShopifyResource.activate_session(session)

def get_meta(namespace, key, default=0):
    try:
        m = shopify.Metafield.find(namespace=namespace, key=key)
        if m:
            val = m[0].value
            try: return int(float(val))
            except: return val
    except: pass
    return default

def set_meta(namespace, key, value, vtype="integer"):
    try:
        m = shopify.Metafield()
        m.namespace = namespace
        m.key = key
        m.value = value
        m.type = vtype
        m.save()
    except Exception as e: print(f"⚠️ Erreur Metafield: {e}")

# --- MIDDLEWARES ---
def clean_shop_url(url):
    return url.replace("https://", "").replace("http://", "").strip("/") if url else ""

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def add_csp_header(request: Request, call_next):
    response = await call_next(request)
    shop = request.query_params.get("shop", "")
    response.headers["Content-Security-Policy"] = f"frame-ancestors https://{shop} https://admin.shopify.com;"
    return response

# --- ROUTES D'AUTH ---
@app.get("/")
async def index(request: Request):
    shop = request.query_params.get("shop")
    return templates.TemplateResponse("index.html", {"request": request, "shop": shop, "api_key": SHOPIFY_API_KEY})

@app.get("/login")
def login(shop: str):
    shop = clean_shop_url(shop)
    auth_url = f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={','.join(SCOPES)}&redirect_uri={HOST}/auth/callback"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(shop: str, code: str):
    shop = clean_shop_url(shop)
    url = f"https://{shop}/admin/oauth/access_token"
    res = requests.post(url, json={"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code})
    token = res.json().get('access_token')
    save_token_db(shop, token) # Sauvegarde CRUCIALE pour le widget
    return RedirectResponse(f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")

# --- ROUTES API (DATA) ---
@app.get("/api/get-data")
def get_data(shop: str):
    shop = clean_shop_url(shop)
    token = get_token_db(shop)
    if not token: raise HTTPException(status_code=401)
    get_shopify_session(shop, token)
    return {
        "credits": get_meta("virtual_try_on", "wallet"),
        "usage": get_meta("virtual_try_on", "total_tryons"),
        "atc": get_meta("virtual_try_on", "total_atc"),
        "lifetime": get_meta("virtual_try_on", "lifetime_credits"),
        "widget": {
            "text": get_meta("vton_widget", "btn_text", "Try It On Now ✨"),
            "bg": get_meta("vton_widget", "btn_bg", "#000000"),
            "color": get_meta("vton_widget", "btn_text_color", "#ffffff")
        },
        "security": {"max_tries": get_meta("vton_security", "max_tries", 5)}
    }

@app.post("/api/save-settings")
async def save_settings(request: Request):
    data = await request.json()
    shop = clean_shop_url(data.get("shop"))
    token = get_token_db(shop)
    if token:
        get_shopify_session(shop, token)
        set_meta("vton_widget", "btn_text", data.get("text"), "single_line_text_field")
        set_meta("vton_widget", "btn_bg", data.get("bg"), "color")
        set_meta("vton_widget", "btn_text_color", data.get("color"), "color")
        set_meta("vton_security", "max_tries", data.get("max_tries"), "integer")
    return {"ok": True}

@app.post("/api/track-atc")
async def track_atc(request: Request):
    data = await request.json()
    shop = clean_shop_url(data.get("shop"))
    token = get_token_db(shop)
    if token:
        get_shopify_session(shop, token)
        set_meta("virtual_try_on", "total_atc", get_meta("virtual_try_on", "total_atc") + 1)
    return {"ok": True}

# --- GÉNÉRATION IA (Widget & Admin) ---
@app.post("/api/generate")
async def generate(
    request: Request,
    shop: str = Form(...),
    person_image: UploadFile = File(...),
    clothing_url: Optional[str] = Form(None)
):
    shop_domain = clean_shop_url(shop)
    token = get_token_db(shop_domain)
    if not token: return JSONResponse({"error": "Admin must login once"}, status_code=401)

    try:
        get_shopify_session(shop_domain, token)
        credits = get_meta("virtual_try_on", "wallet")
        if credits < 1: return JSONResponse({"error": "No credits"}, status_code=402)

        # Check Limite IP
        client_ip = request.client.host
        user_stats = RATE_LIMIT_DB.get(client_ip, {"count": 0, "reset": time.time()})
        if time.time() - user_stats["reset"] > 86400: user_stats = {"count": 0, "reset": time.time()}
        if user_stats["count"] >= get_meta("vton_security", "max_tries", 5):
            return JSONResponse({"error": "Daily limit reached"}, status_code=429)

        # IA Replicate
        p_content = await person_image.read()
        output = replicate.run(MODEL_ID, input={
            "human_img": io.BytesIO(p_content),
            "garm_img": clothing_url,
            "category": "upper_body"
        })
        
        # Updates
        set_meta("virtual_try_on", "wallet", credits - 1)
        set_meta("virtual_try_on", "total_tryons", get_meta("virtual_try_on", "total_tryons") + 1)
        user_stats["count"] += 1
        RATE_LIMIT_DB[client_ip] = user_stats

        res_url = str(output[0]) if isinstance(output, list) else str(output)
        return {"result_image_url": res_url}
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/styles.css")
def styles(): return FileResponse('styles.css')
@app.get("/app.js")
def javascript(): return FileResponse('app.js')
