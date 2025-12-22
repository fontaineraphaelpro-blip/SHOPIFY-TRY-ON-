import os
import shopify
import psycopg2
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 
DATABASE_URL = os.getenv("DATABASE_URL") # Nouvelle variable Render
SCOPES = ['write_script_tags', 'read_products']

# Ton modèle IDM-VTON
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

# Servir les fichiers statiques
app.mount("/static", StaticFiles(directory="."), name="static")

# --- GESTION BASE DE DONNÉES (POSTGRESQL) ---
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Création de la table si elle n'existe pas
        cur.execute('''
            CREATE TABLE IF NOT EXISTS shops (
                shop_url VARCHAR(255) PRIMARY KEY,
                access_token TEXT,
                credits INTEGER DEFAULT 50
            );
        ''')
        conn.commit()
        cur.close()
        conn.close()
        print("Base de données initialisée avec succès.")
    except Exception as e:
        print(f"Erreur DB Init: {e}")

# On lance l'initialisation au démarrage
init_db()

def get_shop_data(shop_url):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT access_token, credits FROM shops WHERE shop_url = %s", (shop_url,))
    data = cur.fetchone()
    cur.close()
    conn.close()
    return data

def update_credits(shop_url, amount):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE shops SET credits = credits + %s WHERE shop_url = %s", (amount, shop_url))
    conn.commit()
    cur.close()
    conn.close()

# --- ROUTES SHOPIFY ---

@app.get("/login")
def login(shop: str):
    if not shop: return "Shop manquant", 400
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    permission_url = shopify.Session(shop.strip(), "2024-01").create_permission_url(SCOPES, f"{HOST}/auth/callback")
    return RedirectResponse(permission_url)

@app.get("/auth/callback")
def auth_callback(shop: str, code: str):
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(shop, "2024-01")
    try:
        access_token = session.request_token(dict(code=code))
        
        conn = get_db_connection()
        cur = conn.cursor()
        # "Upsert" : Insère ou met à jour si existe déjà
        cur.execute("""
            INSERT INTO shops (shop_url, access_token, credits) 
            VALUES (%s, %s, 50)
            ON CONFLICT (shop_url) 
            DO UPDATE SET access_token = EXCLUDED.access_token;
        """, (shop, access_token))
        conn.commit()
        cur.close()
        conn.close()
        
        return RedirectResponse(f"/?shop={shop}")
    except Exception as e:
        return f"Erreur installation: {e}", 500

# --- UI & API ---

@app.get("/")
def index(shop: str = None):
    return FileResponse('index.html')

@app.get("/api/get-credits")
def get_credits_api(shop: str):
    data = get_shop_data(shop)
    # Si pas de data, on renvoie 0 (mais ça ne devrait plus arriver avec Postgres !)
    if not data: return {"credits": 0}
    return {"credits": data[1]}

# --- PAIEMENT ---
class BuyRequest(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    data = get_shop_data(req.shop)
    if not data: raise HTTPException(401, "Shop introuvable en base.")
    
    token = data[0]
    
    if req.pack_id == 'pack_10': price, credits, name = 4.99, 10, "Pack 10 Crédits"
    elif req.pack_id == 'pack_30': price, credits, name = 9.99, 30, "Pack 30 Crédits"
    else: price, credits, name = 19.99, 100, "Pack 100 Crédits"

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
    if not data: return RedirectResponse(f"/?shop={shop}&error=db_error")

    token = data[0]
    session = shopify.Session(shop, "2024-01", token)
    shopify.ShopifyResource.activate_session(session)
    
    charge = shopify.ApplicationCharge.find(charge_id)
    if charge.status == 'accepted':
        charge.activate()
        update_credits(shop, int(credits))
        return RedirectResponse(f"/?shop={shop}&success=true")
    else:
        return RedirectResponse(f"/?shop={shop}&error=declined")

# --- GENERATION IA ---
class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    print(f"Demande IA pour : {req.shop}")
    
    # 1. Vérification des Crédits (REMISE EN PLACE !)
    data = get_shop_data(req.shop)
    if not data:
        raise HTTPException(401, "Boutique non trouvée. Veuillez réinstaller l'app.")
    
    credits_dispo = data[1]
    
    # Sécurité : On bloque si pas assez de crédits
    if credits_dispo < 1:
        raise HTTPException(402, "Crédits insuffisants. Rechargez votre compte.")

    try:
        category_map = {"tops": "upper_body", "bottoms": "lower_body", "one-pieces": "dresses"}
        
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": req.person_image_url,
                "garm_img": req.clothing_image_url,
                "garment_des": req.category, 
                "category": category_map.get(req.category, "upper_body"),
                "crop": False, "seed": 42, "steps": 30
            }
        )
        
        # 2. Conversion sécurisée de la réponse
        final_url = str(output[0]) if isinstance(output, list) else str(output)
        
        # 3. Débit du crédit (IMPORTANT)
        update_credits(req.shop, -1)
        
        return {
            "result_image_url": final_url,
            "credits_remaining": credits_dispo - 1
        }
        
    except Exception as e:
        print(f"Erreur IA: {e}")
        raise HTTPException(500, f"Erreur génération: {str(e)}")
