import os
import io
import sqlite3
import shopify
import replicate
import binascii
from typing import Optional
from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

# --- 1. CONFIGURATION ---
# Ces infos viennent de ton tableau de bord Partenaire Shopify
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
# L'URL de ton serveur (ex: https://mon-app.onrender.com ou l'URL ngrok pour tester)
HOST_URL = os.getenv("HOST_URL") 
SCOPES = ["write_products", "read_products", "write_metaobjects", "read_metaobjects"]

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)

app = FastAPI()
templates = Jinja2Templates(directory=".")

# Initialisation DB au démarrage (plus besoin de script séparé)
def init_db():
    with sqlite3.connect("database.db") as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS shops (domain TEXT PRIMARY KEY, token TEXT NOT NULL)")

init_db()

# --- 2. FONCTIONS UTILES ---
def get_token_db(shop):
    with sqlite3.connect("database.db") as conn:
        cur = conn.cursor()
        cur.execute("SELECT token FROM shops WHERE domain = ?", (shop,))
        row = cur.fetchone()
        return row[0] if row else None

def save_token_db(shop, token):
    with sqlite3.connect("database.db") as conn:
        conn.execute("INSERT OR REPLACE INTO shops (domain, token) VALUES (?, ?)", (shop, token))

def clean_shop_url(url):
    """Nettoie l'url pour avoir juste 'boutique.myshopify.com'"""
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

# --- 3. ROUTES D'INSTALLATION (OAUTH) ---
# C'est ÇA qui manque pour vendre l'app

@app.get("/login")
def login(shop: str):
    """Première étape : Shopify nous envoie ici quand le client clique sur Installer"""
    shop = clean_shop_url(shop)
    if not shop:
        return "Paramètre 'shop' manquant", 400
    
    # On génère une URL d'autorisation unique
    state = binascii.b2a_hex(os.urandom(15)).decode("utf-8")
    redirect_uri = f"{HOST_URL}/auth/callback"
    permission_url = shopify.Session(shop.strip(), "2024-01").create_permission_url(SCOPES, redirect_uri, state)
    
    return RedirectResponse(permission_url)

@app.get("/auth/callback")
def auth_callback(request: Request):
    """Deuxième étape : Shopify revient ici après que le client a accepté"""
    params = request.query_params
    shop = params.get("shop")
    
    try:
        session = shopify.Session(shop, "2024-01")
        token = session.request_token(params) # On échange le code temporaire contre le vrai Token
        
        # SAUVEGARDE DU CLIENT (CRITIQUE POUR COMMERCIALISER)
        save_token_db(shop, token)
        
        # On redirige vers l'interface de l'app dans Shopify
        return RedirectResponse(f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
    
    except Exception as e:
        return f"Erreur d'installation : {str(e)}", 500


# --- 4. L'INTERFACE DE L'APP ---

@app.get("/")
async def index(request: Request):
    # Pour que l'app s'affiche DANS Shopify, il faut passer la clef API au frontend
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "api_key": SHOPIFY_API_KEY
    })

# --- 5. L'IA (MOTEUR) ---

@app.post("/api/generate")
async def generate(
    shop: str = Form(...), 
    person_image: UploadFile = File(...), 
    clothing_url: str = Form(...) 
):
    print(f"🚀 REÇU: Shop={shop}")
    
    shop = clean_shop_url(shop)
    token = get_token_db(shop) # On récupère le token de CE client spécifique

    if not token:
        return JSONResponse({"error": "App non installée. Veuillez relancer l'app via Shopify."}, status_code=403)

    try:
        # Configuration de la session Shopify pour ce client
        session = shopify.Session(shop, "2024-01", token)
        shopify.ShopifyResource.activate_session(session)

        # (Optionnel) Vérification des crédits ici...
        # ...

        # Appel Replicate
        person_bytes = await person_image.read()
        
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": io.BytesIO(person_bytes),
                "garm_img": clothing_url,
                "garment_des": "upper_body",
                "category": "upper_body",
                "crop": False,
                "seed": 42
            }
        )
        
        result_url = str(output[0]) if isinstance(output, list) else str(output)
        
        # (Optionnel) Débit des crédits ici...
        
        return {"result_image_url": result_url}

    except Exception as e:
        print(f"🔥 ERREUR: {str(e)}")
        shopify.ShopifyResource.clear_session()
        return JSONResponse({"error": str(e)}, status_code=500)
