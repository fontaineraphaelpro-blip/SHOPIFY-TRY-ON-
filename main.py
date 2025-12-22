import os
import shopify
import httpx # Le secret de la vitesse
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import replicate

# CONFIG
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 
SCOPES = ['read_products', 'write_products']
API_VERSION = "2024-01" # Version stable
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="."), name="static")

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
    if not shop: return HTMLResponse("Shop manquant")
    shop = clean_shop_url(shop)
    auth_url = f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={','.join(SCOPES)}&redirect_uri={HOST}/auth/callback"
    return RedirectResponse(auth_url)

# OPTIMISATION 1 : AUTHENTIFICATION ASYNC (Règle le bug des 30s à l'installation)
@app.get("/auth/callback")
async def auth_callback(shop: str, code: str):
    shop = clean_shop_url(shop)
    url = f"https://{shop}/admin/oauth/access_token"
    payload = {"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code}
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload)
        
    if resp.status_code == 200:
        token = resp.json().get('access_token')
        shop_sessions[shop] = token
        return RedirectResponse(f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
    
    return HTMLResponse("Erreur Connexion")

# --- API ---
class BuyRequest(BaseModel):
    shop: str
    pack_id: str

# OPTIMISATION 2 : PAIEMENT ASYNC (Règle la lenteur des boutons)
@app.post("/api/buy-credits")
async def buy_credits(req: BuyRequest):
    shop = clean_shop_url(req.shop)
    token = shop_sessions.get(shop)
    
    if not token:
        # Si pas de token, on renvoie l'ordre de recharger
        raise HTTPException(status_code=401, detail="Reload needed")

    if req.pack_id == 'pack_10': price, name = 4.99, "10 Crédits"
    elif req.pack_id == 'pack_30': price, name = 9.99, "30 Crédits"
    else: price, name = 19.99, "100 Crédits"

    # Construction manuelle de la requête Shopify (Beaucoup plus rapide que la lib officielle)
    url = f"https://{shop}/admin/api/{API_VERSION}/application_charges.json"
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    payload = {
        "application_charge": {
            "name": name,
            "price": price,
            "test": True,
            "return_url": f"{HOST}/billing/callback?shop={shop}"
        }
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code == 201:
        data = resp.json()
        return {"confirmation_url": data['application_charge']['confirmation_url']}
    
    # Si erreur 401 (Token invalide côté Shopify)
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Token invalid")
        
    return {"error": "Erreur Shopify", "details": resp.text}

@app.get("/billing/callback")
def billing_callback(shop: str):
    return HTMLResponse("<script>window.top.location.href='/';</script>")

class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    # L'IA est déjà rapide, on ne touche pas
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
