import os
import hmac
import hashlib
import base64
import json
import shopify
import requests
import replicate
import sqlite3
from fastapi import FastAPI, Request, Header
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 
SCOPES = ['read_products', 'write_products']
API_VERSION = "2025-01"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

# --- BASE DE DONNÉES (SQLITE) ---
def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Initialisation des tables
db = get_db()
db.execute('CREATE TABLE IF NOT EXISTS sessions (shop TEXT PRIMARY KEY, token TEXT)')
db.execute('CREATE TABLE IF NOT EXISTS credits (shop TEXT PRIMARY KEY, count INTEGER)')
db.commit()
db.close()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODÈLES DE DONNÉES ---
class BuyModel(BaseModel):
    shop: str
    pack_id: str
    custom_amount: int = None

class GenerateModel(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str = "upper_body"

# --- UTILITAIRES ---
def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

def get_session(shop):
    db = get_db()
    row = db.execute('SELECT token FROM sessions WHERE shop = ?', (shop,)).fetchone()
    db.close()
    if not row: return None
    session = shopify.Session(shop, API_VERSION, row['token'])
    shopify.ShopifyResource.activate_session(session)
    return session

# --- ROUTES STATIQUES ---
@app.get("/")
def index():
    if os.path.exists('index.html'): return FileResponse('index.html')
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
            db = get_db()
            db.execute('INSERT OR REPLACE INTO sessions (shop, token) VALUES (?, ?)', (shop, token))
            # 10 crédits cadeaux si nouveau
            check = db.execute('SELECT count FROM credits WHERE shop = ?', (shop,)).fetchone()
            if not check:
                db.execute('INSERT INTO credits (shop, count) VALUES (?, ?)', (shop, 10))
            db.commit()
            db.close()
            
            shop_name = shop.replace(".myshopify.com", "")
            return RedirectResponse(f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}")
        return HTMLResponse(f"Token Error: {res.text}", status_code=400)
    except Exception as e:
        return HTMLResponse(content=f"Auth Error: {str(e)}", status_code=500)

# --- API CRÉDITS & PAIEMENT ---

@app.get("/api/get-credits")
def get_credits(shop: str, authorization: str = Header(None)):
    shop = clean_shop_url(shop)
    db = get_db()
    row = db.execute('SELECT count FROM credits WHERE shop = ?', (shop,)).fetchone()
    db.close()
    if not row: return JSONResponse(content={"error": "Session lost"}, status_code=401)
    return {"credits": row['count']}

@app.post("/api/buy-credits")
def buy_credits(data: BuyModel, authorization: str = Header(None)):
    shop = clean_shop_url(data.shop)
    if not get_session(shop):
        return JSONResponse(content={"error": "Session expirée"}, status_code=401)

    price = None
    name = ""
    if data.pack_id in ['pack_10', 'pack_discovery']:
        price = 4.99
        name = "Discovery Pack (10 Credits)"
    elif data.pack_id in ['pack_30', 'pack_standard']:
        price = 12.99
        name = "Standard Pack (30 Credits)"
    elif data.pack_id in ['pack_100', 'pack_business']:
        price = 29.99
        name = "Business Pack (100 Credits)"
    elif data.pack_id == 'pack_custom' and data.custom_amount:
        price = float(int(data.custom_amount) * 0.25)
        name = f"Custom Pack ({data.custom_amount} Credits)"
    
    if price is None: return JSONResponse(content={"error": "Pack invalide"}, status_code=400)

    try:
        charge = shopify.ApplicationCharge.create({
            "name": name,
            "price": price,
            "return_url": f"{HOST}/api/charge/callback?shop={shop}&pack_id={data.pack_id}&custom={data.custom_amount or 0}",
            "test": False # <--- MODE RÉEL ACTIVÉ
        })
        return {"confirmation_url": charge.confirmation_url}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/charge/callback")
def charge_callback(shop: str, charge_id: str, pack_id: str, custom: int = 0):
    shop = clean_shop_url(shop)
    if not get_session(shop): return HTMLResponse("Session expirée.")

    try:
        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status == 'accepted':
            charge.activate()
            
            credits_to_add = 0
            if pack_id in ['pack_10', 'pack_discovery']: credits_to_add = 10
            elif pack_id in ['pack_30', 'pack_standard']: credits_to_add = 30
            elif pack_id in ['pack_100', 'pack_business']: credits_to_add = 100
            elif pack_id == 'pack_custom': credits_to_add = int(custom)
            
            db = get_db()
            db.execute('UPDATE credits SET count = count + ? WHERE shop = ?', (credits_to_add, shop))
            db.commit()
            db.close()
            
            return RedirectResponse(f"https://{shop}/admin/apps/{SHOPIFY_API_KEY}")
        return HTMLResponse("Paiement refusé.")
    except Exception as e:
        return HTMLResponse(f"Erreur: {str(e)}")

# --- API GÉNÉRATION IA ---

@app.post("/api/generate")
def generate_image(data: GenerateModel, authorization: str = Header(None)):
    shop = clean_shop_url(data.shop)
    db = get_db()
    row = db.execute('SELECT count FROM credits WHERE shop = ?', (shop,)).fetchone()
    
    if (not row or row['count'] < 1) and shop != "demo":
        db.close()
        return {"error": "Crédits insuffisants"}

    try:
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": data.person_image_url,
                "garm_img": data.clothing_image_url,
                "garment_des": data.category,
            }
        )
        
        if shop != "demo":
            db.execute('UPDATE credits SET count = count - 1 WHERE shop = ?', (shop,))
            db.commit()
        db.close()
        return {"result_image_url": output}
    except Exception as e:
        db.close()
        return {"error": str(e)}

# --- WEBHOOKS RGPD ---
@app.post("/webhooks/gdpr")
async def gdpr_webhooks(request: Request):
    try:
        data = await request.body()
        hmac_header = request.headers.get('X-Shopify-Hmac-SHA256')
        topic = request.headers.get('X-Shopify-Topic')
        digest = hmac.new(SHOPIFY_API_SECRET.encode('utf-8'), data, hashlib.sha256).digest()
        computed_hmac = base64.b64encode(digest).decode()

        if not hmac_header or not hmac.compare_digest(computed_hmac, hmac_header):
            return HTMLResponse(content="Unauthorized", status_code=401)

        if topic == "shop/redact":
            payload = json.loads(data)
            db = get_db()
            db.execute('DELETE FROM credits WHERE shop = ?', (payload.get('shop_domain'),))
            db.execute('DELETE FROM sessions WHERE shop = ?', (payload.get('shop_domain'),))
            db.commit()
            db.close()

        print(f"✅ Webhook {topic} traité")
        return HTMLResponse(content="OK", status_code=200)
    except:
        return HTMLResponse(content="Error", status_code=200)
