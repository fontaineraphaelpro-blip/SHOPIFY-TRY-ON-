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
def index():
    return FileResponse('index.html')

@app.get("/styles.css")
def styles():
    return FileResponse('styles.css')

@app.get("/app.js")
def javascript():
    return FileResponse('app.js')

# --- ROUTES SHOPIFY (RÉPARÉES) ---

@app.get("/login")
def login(shop: str, host: str = None):
    shop = clean_shop_url(shop)
    # On construit l'URL manuellement pour éviter les erreurs de session préalable
    auth_url = (
        f"https://{shop}/admin/oauth/authorize?"
        f"client_id={SHOPIFY_API_KEY}&"
        f"scope={','.join(SCOPES)}&"
        f"redirect_uri={HOST}/auth/callback"
    )
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(shop: str, code: str, host: str = None):
    shop = clean_shop_url(shop)
    try:
        # Échange manuel du code contre le token (CONTOURNE L'ERREUR HMAC)
        url = f"https://{shop}/admin/oauth/access_token"
        payload = {
            "client_id": SHOPIFY_API_KEY,
            "client_secret": SHOPIFY_API_SECRET,
            "code": code
        }
        res = requests.post(url, json=payload)
        
        if res.status_code == 200:
            token = res.json().get('access_token')
            shop_sessions[shop] = token
            
            # Redirection vers l'admin Shopify en mode Embed
            shop_name = shop.replace(".myshopify.com", "")
            if host:
                # Utilisation du paramètre host pour éviter les boucles de redirection
                return RedirectResponse(f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}?host={host}")
            else:
                return RedirectResponse(f"https://{shop}/admin/apps/{SHOPIFY_API_KEY}")
        else:
            return HTMLResponse(f"Erreur d'échange de token: {res.text}", status_code=400)
            
    except Exception as e:
        return HTMLResponse(content=f"Erreur d'authentification : {str(e)}", status_code=500)

# --- API GÉNÉRATION IA (NETTOYÉE) ---

class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    try:
        clothing_url = req.clothing_image_url
        if clothing_url.startswith("//"):
            clothing_url = "https:" + clothing_url

        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": req.person_image_url,
                "garm_img": clothing_url,
                "garment_des": req.category, 
                "category": "upper_body",
                "crop": False, "seed": 42, "steps": 30
            }
        )
        url = str(output[0]) if isinstance(output, list) else str(output)
        return {"result_image_url": url}
    except Exception as e: 
        return {"error": str(e)}

# --- WEBHOOKS RGPD ---
@app.post("/webhooks/customers/data_request")
def w1(): return {"ok": True}
@app.post("/webhooks/customers/redact")
def w2(): return {"ok": True}
@app.post("/webhooks/shop/redact")
def w3(): return {"ok": True}
