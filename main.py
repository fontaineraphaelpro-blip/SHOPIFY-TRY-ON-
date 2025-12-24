import os
import requests
import shopify
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST")  # Doit être https://ton-app.onrender.com
API_VERSION = "2024-04"
SCOPES = ['read_products', 'write_products']

# Replicate AI Model
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

# --- MIDDLEWARE DE SÉCURITÉ (Anti-Écran Blanc) ---
class ShopifySecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Indispensable pour que Shopify accepte d'afficher l'app dans l'iframe
        response.headers["Content-Security-Policy"] = (
            "frame-ancestors https://admin.shopify.com https://*.myshopify.com;"
        )
        return response

app.add_middleware(ShopifySecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- BASES DE DONNÉES (En mémoire pour le test) ---
shop_sessions = {}
credits_db = {}

# --- MODÈLES DE DONNÉES ---
class BuyModel(BaseModel):
    shop: str
    pack_id: str

class GenerateModel(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str = "upper_body"

# --- FONCTIONS UTILES ---
def clean_shop_url(shop: str):
    if not shop: return None
    return shop.replace("https://", "").replace("http://", "").split("/")[0]

def get_shopify_session(shop: str):
    token = shop_sessions.get(shop)
    if not token:
        return None
    session = shopify.Session(shop, API_VERSION, token)
    shopify.ShopifyResource.activate_session(session)
    return session

# --- ROUTES AUTHENTIFICATION ---

@app.get("/login")
def login(shop: str):
    shop = clean_shop_url(shop)
    auth_url = f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={','.join(SCOPES)}&redirect_uri={HOST}/auth/callback"
    return RedirectResponse(auth_url)

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
            token = res.json().get("access_token")
            shop_sessions[shop] = token
            if shop not in credits_db:
                credits_db[shop] = 10  # 10 crédits offerts
            
            # Redirection vers l'admin Shopify
            shop_name = shop.replace(".myshopify.com", "")
            return RedirectResponse(f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}")
    except Exception as e:
        return HTMLResponse(content=f"Erreur Auth: {str(e)}", status_code=500)

# --- API CRÉDITS & PAIEMENTS ---

@app.get("/api/get-credits")
def get_credits(shop: str, authorization: str = Header(None)):
    shop = clean_shop_url(shop)
    count = credits_db.get(shop, 10)
    return {"credits": count}

@app.post("/api/buy-credits")
def buy_credits(data: BuyModel, authorization: str = Header(None)):
    shop = clean_shop_url(data.shop)
    session = get_shopify_session(shop)
    
    if not session:
        return JSONResponse(status_code=401, content={"error": "Session expirée, rechargez l'app"})

    # Prix correspondants à ton HTML
    prices = {
        "pack_discovery": 4.99,
        "pack_standard": 12.99,
        "pack_business": 29.99
    }
    
    price = prices.get(data.pack_id, 4.99)

    try:
        charge = shopify.ApplicationCharge.create({
            "name": f"Crédits StyleLab - {data.pack_id}",
            "price": price,
            "return_url": f"{HOST}/api/charge/callback?shop={shop}&pack_id={data.pack_id}",
            "test": True  # Mettre False pour de vrais paiements
        })
        return {"confirmation_url": charge.confirmation_url}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/charge/callback")
def charge_callback(shop: str, charge_id: str, pack_id: str):
    shop = clean_shop_url(shop)
    get_shopify_session(shop)
    
    charge = shopify.ApplicationCharge.find(charge_id)
    if charge.status == "accepted":
        charge.activate()
        
        # Ajout des crédits
        bonus = {"pack_discovery": 10, "pack_standard": 30, "pack_business": 100}
        credits_db[shop] = credits_db.get(shop, 0) + bonus.get(pack_id, 0)
        
    return RedirectResponse(f"https://{shop}/admin/apps/{SHOPIFY_API_KEY}")

# --- API GÉNÉRATION IA ---

@app.post("/api/generate")
def generate(data: GenerateModel, authorization: str = Header(None)):
    shop = clean_shop_url(data.shop)
    
    current_credits = credits_db.get(shop, 0)
    if current_credits <= 0:
        return {"error": "Crédits insuffisants. Veuillez en acheter."}

    try:
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": data.person_image_url,
                "garm_img": data.clothing_image_url,
                "garment_des": data.category
            }
        )
        # Débiter un crédit
        credits_db[shop] = current_credits - 1
        return {"result_image_url": output}
    except Exception as e:
        return {"error": f"Erreur IA: {str(e)}"}

# --- FICHIERS STATIQUES ---

@app.get("/")
def read_index():
    return FileResponse("index.html")

@app.get("/app.js")
def read_js():
    return FileResponse("app.js")

@app.get("/styles.css")
def read_css():
    return FileResponse("styles.css")

@app.post("/webhooks/gdpr")
def gdpr():
    return {"status": "ok"}
