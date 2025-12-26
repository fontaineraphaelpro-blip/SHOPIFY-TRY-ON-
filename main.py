import os
import io
import time
import sqlite3
import shopify
import replicate
from typing import Optional, Dict
from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN") 
HOST = os.getenv("HOST", "https://ton-app.onrender.com").rstrip('/')
SCOPES = ['read_products', 'write_products', 'read_themes', 'write_themes']
API_VERSION = "2024-10"

# LE BON MODÈLE (Celui qui marche)
MODEL_ID = "cuuupid/idm-vton:906425dbca90663f8c950892a2b9617e76527b3f9d3f5ce6bb2c29664b7856d9"

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=".")

# --- MIDDLEWARE SÉCURITÉ CRITIQUE (Pour l'Iframe) ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # On autorise l'affichage en iframe partout pour éviter les blocages
    response.headers["Content-Security-Policy"] = "frame-ancestors *;"
    response.headers["X-Frame-Options"] = "ALLOWALL"
    return response

# --- BASE DE DONNÉES ---
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
    except: return None

def clean_shop(url):
    return url.replace("https://", "").replace("http://", "").strip("/") if url else ""

# --- FONCTIONS SHOPIFY ---
def get_shopify_session(shop, token):
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(shop, API_VERSION, token)
    shopify.ShopifyResource.activate_session(session)

def get_metafield(namespace, key, default=0):
    try:
        metafields = shopify.Metafield.find(namespace=namespace, key=key)
        if metafields:
            return int(float(metafields[0].value))
    except: pass
    return default

def set_metafield(namespace, key, value, type_val="integer"):
    try:
        metafield = shopify.Metafield()
        metafield.namespace = namespace
        metafield.key = key
        metafield.value = value
        metafield.type = type_val
        metafield.save()
    except Exception as e: print(f"Metafield Error: {e}")

# --- ROUTES STATIQUES ---
@app.get("/styles.css")
def styles(): return FileResponse('styles.css', media_type='text/css')

@app.get("/app.js")
def javascript(): return FileResponse('app.js', media_type='application/javascript')

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    shop = request.query_params.get("shop")
    return templates.TemplateResponse("index.html", { "request": request, "shop": shop, "api_key": SHOPIFY_API_KEY })

# --- ROUTES AUTHENTIFICATION (ADMIN) ---
@app.get("/login")
def login(shop: str):
    shop = clean_shop(shop)
    auth_url = f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={','.join(SCOPES)}&redirect_uri={HOST}/auth/callback"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(request: Request):
    params = dict(request.query_params)
    shop = clean_shop(params.get("shop"))
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
        return HTMLResponse(f"Auth Error: {res.text}", status_code=400)
    except Exception as e: return HTMLResponse(f"Error: {e}", status_code=500)

# --- ROUTES API DASHBOARD ---
@app.get("/api/get-data")
def get_data_route(shop: str):
    shop = clean_shop(shop)
    token = get_token_db(shop)
    if not token: return JSONResponse({"error": "No token"}, status_code=401)
    try:
        get_shopify_session(shop, token)
        credits = get_metafield("virtual_try_on", "wallet", 0)
        usage = get_metafield("virtual_try_on", "total_tryons", 0)
        return {"credits": credits, "usage": usage}
    except: return {"credits": 0}

# --- ROUTE GENERATION (LA LOGIQUE QUI MARCHE) ---
@app.post("/api/generate")
async def generate(
    shop: str = Form(...),
    person_image: UploadFile = File(...),
    clothing_url: str = Form(...) # On attend l'URL ici
):
    print(f"🚀 GENERATION REÇUE: Shop={shop}")
    
    shop = clean_shop(shop)
    token = get_token_db(shop)
    
    if not token:
        # En production, il faudrait bloquer. Pour le test, on log juste.
        print("⚠️ Attention: Token manquant pour ce shop.")

    try:
        # 1. Vérification Crédits (Si token existe)
        if token:
            get_shopify_session(shop, token)
            credits = get_metafield("virtual_try_on", "wallet", 0)
            if credits < 1:
                return JSONResponse({"error": "Plus de crédits disponibles."}, status_code=402)

        # 2. Appel Replicate
        person_bytes = await person_image.read()
        
        print(f"🤖 Envoi Replicate... (Modele: {MODEL_ID})")
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": io.BytesIO(person_bytes),
                "garm_img": clothing_url,
                "garment_des": "upper_body",
                "category": "upper_body",
                "crop": False,
                "seed": 42,
                "steps": 30
            }
        )
        
        result_url = str(output[0]) if isinstance(output, list) else str(output)
        print(f"✅ SUCCÈS: {result_url}")

        # 3. Débit & Stats (Si token existe)
        if token:
            set_metafield("virtual_try_on", "wallet", credits - 1)
            usage = get_metafield("virtual_try_on", "total_tryons", 0)
            set_metafield("virtual_try_on", "total_tryons", usage + 1)

        return {"result_image_url": result_url}

    except Exception as e:
        print(f"🔥 CRASH: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)
