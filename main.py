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

# Ton modèle IDM-VTON spécifique
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

app.mount("/static", StaticFiles(directory="."), name="static")

# --- BASE DE DONNÉES (SQLite) ---
def init_db():
    conn = sqlite3.connect('shops.db')
    c = conn.cursor()
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
    c.execute("UPDATE shops SET credits = credits + ? WHERE shop_url=?", (amount, shop_url))
    conn.commit()
    conn.close()

# --- ROUTES SHOPIFY (AUTH) ---
@app.get("/login")
def login(shop: str):
    if not shop: return "Paramètre shop manquant", 400
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    permission_url = shopify.Session(shop.strip(), "2024-01").create_permission_url(SCOPES, f"{HOST}/auth/callback")
    return RedirectResponse(permission_url)

@app.get("/auth/callback")
def auth_callback(shop: str, code: str):
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(shop, "2024-01")
    try:
        access_token = session.request_token(dict(code=code))
        conn = sqlite3.connect('shops.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO shops (shop_url, access_token, credits) VALUES (?, ?, ?)", (shop, access_token, 5))
        c.execute("UPDATE shops SET access_token=? WHERE shop_url=?", (access_token, shop))
        conn.commit()
        conn.close()
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
    if not data: return {"credits": 0}
    return {"credits": data[1]}

# --- FACTURATION ---
class BuyRequest(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    data = get_shop_data(req.shop)
    if not data: raise HTTPException(401, "Shop introuvable")
    
    price = 4.99 if req.pack_id == 'pack_10' else 9.99 if req.pack_id == 'pack_30' else 19.99
    credits = 10 if req.pack_id == 'pack_10' else 30 if req.pack_id == 'pack_30' else 100
    
    session = shopify.Session(req.shop, "2024-01", data[0])
    shopify.ShopifyResource.activate_session(session)
    
    charge = shopify.ApplicationCharge.create({
        "name": f"Pack {credits} Crédits",
        "price": price,
        "return_url": f"{HOST}/billing/callback?shop={req.shop}&credits={credits}",
        "test": True
    })
    return {"confirmation_url": charge.confirmation_url}

@app.get("/billing/callback")
def billing_callback(shop: str, credits: int, charge_id: str):
    data = get_shop_data(shop)
    session = shopify.Session(shop, "2024-01", data[0])
    shopify.ShopifyResource.activate_session(session)
    charge = shopify.ApplicationCharge.find(charge_id)
    if charge.status == 'accepted':
        charge.activate()
        update_credits(shop, int(credits))
        return RedirectResponse(f"/?shop={shop}&success=true")
    else:
        return RedirectResponse(f"/?shop={shop}&error=payment_declined")

# --- GENERATION IA (MODIFIÉ POUR IDM-VTON) ---
class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    data = get_shop_data(req.shop)
    if not data or data[1] < 1: raise HTTPException(402, "Crédits insuffisants")

    try:
        # Adaptation des paramètres pour IDM-VTON
        # Il attend: human_img, garm_img, garment_des
        
        # On mappe tes catégories vers ce que IDM-VTON comprend le mieux
        category_map = {
            "tops": "upper_body",
            "bottoms": "lower_body", 
            "one-pieces": "dresses"
        }
        
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": req.person_image_url,
                "garm_img": req.clothing_image_url,
                "garment_des": req.category, # IDM-VTON utilise la description pour aider
                "category": category_map.get(req.category, "upper_body"),
                "crop": False, # Important pour garder toute l'image
                "seed": 42,
                "steps": 30
            }
        )
        
        update_credits(req.shop, -1)
        
        # IDM-VTON renvoie souvent l'image directement
        return {
            "result_image_url": output,
            "credits_remaining": data[1] - 1
        }
        
    except Exception as e:
        print(f"Erreur Replicate: {e}")
        raise HTTPException(500, f"Erreur IA: {str(e)}")
