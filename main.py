import os
import shopify
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") # Doit être https://shopify-try-on.onrender.com
SCOPES = ['read_products', 'write_products']
API_VERSION = "2024-01"

# Ton modèle Replicate (IDM-VTON)
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mémoire tampon pour les tokens
shop_sessions = {}

def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

# --- ROUTES FICHIERS STATIQUES ---

@app.get("/")
def index():
    return FileResponse('index.html')

@app.get("/styles.css")
def styles():
    return FileResponse('styles.css')

@app.get("/app.js")
def javascript():
    return FileResponse('app.js')

# --- ROUTES SHOPIFY (INSTALLATION & AUTH) ---

@app.get("/login")
def login(shop: str):
    shop = clean_shop_url(shop)
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(shop, API_VERSION)
    
    redirect_uri = f"{HOST}/auth/callback"
    auth_url = session.create_permission_url(SCOPES, redirect_uri)
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(shop: str, code: str, host: str = None):
    shop = clean_shop_url(shop)
    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION)
        
        access_token = session.request_token({"code": code})
        shop_sessions[shop] = access_token
        
        shop_name = shop.replace(".myshopify.com", "")
        if host:
            return RedirectResponse(f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}?host={host}")
        else:
            return RedirectResponse(f"https://{shop}/admin/apps/{SHOPIFY_API_KEY}")
            
    except Exception as e:
        return HTMLResponse(content=f"Erreur d'authentification : {str(e)}", status_code=500)

# --- API CRÉDITS & PAIEMENT ---

class BuyRequest(BaseModel):
    shop: str
    pack_id: str
    custom_amount: int = 0

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    shop = clean_shop_url(req.shop)
    token = shop_sessions.get(shop)
    
    if not token:
        raise HTTPException(status_code=401, detail="Session expirée, veuillez recharger l'app.")

    price, name, credits = 0, "", 0
    if req.pack_id == 'pack_10': price, name, credits = 4.99, "10 Crédits", 10
    elif req.pack_id == 'pack_30': price, name, credits = 12.99, "30 Crédits", 30
    elif req.pack_id == 'pack_100': price, name, credits = 29.99, "100 Crédits", 100
    else: return {"error": "Pack invalide"}

    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        return_url = f"{HOST}/billing/callback?shop={shop}&amt={credits}"
        
        charge = shopify.ApplicationCharge.create({
            "name": name, "price": price, "test": True, "return_url": return_url
        })
        
        if charge.confirmation_url:
            return {"confirmation_url": charge.confirmation_url}
        return {"error": "Erreur création charge"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/billing/callback")
def billing_callback(shop: str, amt: int, charge_id: str):
    shop = clean_shop_url(shop)
    token = shop_sessions.get(shop)
    if not token: return RedirectResponse(f"/login?shop={shop}")

    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)

        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status != 'active': charge.activate()

        current_shop = shopify.Shop.current()
        credits_field = shopify.Metafield.find(namespace="stylelab", key="credits")
        
        current_credits = 0
        if credits_field:
            if isinstance(credits_field, list) and len(credits_field) > 0: current_credits = int(credits_field[0].value)
            else: current_credits = int(credits_field.value)

        new_total = current_credits + amt
        metafield = shopify.Metafield({'namespace': 'stylelab', 'key': 'credits', 'value': new_total, 'type': 'number_integer'})
        current_shop.add_metafield(metafield)

        shop_name = shop.replace(".myshopify.com", "")
        admin_url = f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}"
        return HTMLResponse(f"<script>window.top.location.href='{admin_url}';</script>")
    except Exception as e:
        return HTMLResponse(f"Erreur: {e}")

@app.get("/api/get-credits")
def get_credits(shop: str):
    shop = clean_shop_url(shop)
    token = shop_sessions.get(shop)
    if not token: raise HTTPException(status_code=401)

    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        mf = shopify.Metafield.find(namespace="stylelab", key="credits")
        credits = 0
        if mf:
            if isinstance(mf, list) and len(mf) > 0: credits = int(mf[0].value)
            else: credits = int(mf.value)
        return {"credits": credits}
    except: return {"credits": 0}

# --- API GÉNÉRATION IA (CORRIGÉE) ---

class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    try:
        # CORRECTION ICI : Nettoyage de l'URL pour Replicate
        clothing_url = req.clothing_image_url
        if clothing_url.startswith("//"):
            clothing_url = "https:" + clothing_url

        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": req.person_image_url,
                "garm_img": clothing_url, # On utilise l'URL nettoyée
                "garment_des": req.category, 
                "category": "upper_body",
                "crop": False, "seed": 42, "steps": 30
            }
        )
        url = str(output[0]) if isinstance(output, list) else str(output)
        return {"result_image_url": url}
    except Exception as e: return {"error": str(e)}

# --- WEBHOOKS OBLIGATOIRES (RGPD) ---
@app.post("/webhooks/customers/data_request")
def w1(): return {"ok": True}
@app.post("/webhooks/customers/redact")
def w2(): return {"ok": True}
@app.post("/webhooks/shop/redact")
def w3(): return {"ok": True}
