import os
import requests
import shopify
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST")  # Exemple: https://ton-app.com
API_VERSION = "2024-04"
APP_HANDLE = "vton-magic"

app = FastAPI()

shop_sessions = {}  # stocke les tokens en mémoire (à récupérer via id_token côté client)

# --- MIDDLEWARE CSP (Shopify iframe) ---
@app.middleware("http")
async def shopify_csp(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "frame-ancestors https://admin.shopify.com https://*.myshopify.com"
    # Supprime X-Frame-Options si existant
    if "x-frame-options" in response.headers:
        del response.headers["x-frame-options"]
    return response

# --- Helpers ---
def activate_session(shop: str):
    token = shop_sessions.get(shop)
    if not token:
        raise HTTPException(401, "Shop not authenticated")
    session = shopify.Session(shop, API_VERSION, token)
    shopify.ShopifyResource.activate_session(session)

def get_credits():
    """Récupère les crédits depuis les metafields Shopify"""
    shop = shopify.Shop.current()
    metafields = shopify.Metafield.find(namespace="vton_magic")
    for m in metafields:
        if m.key == "credits":
            return int(m.value)
    return 10  # valeur par défaut

def set_credits(value: int):
    """Stocke les crédits dans les metafields Shopify"""
    shop = shopify.Shop.current()
    metafields = shopify.Metafield.find(namespace="vton_magic")
    for m in metafields:
        if m.key == "credits":
            m.value = value
            m.save()
            return
    # Si pas trouvé, création
    mf = shopify.Metafield({
        "namespace": "vton_magic",
        "key": "credits",
        "type": "number_integer",
        "value": value,
        "owner_resource": "shop",
        "owner_id": shop.id
    })
    mf.save()

# --- MODE SERVEUR DE FICHIERS ---
@app.get("/")
def index():
    return FileResponse("index.html")

@app.get("/app.js")
def js():
    return FileResponse("app.js")

@app.get("/styles.css")
def css():
    return FileResponse("styles.css")

# --- ROUTES OAUTH ---
@app.get("/login")
def login(shop: str):
    shop_clean = shop.replace("https://","").replace("http://","").split("/")[0]
    auth_url = (
        f"https://{shop_clean}/admin/oauth/authorize"
        f"?client_id={SHOPIFY_API_KEY}"
        f"&scope=read_metafields,write_metafields"
        f"&redirect_uri={HOST}/auth/callback"
    )
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def callback(shop: str, code: str):
    shop_clean = shop.replace("https://","").replace("http://","").split("/")[0]
    res = requests.post(f"https://{shop_clean}/admin/oauth/access_token", json={
        "client_id": SHOPIFY_API_KEY,
        "client_secret": SHOPIFY_API_SECRET,
        "code": code
    })
    token = res.json()["access_token"]
    shop_sessions[shop_clean] = token
    return RedirectResponse(f"https://admin.shopify.com/store/{shop_clean}/apps/{APP_HANDLE}")

# --- API GET CREDITS ---
@app.get("/api/get-credits")
def api_get_credits(shop: str, authorization: str = Header(None)):
    activate_session(shop)
    return {"credits": get_credits()}

# --- API ACHAT CREDITS ---
class BuyModel(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def api_buy(data: BuyModel, authorization: str = Header(None)):
    activate_session(data.shop)
    prices = {"pack_10": 4.99, "pack_30": 12.99, "pack_100": 29.99}
    try:
        charge = shopify.RecurringApplicationCharge.create({
            "name": f"Credits {data.pack_id}",
            "price": prices[data.pack_id],
            "return_url": f"{HOST}/",
            "test": True
        })
        return {"confirmation_url": charge.confirmation_url}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
