import os, time, jwt, requests, shopify
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from pydantic import BaseModel

SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST")
API_VERSION = "2024-04"
APP_HANDLE = "vton-magic"

SCOPES = [
    "read_metafields",
    "write_metafields"
]

app = FastAPI()
shop_sessions = {}
pending_charges = {}

# ---------------- AUTH ----------------

def verify_token(auth: str, shop: str):
    if not auth:
        raise HTTPException(401, "No token")

    token = auth.replace("Bearer ", "")
    decoded = jwt.decode(
        token,
        SHOPIFY_API_SECRET,
        algorithms=["HS256"],
        audience=SHOPIFY_API_KEY
    )

    if decoded["iss"] != f"https://{shop}":
        raise HTTPException(401, "Invalid issuer")

    if decoded["exp"] < time.time():
        raise HTTPException(401, "Expired")

def activate_session(shop):
    token = shop_sessions.get(shop)
    if not token:
        raise HTTPException(401, "No session")
    session = shopify.Session(shop, API_VERSION, token)
    shopify.ShopifyResource.activate_session(session)

# ---------------- METAFIELDS ----------------

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

# ---------------- ROUTES ----------------

@app.get("/")
def index():
    return FileResponse("index.html")

@app.get("/app.js")
def js():
    return FileResponse("app.js")

@app.get("/styles.css")
def css():
    return FileResponse("styles.css")

@app.get("/login")
def login(shop: str):
    return RedirectResponse(
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={SHOPIFY_API_KEY}"
        f"&scope={','.join(SCOPES)}"
        f"&redirect_uri={HOST}/auth/callback"
    )

@app.get("/auth/callback")
def callback(shop: str, code: str):
    res = requests.post(
        f"https://{shop}/admin/oauth/access_token",
        json={
            "client_id": SHOPIFY_API_KEY,
            "client_secret": SHOPIFY_API_SECRET,
            "code": code
        }
    )
    token = res.json()["access_token"]
    shop_sessions[shop] = token

    return RedirectResponse(
        f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{APP_HANDLE}"
    )

@app.get("/api/get-credits")
def credits(shop: str, authorization: str = Header(None)):
    verify_token(authorization, shop)
    activate_session(shop)
    return {"credits": get_credits()}

class Buy(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def buy(data: Buy, authorization: str = Header(None)):
    verify_token(authorization, data.shop)
    activate_session(data.shop)

    prices = {"pack_10": 4.99, "pack_30": 12.99, "pack_100": 29.99}
    price = prices[data.pack_id]

    charge = shopify.RecurringApplicationCharge.create({
        "name": f"Credits {data.pack_id}",
        "price": price,
        "return_url": f"{HOST}/api/charge/callback?shop={data.shop}",
        "test": True
    })

    pending_charges[str(charge.id)] = data.pack_id
    return {"confirmation_url": charge.confirmation_url}

@app.get("/api/charge/callback")
def charge_callback(shop: str, charge_id: str):
    activate_session(shop)
    charge = shopify.RecurringApplicationCharge.find(charge_id)

    if charge.status == "accepted":
        charge.activate()
        pack = pending_charges.get(charge_id)
        bonus = {"pack_10": 10, "pack_30": 30, "pack_100": 100}
        set_credits(get_credits() + bonus[pack])

    return RedirectResponse(
        f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{APP_HANDLE}"
    )
