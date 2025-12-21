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
HOST = os.getenv("HOST") 
SCOPES = ['write_script_tags', 'read_products']

# Ton modèle IDM-VTON
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

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
        # On insère le shop avec 50 crédits offerts pour le test
        c.execute("INSERT OR IGNORE INTO shops (shop_url, access_token, credits) VALUES (?, ?, ?)", (shop, access_token, 50))
        # Mise à jour du token si le shop existe déjà
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
    return FileResponse('index.html')

@app.get("/api/get-credits")
def get_credits_api(shop: str):
    data = get_shop_data(shop)
    if not data:
        # Si la DB est vide (Render restart), on renvoie 0 mais l'IA marchera quand même
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
        # Si la DB est vide, on force une erreur explicite
        raise HTTPException(401, "Session expirée (Render). Veuillez réinstaller l'app pour tester le paiement.")
    
    token = data[0]
    
    # Prix et Crédits
    if req.pack_id == 'pack_10':
        price, credits, name = 4.99, 10, "Pack Découverte (10 Crédits)"
    elif req.pack_id == 'pack_30':
        price, credits, name = 9.99, 30, "Pack Créateur (30 Crédits)"
    else:
        price, credits, name = 19.99, 100, "Pack Agence (100 Crédits)"

    session = shopify.Session(req.shop, "2024-01", token)
    shopify.ShopifyResource.activate_session(session)
    
    charge = shopify.ApplicationCharge.create({
        "name": name,
        "price": price,
        "return_url": f"{HOST}/billing/callback?shop={req.shop}&credits={credits}",
        "test": True 
    })
    
    return {"confirmation_url": charge.confirmation_url}

@app.get("/billing/callback")
def billing_callback(shop: str, credits: int, charge_id: str):
    data = get_shop_data(shop)
    if not data:
         return RedirectResponse(f"/?shop={shop}&error=session_expired")

    token = data[0]
    session = shopify.Session(shop, "2024-01", token)
    shopify.ShopifyResource.activate_session(session)
    
    charge = shopify.ApplicationCharge.find(charge_id)
    if charge.status == 'accepted':
        charge.activate()
        update_credits(shop, int(credits))
        return RedirectResponse(f"/?shop={shop}&success=true&added={credits}")
    else:
        return RedirectResponse(f"/?shop={shop}&error=payment_declined")

# --- GENERATION IA (MODE "OPEN BAR" ACTIVÉ) ---
class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    # NOTE: J'ai commenté la vérification des crédits pour que tu puisses tester
    # même si Render a effacé la base de données.
    
    # data = get_shop_data(req.shop)
    # if not data or data[1] < 1:
    #     raise HTTPException(402, "Crédits insuffisants")

    try:
        # Mapping des catégories pour IDM-VTON
        category_map = {
            "tops": "upper_body",
            "bottoms": "lower_body", 
            "one-pieces": "dresses"
        }
        
        print("Lancement génération IDM-VTON...")
        
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": req.person_image_url,
                "garm_img": req.clothing_image_url,
                "garment_des": req.category, 
                "category": category_map.get(req.category, "upper_body"),
                "crop": False,
                "seed": 42,
                "steps": 30
            }
        )
        
        # NOTE: On ne déduit pas de crédits pour le moment
        # update_credits(req.shop, -1)
        
        return {
            "result_image_url": output,
            "credits_remaining": 999 # Nombre fictif pour l'UI
        }
        
    except Exception as e:
        print(f"Erreur Replicate: {e}")
        raise HTTPException(500, f"Erreur IA: {str(e)}")
