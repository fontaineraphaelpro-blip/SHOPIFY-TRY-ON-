import os
import requests
import shopify
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST")
API_VERSION = "2024-04"
APP_HANDLE = "vton-magic"

app = FastAPI()
shop_sessions = {}

# Middleware CSP
@app.middleware("http")
async def shopify_csp(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "frame-ancestors https://admin.shopify.com https://*.myshopify.com"
    response.headers.pop("X-Frame-Options", None)
    return response

# Helpers
def activate_session(shop: str):
    token = shop_sessions.get(shop)
    if not token:
        raise HTTPException(401, "Shop not authenticated")
    session = shopify.Session(shop, API_VERSION, token)
    shopify.ShopifyResource.activate_session(session)

def get_credits():
    shop = shopify.Shop.current()
    for m in shop.metafields():
        if m.namespace == "vton_magic" and m.key == "credits":
            return int(m.value)
    return 10

def set_credits(value: int):
    shop = shopify.Shop.current()
    metafield = shopify.Metafield({
        "namespace": "vton_magic",
        "key": "credits",
        "type": "number_integer",
        "value": value,
        "owner_resource": "shop",
        "owner_id": shop.id
    })
    metafield.save()

# Static files
@app.get("/")
def index(): return FileResponse("index.html")
@app.get("/app.js")
def js(): return FileResponse("app.js")
@app.get("/styles.css")
def css(): return FileResponse("styles.css")

# OAuth
@app.get("/login")
def login(shop: str):
    return RedirectResponse(
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={SHOPIFY_API_KEY}&scope=read_metafields,write_metafields"
        f"&redirect_uri={HOST}/auth/callback"
    )

@app.get("/auth/callback")
def callback(shop: str, code: str):
    res = requests.post(f"https://{shop}/admin/oauth/access_token", json={
        "client_id": SHOPIFY_API_KEY,
        "client_secret": SHOPIFY_API_SECRET,
        "code": code
    })
    token = res.json()["access_token"]
    shop_sessions[shop] = token
    return RedirectResponse(f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{APP_HANDLE}")

# API
@app.get("/api/get-credits")
def api_get_credits(shop: str, authorization: str = Header(None)):
    activate_session(shop)
    return {"credits": get_credits()}

class BuyModel(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def api_buy(data: BuyModel, authorization: str = Header(None)):
    activate_session(data.shop)
    prices = {"pack_10": 4.99, "pack_30": 12.99, "pack_100": 29.99}
    charge = shopify.RecurringApplicationCharge.create({
        "name": f"Credits {data.pack_id}",
        "price": prices[data.pack_id],
        "return_url": f"{HOST}/",
        "test": True
    })
    return {"confirmation_url": charge.confirmation_url}
