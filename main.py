import os
import shopify
import requests
from fastapi import FastAPI, Request, Header
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 
API_VERSION = "2025-01"

app = FastAPI()

# Configuration CORS pour autoriser les requêtes depuis Shopify
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- BASES DE DONNÉES EN MÉMOIRE (RAM) ---
shop_sessions = {}  
credits_db = {}     

class BuyModel(BaseModel):
    shop: str
    pack_id: str

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

# --- ROUTES D'AUTHENTIFICATION ---

@app.get("/auth/callback")
def auth_callback(shop: str, code: str):
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
            # Initialisation des 10 crédits gratuits
            if shop not in credits_db:
                credits_db[shop] = 10 
            
            shop_name = shop.replace(".myshopify.com", "")
            # Redirection vers l'admin Shopify
            return RedirectResponse(f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}")
        return HTMLResponse(f"Erreur Token: {res.text}", status_code=400)
    except Exception as e:
        return HTMLResponse(content=f"Erreur Auth: {str(e)}", status_code=500)

# --- API CRÉDITS & PAIEMENTS ---

@app.get("/api/get-credits")
def api_get_credits(shop: str, authorization: str = Header(None)):
    shop = clean_shop_url(shop)
    # Renvoie les crédits stockés ou 10 par défaut
    count = credits_db.get(shop, 10)
    return {"credits": count}

@app.post("/api/buy-credits")
def buy_credits(data: BuyModel, authorization: str = Header(None)):
    shop = clean_shop_url(data.shop)
    session = get_shopify_session(shop)
    
    if not session:
        return JSONResponse(content={"error": "Session expirée, veuillez recharger l'app"}, status_code=401)

    try:
        # Définition du prix selon le pack
        price = 4.99 if data.pack_id in ["pack_10", "pack_discovery"] else 12.99
        
        # Création de la demande de paiement chez Shopify
        charge = shopify.ApplicationCharge.create({
            "name": f"Pack Crédits StyleLab ({data.pack_id})",
            "price": price,
            "return_url": f"{HOST}/api/charge/callback?shop={shop}&pack_id={data.pack_id}",
            "test": True # Laisse sur True pour tester sans payer, False pour le réel
        })

        if charge.confirmation_url:
            return {"confirmation_url": charge.confirmation_url}
        else:
            return JSONResponse(content={"error": "Impossible de générer l'URL Shopify"}, status_code=500)
            
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/charge/callback")
def charge_callback(shop: str, charge_id: str, pack_id: str):
    shop = clean_shop_url(shop)
    if get_shopify_session(shop):
        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status == 'accepted':
            charge.activate()
            # Ajout des crédits après confirmation
            add = 10 if pack_id in ["pack_10", "pack_discovery"] else 30
            credits_db[shop] = credits_db.get(shop, 0) + add
            
    return RedirectResponse(f"https://{shop}/admin/apps/{SHOPIFY_API_KEY}")

# --- SERVEUR DE FICHIERS ---

@app.get("/")
def index(): 
    return FileResponse('index.html')

@app.get("/app.js")
def js(): 
    return FileResponse('app.js')

@app.get("/styles.css")
def css(): 
    return FileResponse('styles.css')

@app.post("/webhooks/gdpr")
async def gdpr(): 
    return HTMLResponse("OK", status_code=200)
