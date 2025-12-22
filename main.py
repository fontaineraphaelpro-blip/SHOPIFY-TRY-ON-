import os
import shopify
import requests
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 
SCOPES = ['read_products', 'write_products']
API_VERSION = "2025-01" 
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

# --- CORS (Pour que Shopify puisse afficher l'app) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- FICHIERS STATIQUES (C'est ici la modif importante) ---
# On dit : "Quand on demande /static, cherche dans le dossier actuel (.)"
app.mount("/static", StaticFiles(directory="."), name="static")

# --- ROUTES ---

@app.get("/")
def index():
    # On sert simplement le fichier HTML
    return FileResponse('index.html')

@app.get("/login")
def login(shop: str):
    # Redirection vers l'auth Shopify
    auth_url = f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={','.join(SCOPES)}&redirect_uri={HOST}/auth/callback"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(shop: str, code: str):
    # Validation du token (simplifié)
    url = f"https://{shop}/admin/oauth/access_token"
    payload = {"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code}
    requests.post(url, json=payload) 
    # Redirection vers l'admin Shopify
    return RedirectResponse(f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")

# --- API ---

class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    try:
        cat_map = {"tops": "upper_body", "bottoms": "lower_body", "one-pieces": "dresses"}
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": req.person_image_url,
                "garm_img": req.clothing_image_url,
                "garment_des": req.category, 
                "category": cat_map.get(req.category, "upper_body"),
                "crop": False, "seed": 42, "steps": 30
            }
        )
        final_url = str(output[0]) if isinstance(output, list) else str(output)
        return {"result_image_url": final_url}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/get-credits")
def get_credits(shop: str):
    # Faux crédits pour l'affichage admin
    return {"credits": 120}

@app.post("/api/buy-credits")
def buy_credits():
    return {"message": "Fonctionnalité désactivée pour ce test"}
