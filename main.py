import os
import hmac
import hashlib
import base64
import json
import shopify
import requests
import replicate
from fastapi import FastAPI, Request, Header # AJOUT DE HEADER
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
credits_db = {}     

class BuyModel(BaseModel):
    shop: str
    pack_id: str
    custom_amount: int = None

class GenerateModel(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str = "upper_body"

def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

def get_session(shop):
    token = shop_sessions.get(shop)
    if not token:
        return None
    session = shopify.Session(shop, API_VERSION, token)
    shopify.ShopifyResource.activate_session(session)
    return session

@app.get("/")
def index():
    if os.path.exists('index.html'): return FileResponse('index.html')
    return HTMLResponse("<h1>StyleLab App is Running</h1>")

@app.get("/styles.css")
def styles():
    if os.path.exists('styles.css'): return FileResponse('styles.css')
    return HTMLResponse("")

@app.get("/app.js")
def javascript():
    if os.path.exists('app.js'): return FileResponse('app.js')
    return HTMLResponse("")

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
            if shop not in credits_db:
                credits_db[shop] = 10 
                
            shop_name = shop.replace(".myshopify.com", "")
            if host:
                return RedirectResponse(f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}?host={host}")
            else:
                return RedirectResponse(f"https://{shop}/admin/apps/{SHOPIFY_API_KEY}")
        return HTMLResponse(f"Token Error: {res.text}", status_code=400)
    except Exception as e:
        return HTMLResponse(content=f"Auth Error: {str(e)}", status_code=500)

# --- API CRÉDITS & PAIEMENT (AVEC HEADER POUR VALIDATION) ---

@app.get("/api/get-credits")
def get_credits(shop: str, authorization: str = Header(None)): # AJOUTÉ
    shop = clean_shop_url(shop)
    if shop not in shop_sessions:
        return JSONResponse(content={"error": "Session lost"}, status_code=401)
    
    count = credits_db.get(shop, 0)
    return {"credits": count}

@app.post("/api/buy-credits")
def buy_credits(data: BuyModel, authorization: str = Header(None)): # AJOUTÉ
    shop = clean_shop_url(data.shop)
    if not get_session(shop):
        return JSONResponse(content={"error": "Session expirée"}, status_code=401)

    try:
        price = None
        name = ""
        
        if data.pack_id == 'pack_discovery':
            price = 4.99
            name = "Discovery Pack (10 Credits)"
        elif data.pack_id == 'pack_standard':
            price = 12.99
            name = "Standard Pack (30 Credits)"
        elif data.pack_id == 'pack_business':
            price = 29.99
            name = "Business Pack (100 Credits)"
        elif data.pack_id == 'pack_custom' and data.custom_amount:
            amount = int(data.custom_amount)
            price = float(amount * 0.25)
            name = f"Custom Pack ({amount} Credits)"
        
        if price is None:
            return JSONResponse(content={"error": "Pack invalide"}, status_code=400)

        charge = shopify.ApplicationCharge.create({
            "name": name,
            "price": price,
            "return_url": f"{HOST}/api/charge/callback?shop={shop}&pack_id={data.pack_id}&custom={data.custom_amount or 0}",
            "test": True 
        })

        if charge.confirmation_url:
            return {"confirmation_url": charge.confirmation_url}
        else:
            return {"error": "Erreur création charge Shopify"}

    except Exception as e:
        print(f"Erreur paiement: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/charge/callback")
def charge_callback(shop: str, charge_id: str, pack_id: str, custom: int = 0):
    shop = clean_shop_url(shop)
    if not get_session(shop):
        return HTMLResponse("Session expirée. Veuillez recharger l'application.")

    try:
        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status == 'accepted':
            charge.activate()
            
            credits_to_add = 0
            if pack_id == 'pack_discovery': credits_to_add = 10
            elif pack_id == 'pack_standard': credits_to_add = 30
            elif pack_id == 'pack_business': credits_to_add = 100
            elif pack_id == 'pack_custom': credits_to_add = int(custom)
            
            current = credits_db.get(shop, 0)
            credits_db[shop] = current + credits_to_add
            
            return RedirectResponse(f"https://{shop}/admin/apps/{SHOPIFY_API_KEY}")
        else:
            return HTMLResponse("Paiement refusé ou annulé.")
            
    except Exception as e:
        return HTMLResponse(f"Erreur validation paiement: {str(e)}")

@app.post("/api/generate")
def generate_image(data: GenerateModel, authorization: str = Header(None)): # AJOUTÉ
    shop = clean_shop_url(data.shop)
    
    current_credits = credits_db.get(shop, 0)
    if current_credits < 1 and shop != "demo":
        return {"error": "Crédits insuffisants"}

    try:
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": data.person_image_url,
                "garm_img": data.clothing_image_url,
                "garment_des": data.category,
            }
        )
        
        if shop != "demo":
            credits_db[shop] = current_credits - 1
            
        return {"result_image_url": output}
        
    except Exception as e:
        print(f"Replicate Error: {e}")
        return {"error": str(e)}

@app.post("/webhooks/gdpr")
async def gdpr_webhooks(request: Request):
    try:
        data = await request.body()
        hmac_header = request.headers.get('X-Shopify-Hmac-SHA256')
        topic = request.headers.get('X-Shopify-Topic')
        
        if not SHOPIFY_API_SECRET:
            return HTMLResponse(content="Config Error", status_code=500)

        digest = hmac.new(SHOPIFY_API_SECRET.encode('utf-8'), data, hashlib.sha256).digest()
        computed_hmac = base64.b64encode(digest).decode()

        if not hmac_header or not hmac.compare_digest(computed_hmac, hmac_header):
            return HTMLResponse(content="Unauthorized", status_code=401)

        print(f"✅ RGPD Webhook reçu : {topic}")
        return HTMLResponse(content="Webhook received", status_code=200)

    except Exception as e:
        return HTMLResponse(content="Error processed", status_code=200)
