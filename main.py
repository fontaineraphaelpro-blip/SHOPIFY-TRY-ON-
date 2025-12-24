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
SCOPES = ['read_products', 'write_products', 'read_content', 'write_content'] # Ajout des scopes pour Metafields
API_VERSION = "2025-01"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

# --- STOCKAGE TEMPORAIRE DES TOKENS ---
# Note: Puisque tu ne veux pas de DB, si ton serveur redémarre, le marchand devra 
# juste cliquer sur l'app dans son admin pour se "re-logger" automatiquement.
shop_sessions = {}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODÈLES ---
class BuyModel(BaseModel):
    shop: str
    pack_id: str
    custom_amount: int = None

class GenerateModel(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str = "upper_body"

# --- UTILITAIRES METAFIELDS ---

def get_shop_credits(shop):
    """Lit les crédits depuis Shopify Metafields"""
    session = get_session(shop)
    if not session: return 0
    try:
        # On cherche un metafield dans le namespace 'stylelab' avec la clé 'credits'
        metafields = shopify.Metafield.find(namespace="stylelab", key="credits")
        if metafields:
            return int(metafields[0].value)
        return 10 # 10 crédits par défaut si rien n'existe
    except:
        return 10

def update_shop_credits(shop, new_count):
    """Écrit les crédits dans Shopify Metafields"""
    get_session(shop)
    metafield = shopify.Metafield({
        'namespace': 'stylelab',
        'key': 'credits',
        'value': new_count,
        'type': 'integer'
    })
    metafield.save()

def get_session(shop):
    token = shop_sessions.get(shop)
    if not token: return None
    session = shopify.Session(shop, API_VERSION, token)
    shopify.ShopifyResource.activate_session(session)
    return session

def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

# --- ROUTES ---

@app.get("/auth/callback")
def auth_callback(shop: str, code: str, host: str = None):
    shop = clean_shop_url(shop)
    try:
        url = f"https://{shop}/admin/oauth/access_token"
        payload = {"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code}
        res = requests.post(url, json=payload)
        
        if res.status_code == 200:
            token = res.json().get('access_token')
            shop_sessions[shop] = token # Stocké en mémoire vive (RAM)
            
            # On vérifie si les crédits existent déjà sur Shopify, sinon on les crée
            get_session(shop)
            if not shopify.Metafield.find(namespace="stylelab", key="credits"):
                update_shop_credits(shop, 10)
                
            shop_name = shop.replace(".myshopify.com", "")
            return RedirectResponse(f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}")
        return HTMLResponse(content="Auth Error", status_code=400)
    except Exception as e:
        return HTMLResponse(content=str(e), status_code=500)

@app.get("/api/get-credits")
def api_get_credits(shop: str, authorization: str = Header(None)):
    shop = clean_shop_url(shop)
    if shop not in shop_sessions:
        return JSONResponse(content={"error": "reauth_needed"}, status_code=401)
    
    count = get_shop_credits(shop)
    return {"credits": count}

@app.post("/api/buy-credits")
def buy_credits(data: BuyModel, authorization: str = Header(None)):
    shop = clean_shop_url(data.shop)
    if not get_session(shop): return JSONResponse(status_code=401)

    price = 4.99 # Exemple par défaut
    credits_to_add = 10
    
    if data.pack_id in ['pack_10', 'pack_discovery']:
        price, credits_to_add = 4.99, 10
    elif data.pack_id in ['pack_30', 'pack_standard']:
        price, credits_to_add = 12.99, 30
    elif data.pack_id in ['pack_100', 'pack_business']:
        price, credits_to_add = 29.99, 100
    elif data.pack_id == 'pack_custom':
        credits_to_add = int(data.custom_amount)
        price = float(credits_to_add * 0.25)

    try:
        charge = shopify.ApplicationCharge.create({
            "name": f"Top-up {credits_to_add} Credits",
            "price": price,
            "return_url": f"{HOST}/api/charge/callback?shop={shop}&add={credits_to_add}",
            "test": False # Production
        })
        return {"confirmation_url": charge.confirmation_url}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/charge/callback")
def charge_callback(shop: str, charge_id: str, add: int):
    shop = clean_shop_url(shop)
    if not get_session(shop): return HTMLResponse("Error")
    
    charge = shopify.ApplicationCharge.find(charge_id)
    if charge.status == 'accepted':
        charge.activate()
        # MISE À JOUR SHOPIFY
        current = get_shop_credits(shop)
        update_shop_credits(shop, current + add)
        
        return RedirectResponse(f"https://{shop}/admin/apps/{SHOPIFY_API_KEY}")
    return HTMLResponse("Payment Failed")

@app.post("/api/generate")
def generate_image(data: GenerateModel, authorization: str = Header(None)):
    shop = clean_shop_url(data.shop)
    if shop == "demo": # Mode démo sans crédits
        pass
    else:
        current = get_shop_credits(shop)
        if current < 1: return {"error": "Crédits insuffisants"}
        update_shop_credits(shop, current - 1)

    try:
        output = replicate.run(MODEL_ID, input={
            "human_img": data.person_image_url,
            "garm_img": data.clothing_image_url,
            "garment_des": data.category,
        })
        return {"result_image_url": output}
    except Exception as e:
        return {"error": str(e)}

# Serveur des fichiers statiques
@app.get("/")
def index(): return FileResponse('index.html')
@app.get("/app.js")
def js(): return FileResponse('app.js')
@app.get("/styles.css")
def css(): return FileResponse('styles.css')

@app.post("/webhooks/gdpr")
async def gdpr(): return HTMLResponse(content="OK", status_code=200)
