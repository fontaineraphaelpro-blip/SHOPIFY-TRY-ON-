import os
import hmac
import hashlib
import base64
import json
import shopify
import requests
import replicate
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

# Modèle Replicate
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- BASES DE DONNÉES EN MÉMOIRE ---
shop_sessions = {}  
credits_db = {}     

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
def clean_shop_url(url: str):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").split('/')[0].strip("/")

def get_shopify_session(shop: str):
    token = shop_sessions.get(shop)
    if not token:
        return None
    session = shopify.Session(shop, API_VERSION, token)
    shopify.ShopifyResource.activate_session(session)
    return session

# --- ROUTES AUTHENTIFICATION ---

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
        payload = {
            "client_id": SHOPIFY_API_KEY, 
            "client_secret": SHOPIFY_API_SECRET, 
            "code": code
        }
        res = requests.post(url, json=payload)
        
        if res.status_code == 200:
            token = res.json().get('access_token')
            shop_sessions[shop] = token
            if shop not in credits_db:
                credits_db[shop] = 10 
            
            shop_name = shop.replace(".myshopify.com", "")
            # Redirection propre vers l'admin Shopify
            return RedirectResponse(f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}")
        return HTMLResponse(f"Token Error: {res.text}", status_code=400)
    except Exception as e:
        return HTMLResponse(content=f"Auth Error: {str(e)}", status_code=500)

# --- API CRÉDITS & PAIEMENTS ---

@app.get("/api/get-credits")
def api_get_credits(shop: str, authorization: str = Header(None)):
    shop = clean_shop_url(shop)
    # On renvoie les crédits ou 10 par défaut pour les nouveaux shops
    count = credits_db.get(shop, 10)
    return {"credits": count}

@app.post("/api/buy-credits")
def buy_credits(data: BuyModel, authorization: str = Header(None)):
    shop = clean_shop_url(data.shop)
    session = get_shopify_session(shop)
    
    if not session:
        return JSONResponse(content={"error": "Reauth needed"}, status_code=401)

    try:
        # Correspondance exacte avec ton HTML (Discovery, Standard, Business)
        prices = {
            "pack_discovery": 4.99,
            "pack_standard": 12.99,
            "pack_business": 29.99
        }
        
        price = prices.get(data.pack_id, 4.99)
        if data.pack_id == "pack_custom" and data.custom_amount:
            price = float(data.custom_amount) * 0.25

        charge = shopify.ApplicationCharge.create({
            "name": f"StyleLab Credits: {data.pack_id}",
            "price": price,
            "return_url": f"{HOST}/api/charge/callback?shop={shop}&pack_id={data.pack_id}&custom={data.custom_amount or 0}",
            "test": True 
        })

        if charge.confirmation_url:
            return {"confirmation_url": charge.confirmation_url}
        else:
            return JSONResponse(content={"error": "Shopify API returned no URL"}, status_code=500)
            
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/charge/callback")
def charge_callback(shop: str, charge_id: str, pack_id: str, custom: int = 0):
    shop = clean_shop_url(shop)
    if get_shopify_session(shop):
        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status == 'accepted':
            charge.activate()
            
            # Calcul des crédits
            adds = {"pack_discovery": 10, "pack_standard": 30, "pack_business": 100}
            to_add = adds.get(pack_id, int(custom))
            
            credits_db[shop] = credits_db.get(shop, 0) + to_add
            
    return RedirectResponse(f"https://{shop}/admin/apps/{SHOPIFY_API_KEY}")

# --- GÉNÉRATION IA ---

@app.post("/api/generate")
def generate_image(data: GenerateModel, authorization: str = Header(None)):
    shop = clean_shop_url(data.shop)
    
    current = credits_db.get(shop, 0)
    if current < 1 and shop != "demo":
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
            credits_db[shop] = current - 1
            
        return {"result_image_url": output}
    except Exception as e:
        return {"error": str(e)}

# --- FICHIERS STATIQUES ---
@app.get("/")
def index(): return FileResponse('index.html')

@app.get("/app.js")
def js(): return FileResponse('app.js')

@app.get("/styles.css")
def css(): return FileResponse('styles.css')

@app.post("/webhooks/gdpr")
async def gdpr(): return HTMLResponse("OK")
