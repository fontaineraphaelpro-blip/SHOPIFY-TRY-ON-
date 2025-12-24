import os
import hmac
import hashlib
import base64
import json
import httpx
import replicate
from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
API_VERSION = "2024-01"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Simulation de stockage des tokens (À remplacer par une DB en prod réelle pour les tokens)
# Mais les CRÉDITS sont 100% sur Shopify Metafields
shop_sessions = {} 

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- UTILS SHOPIFY GRAPHQL ---

async def query_shopify(shop, token, query, variables=None):
    url = f"https://{shop}/admin/api/{API_VERSION}/graphql.json"
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={"query": query, "variables": variables}, headers=headers)
        return resp.json()

async def get_shop_data(shop, token):
    """Récupère l'ID du shop et les crédits depuis les Metafields"""
    query = """
    {
      shop {
        id
        metafield(namespace: "stylelab", key: "credits") {
          value
        }
      }
    }
    """
    res = await query_shopify(shop, token, query)
    shop_id = res['data']['shop']['id']
    meta = res['data']['shop']['metafield']
    credits = int(meta['value']) if meta else 10 # 10 par défaut
    return shop_id, credits

async def set_shop_credits(shop, token, shop_id, amount):
    """Enregistre les crédits dans les Metafields Shopify"""
    mutation = """
    mutation metafieldsSet($metafields: [MetafieldsSetInput!]!) {
      metafieldsSet(metafields: $metafields) {
        metafields { key value }
        userErrors { message }
      }
    }
    """
    variables = {
        "metafields": [{
            "ownerId": shop_id,
            "namespace": "stylelab",
            "key": "credits",
            "type": "number_integer",
            "value": str(amount)
        }]
    }
    await query_shopify(shop, token, mutation, variables)

# --- ROUTES ---

@app.get("/")
async def index(shop: str = None):
    return FileResponse('index.html')

@app.get("/login")
def login(shop: str):
    auth_url = f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope=read_products,write_products,read_metafields,write_metafields&redirect_uri={HOST}/auth/callback"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
async def auth_callback(shop: str, code: str):
    url = f"https://{shop}/admin/oauth/access_token"
    data = {"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code}
    async with httpx.AsyncClient() as client:
        res = await client.post(url, json=data)
        token = res.json().get('access_token')
    
    shop_sessions[shop] = token
    
    # Initialisation des crédits sur Shopify à l'installation
    shop_id, credits = await get_shop_data(shop, token)
    await set_shop_credits(shop, token, shop_id, credits)

    return RedirectResponse(f"https://{shop}/admin/apps/{SHOPIFY_API_KEY}")

@app.get("/api/get-credits")
async def get_credits(shop: str):
    token = shop_sessions.get(shop)
    if not token: return JSONResponse({"credits": 0, "error": "No session"}, status_code=401)
    _, credits = await get_shop_data(shop, token)
    return {"credits": credits}

@app.post("/api/generate")
async def generate(
    shop: str = Form(...),
    person_image: UploadFile = File(...),
    clothing_url: str = Form(...)
):
    token = shop_sessions.get(shop)
    if not token: raise HTTPException(status_code=401)

    # 1. Check Credits sur Shopify
    shop_id, current_credits = await get_shop_data(shop, token)
    if current_credits < 1:
        return JSONResponse({"error": "Crédits insuffisants"}, status_code=402)

    try:
        # 2. IA Replicate
        img_bytes = await person_image.read()
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": img_bytes,
                "garm_img": clothing_url,
                "garment_des": "upper_body"
            }
        )

        # 3. Débit Crédit sur Shopify
        new_total = current_credits - 1
        await set_shop_credits(shop, token, shop_id, new_total)

        return {"result_image_url": output, "new_credits": new_total}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
