import os
import hmac
import hashlib
import base64
import shopify
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
# Récupération des variables d'environnement
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST")
SCOPES = ['read_products', 'write_products']
API_VERSION = "2024-01"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

shop_sessions = {}

def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

# --- ROUTES STATIQUES ---
@app.get("/")
def index():
    if os.path.exists('index.html'):
        return FileResponse('index.html')
    return HTMLResponse("<h1>StyleLab App is Running</h1>")

@app.get("/styles.css")
def styles():
    if os.path.exists('styles.css'): return FileResponse('styles.css')
    return HTMLResponse("")

@app.get("/app.js")
def javascript():
    if os.path.exists('app.js'): return FileResponse('app.js')
    return HTMLResponse("")

# --- AUTHENTIFICATION ---
@app.get("/login")
def login(shop: str, host: str = None):
    shop = clean_shop_url(shop)
    auth_url = f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={','.join(SCOPES)}&redirect_uri={HOST}/auth/callback"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(shop: str, code: str, host: str = None):
    shop = clean_shop_url(shop)
    try:
        url = f"https://{shop}/admin/oauth/access_token"
        payload = {"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code}
        res = requests.post(url, json=payload)
        
        if res.status_code == 200:
            token = res.json().get('access_token')
            shop_sessions[shop] = token
            shop_name = shop.replace(".myshopify.com", "")
            if host:
                return RedirectResponse(f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}?host={host}")
            else:
                return RedirectResponse(f"https://{shop}/admin/apps/{SHOPIFY_API_KEY}")
        return HTMLResponse(f"Token Error: {res.text}", status_code=400)
    except Exception as e:
        return HTMLResponse(content=f"Auth Error: {str(e)}", status_code=500)

# --- API ---
@app.get("/api/get-credits")
def get_credits(shop: str):
    return {"credits": 10} # Version simplifiée pour test

# --- WEBHOOKS GDPR OBLIGATOIRES (La partie CRUCIALE) ---
@app.post("/webhooks/gdpr")
async def gdpr_webhooks(request: Request):
    try:
        # 1. Lire les données brutes
        data = await request.body()
        
        # 2. Vérifier la signature HMAC (Obligatoire pour Shopify)
        hmac_header = request.headers.get('X-Shopify-Hmac-SHA256')
        
        if not SHOPIFY_API_SECRET:
            print("❌ Erreur: Secret API manquant")
            return HTMLResponse(content="Config Error", status_code=500)

        digest = hmac.new(SHOPIFY_API_SECRET.encode('utf-8'), data, hashlib.sha256).digest()
        computed_hmac = base64.b64encode(digest).decode()

        # 3. Comparaison
        if hmac_header and hmac.compare_digest(computed_hmac, hmac_header):
            print("✅ Webhook validé et reçu.")
            return HTMLResponse(content="OK", status_code=200)
        else:
            print("⛔ Signature invalide.")
            return HTMLResponse(content="Unauthorized", status_code=401)
    except Exception as e:
        print(f"Erreur: {str(e)}")
        return HTMLResponse(content="Error", status_code=500)
