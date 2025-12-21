import os
import shopify
import sqlite3
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
# L'URL publique de ton app (ex: https://ton-app.onrender.com)
HOST = os.getenv("HOST") 
SCOPES = ['write_script_tags', 'read_products']

# Configuration Replicate (Assure-toi que REPLICATE_API_TOKEN est dans tes variables d'env)
model_version = "fashn-ai/fashn-virtual-try-on:YOUR_MODEL_VERSION_HASH_HERE" 
# Note: Trouve le hash exact du modèle sur replicate.com si besoin, ou utilise replicate.run("fashn-ai/...")

app = FastAPI()

# Servir les fichiers statiques (CSS, JS, Images)
app.mount("/static", StaticFiles(directory="."), name="static")

# --- BASE DE DONNÉES (SQLite) ---
def init_db():
    conn = sqlite3.connect('shops.db')
    c = conn.cursor()
    # On crée une table pour stocker les infos des boutiques
    c.execute('''CREATE TABLE IF NOT EXISTS shops
                 (shop_url TEXT PRIMARY KEY, access_token TEXT, credits INTEGER)''')
    conn.commit()
    conn.close()

init_db()

def get_shop_data(shop_url):
    conn = sqlite3.connect('shops.db')
    c = conn.cursor()
    c.execute("SELECT access_token, credits FROM shops WHERE shop_url=?", (shop_url,))
    data = c.fetchone()
    conn.close()
    return data

def update_credits(shop_url, amount):
    conn = sqlite3.connect('shops.db')
    c = conn.cursor()
    # On ajoute (ou retire si amount est négatif) des crédits
    c.execute("UPDATE shops SET credits = credits + ? WHERE shop_url=?", (amount, shop_url))
    conn.commit()
    conn.close()

# --- ROUTES SHOPIFY (AUTH) ---

@app.get("/login")
def login(shop: str):
    if not shop:
        return "Paramètre shop manquant", 400
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    permission_url = shopify.Session(shop.strip(), "2024-01").create_permission_url(SCOPES, f"{HOST}/auth/callback")
    return RedirectResponse(permission_url)

@app.get("/auth/callback")
def auth_callback(shop: str, code: str):
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(shop, "2024-01")
    try:
        access_token = session.request_token(dict(code=code))
        
        # Sauvegarde en DB
        conn = sqlite3.connect('shops.db')
        c = conn.cursor()
        # On insère le shop s'il n'existe pas, avec 5 crédits offerts
        c.execute("INSERT OR IGNORE INTO shops (shop_url, access_token, credits) VALUES (?, ?, ?)", (shop, access_token, 5))
        # Si le shop existe déjà, on met juste à jour le token
        c.execute("UPDATE shops SET access_token=? WHERE shop_url=?", (access_token, shop))
        conn.commit()
        conn.close()
        
        # Redirection vers l'interface de l'app
        return RedirectResponse(f"/?shop={shop}")
    except Exception as e:
        return f"Erreur d'installation : {str(e)}", 500

# --- ROUTE PRINCIPALE (UI) ---
@app.get("/")
def index(shop: str = None):
    # On sert le fichier HTML
    return FileResponse('index.html')

@app.get("/api/get-credits")
def get_credits_api(shop: str):
    data = get_shop_data(shop)
    if not data:
        return {"credits": 0}
    return {"credits": data[1]}

# --- FACTURATION (BILLING API) ---
class BuyRequest(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    data = get_shop_data(req.shop)
    if not data:
        raise HTTPException(401, "Shop introuvable")
    
    token = data[0]
    
    # Définir le prix selon le pack
    price = 0.0
    credits = 0
    name = ""
    
    if req.pack_id == 'pack_10':
        price = 4.99
        credits = 10
        name = "Pack Découverte (10 Crédits)"
    elif req.pack_id == 'pack_30':
        price = 9.99
        credits = 30
        name = "Pack Créateur (30 Crédits)"
    elif req.pack_id == 'pack_100':
        price = 19.99
        credits = 100
        name = "Pack Agence (100 Crédits)"

    # Créer la session Shopify pour faire l'appel API
    session = shopify.Session(req.shop, "2024-01", token)
    shopify.ShopifyResource.activate_session(session)
    
    # Créer le "ApplicationCharge" (Paiement unique)
    charge = shopify.ApplicationCharge.create({
        "name": name,
        "price": price,
        "return_url": f"{HOST}/billing/callback?shop={req.shop}&credits={credits}",
        "test": True # ⚠️ METTRE FALSE EN PROD
    })
    
    return {"confirmation_url": charge.confirmation_url}

@app.get("/billing/callback")
def billing_callback(shop: str, credits: int, charge_id: str):
    data = get_shop_data(shop)
    token = data[0]
    
    session = shopify.Session(shop, "2024-01", token)
    shopify.ShopifyResource.activate_session(session)
    
    # On doit "activer" le paiement pour toucher l'argent
    charge = shopify.ApplicationCharge.find(charge_id)
    if charge.status == 'accepted':
        charge.activate()
        # On ajoute les crédits en DB
        update_credits(shop, int(credits))
        return RedirectResponse(f"/?shop={shop}&success=true&added={credits}")
    else:
        return RedirectResponse(f"/?shop={shop}&error=payment_declined")

# --- GENERATION IA ---
class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    # 1. Vérification des crédits
    data = get_shop_data(req.shop)
    if not data or data[1] < 1:
        raise HTTPException(402, "Crédits insuffisants")

    # 2. Appel Replicate (Fashn.ai)
    try:
        # Note: Assure-toi que "fashn-ai/fashn-virtual-try-on" est le bon ID modèle
        output = replicate.run(
            "fashn-ai/fashn-virtual-try-on:5664539868770267755866750035075076632463673322765360632557766543",
            input={
                "model_image": req.person_image_url,
                "garment_image": req.clothing_image_url,
                "category": req.category,
                "mode": "performance" # ou "quality"
            }
        )
        
        # 3. Si succès, on débit 1 crédit
        update_credits(req.shop, -1)
        
        # Replicate renvoie souvent une liste ou une URL string
        image_url = output[0] if isinstance(output, list) else output
        
        return {
            "result_image_url": image_url,
            "credits_remaining": data[1] - 1
        }
        
    except Exception as e:
        print(f"Erreur Replicate: {e}")
        raise HTTPException(500, "Erreur de génération IA")