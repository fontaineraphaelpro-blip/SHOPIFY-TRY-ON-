import os
import requests
import shopify
from fastapi import FastAPI, Request, Header
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 
API_VERSION = "2024-04"
SCOPES = ['read_products', 'write_products']
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

# --- MIDDLEWARE CSP (FORCE L'AFFICHAGE DANS SHOPIFY) ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # On autorise explicitement l'admin Shopify à encapsuler notre app
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors https://admin.shopify.com https://*.myshopify.com;"
    )
    # Suppression des protections qui bloquent le chargement en Iframe
    if "X-Frame-Options" in response.headers:
        del response.headers["X-Frame-Options"]
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

shop_sessions = {}
credits_db = {}

class BuyModel(BaseModel):
    shop: str
    pack_id: str

class GenerateModel(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str = "upper_body"

def clean_shop_url(shop: str):
    if not shop: return None
    return shop.replace("https://", "").replace("http://", "").split("/")[0]

def get_shopify_session(shop: str):
    token = shop_sessions.get(shop)
    if not token: return None
    session = shopify.Session(shop, API_VERSION, token)
    shopify.ShopifyResource.activate_session(session)
    return session

# --- ROUTES ---

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
        res = requests.post(url, json={
            "client_id": SHOPIFY_API_KEY,
            "client_secret": SHOPIFY_API_SECRET,
            "code": code
        })
        if res.status_code == 200:
            token = res.json().get("access_token")
            shop_sessions[shop] = token
            if shop not in credits_db: credits_db[shop] = 10
            
            shop_name = shop.replace(".myshopify.com", "")
            # Redirection vers l'URL officielle de l'admin
            return RedirectResponse(f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}")
    except Exception as e:
        return HTMLResponse(content=f"Error: {str(e)}", status_code=500)

@app.get("/api/get-credits")
def get_credits(shop: str, authorization: str = Header(None)):
    shop = clean_shop_url(shop)
    return {"credits": credits_db.get(shop, 10)}

@app.post("/api/buy-credits")
def buy_credits(data: BuyModel, authorization: str = Header(None)):
    shop = clean_shop_url(data.shop)
    session = get_shopify_session(shop)
    if not session: return JSONResponse(status_code=401, content={"error": "Reauth"})

    prices = {"pack_10": 4.99, "pack_30": 12.99, "pack_100": 29.99}
    price = prices.get(data.pack_id, 4.99)

    try:
        charge = shopify.ApplicationCharge.create({
            "name": f"Credits {data.pack_id}",
            "price": price,
            "return_url": f"{HOST}/api/charge/callback?shop={shop}&pack_id={data.pack_id}",
            "test": True
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
        bonus = {"pack_10": 10, "pack_30": 30, "pack_100": 100}
        credits_db[shop] = credits_db.get(shop, 0) + bonus.get(pack_id, 0)
    return RedirectResponse(f"https://{shop}/admin/apps/{SHOPIFY_API_KEY}")

# --- SERVEUR DE FICHIERS (IMPORTANT : VERIFIEZ LES CHEMINS) ---
@app.get("/")
def read_index(): return FileResponse("index.html")

@app.get("/app.js")
def read_js(): return FileResponse("app.js")

@app.get("/styles.css")
def read_css(): return FileResponse("styles.css")
