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
HOST = os.getenv("HOST") 
SCOPES = ['read_products', 'write_products']
API_VERSION = "2024-01"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

shop_sessions = {}

def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

# --- ROUTES STATIQUES ---
@app.get("/")
def index(): return FileResponse('index.html')

@app.get("/styles.css")
def styles(): return FileResponse('styles.css')

@app.get("/app.js")
def javascript(): return FileResponse('app.js')

# --- AUTHENTIFICATION ---
@app.get("/login")
def login(shop: str, host: str = None):
    shop = clean_shop_url(shop)
    auth_url = f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={','.join(SCOPES)}&redirect_uri={HOST}/auth/callback"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(shop: str, code: str, host: str = None):
    shop = clean_shop_url(shop)
    try:
        url = f"https://{shop}/admin/oauth/access_token"
        payload = {"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code}
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            token = res.json().get('access_token')
            shop_sessions[shop] = token
            shop_name = shop.replace(".myshopify.com", "")
            if host:
                return RedirectResponse(f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}?host={host}")
            else:
                return RedirectResponse(f"https://{shop}/admin/apps/{SHOPIFY_API_KEY}")
        return HTMLResponse(f"Error: {res.text}", status_code=400)
    except Exception as e:
        return HTMLResponse(content=f"Auth Error: {str(e)}", status_code=500)

# --- API CRÉDITS & PAIEMENTS (C'ÉTAIT MANQUANT) ---

@app.get("/api/get-credits")
def get_credits(shop: str):
    shop = clean_shop_url(shop)
    token = shop_sessions.get(shop)
    # Si pas de token en mémoire (redémarrage serveur), on renvoie 0 mais on ne plante pas
    if not token: return {"credits": 0}

    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        mf = shopify.Metafield.find(namespace="stylelab", key="credits")
        val = 0
        if mf:
            val = int(mf[0].value) if isinstance(mf, list) else int(mf.value)
        return {"credits": val}
    except:
        return {"credits": 0}

class BuyRequest(BaseModel):
    shop: str
    pack_id: str
    custom_amount: int = 0

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    shop = clean_shop_url(req.shop)
    token = shop_sessions.get(shop)
    if not token: raise HTTPException(status_code=401)

    price, name, credits = 0, "", 0
    if req.pack_id == 'pack_10': price, name, credits = 4.99, "10 Credits", 10
    elif req.pack_id == 'pack_30': price, name, credits = 12.99, "30 Credits", 30
    elif req.pack_id == 'pack_100': price, name, credits = 29.99, "100 Credits", 100
    elif req.pack_id == 'pack_custom':
        credits = req.custom_amount
        price = round(credits * 0.25, 2)
        name = f"{credits} Credits (Custom)"
    else: return {"error": "Invalid Pack"}

    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        return_url = f"{HOST}/billing/callback?shop={shop}&amt={credits}"
        charge = shopify.ApplicationCharge.create({
            "name": name, "price": price, "test": True, "return_url": return_url
        })
        return {"confirmation_url": charge.confirmation_url}
    except Exception as e: return {"error": str(e)}

@app.get("/billing/callback")
def billing_callback(shop: str, amt: int, charge_id: str):
    shop = clean_shop_url(shop)
    token = shop_sessions.get(shop)
    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)

        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status != 'active': charge.activate()

        current_shop = shopify.Shop.current()
        mf = shopify.Metafield.find(namespace="stylelab", key="credits")
        curr = int(mf[0].value) if (mf and isinstance(mf, list)) else (int(mf.value) if mf else 0)

        meta = shopify.Metafield({'namespace': 'stylelab', 'key': 'credits', 'value': curr + amt, 'type': 'number_integer'})
        current_shop.add_metafield(meta)

        # Retour à l'admin
        admin_url = f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}"
        return HTMLResponse(f"<script>window.top.location.href='{admin_url}';</script>")
    except Exception as e: return HTMLResponse(f"Error: {e}")

# --- API IA ---
class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    try:
        clothing_url = req.clothing_image_url
        if clothing_url.startswith("//"): clothing_url = "https:" + clothing_url
        output = replicate.run(MODEL_ID, input={
            "human_img": req.person_image_url, "garm_img": clothing_url,
            "garment_des": req.category, "category": "upper_body"
        })
        return {"result_image_url": str(output[0]) if isinstance(output, list) else str(output)}
    except Exception as e: return {"error": str(e)}

# --- WEBHOOKS ---
@app.post("/webhooks/customers/data_request")
def w1(): return {"ok": True}
@app.post("/webhooks/customers/redact")
def w2(): return {"ok": True}
@app.post("/webhooks/shop/redact")
def w3(): return {"ok": True}
