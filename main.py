import os
import shopify
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 
SCOPES = ['read_products', 'write_products']
API_VERSION = "2025-01" 
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

# Autorise ta boutique à parler au serveur
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sert les fichiers (CSS/JS) qui sont à la racine
app.mount("/static", StaticFiles(directory="."), name="static")

# STOCKAGE EN MÉMOIRE (Pas de base de données)
shop_sessions = {}

def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

# --- ROUTES ---
@app.get("/")
def index():
    return FileResponse('index.html')

@app.get("/login")
def login(shop: str):
    clean_shop = clean_shop_url(shop)
    auth_url = f"https://{clean_shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={','.join(SCOPES)}&redirect_uri={HOST}/auth/callback"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(shop: str, code: str):
    clean_shop = clean_shop_url(shop)
    url = f"https://{clean_shop}/admin/oauth/access_token"
    payload = {"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code}
    
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            token = res.json().get('access_token')
            # ON SAUVEGARDE LE TOKEN EN RAM
            shop_sessions[clean_shop] = token
            return RedirectResponse(f"https://admin.shopify.com/store/{clean_shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
    except: pass
    return HTMLResponse("Erreur Connexion Shopify")

# --- API PAIEMENT & IA ---
class BuyRequest(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    shop = clean_shop_url(req.shop)
    
    # On récupère le token en RAM
    token = shop_sessions.get(shop)
    if not token:
        # Si la RAM est vide (redémarrage), on dit au JS de recharger la page
        raise HTTPException(status_code=401, detail="Reload needed")

    if req.pack_id == 'pack_10': price, name = 4.99, "10 Crédits"
    elif req.pack_id == 'pack_30': price, name = 9.99, "30 Crédits"
    else: price, name = 19.99, "100 Crédits"

    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        charge = shopify.ApplicationCharge.create({
            "name": name, "price": price, "test": True,
            "return_url": f"{HOST}/billing/callback?shop={shop}"
        })
        
        if charge.confirmation_url: return {"confirmation_url": charge.confirmation_url}
        return {"error": "Erreur Shopify"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/billing/callback")
def billing_callback(shop: str):
    return HTMLResponse("<script>window.location.href='/';</script>")

class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    try:
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": req.person_image_url,
                "garm_img": req.clothing_image_url,
                "garment_des": req.category, 
                "category": "upper_body",
                "crop": False, "seed": 42, "steps": 30
            }
        )
        url = str(output[0]) if isinstance(output, list) else str(output)
        return {"result_image_url": url}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/get-credits")
def get_credits(shop: str):
    return {"credits": 120}
