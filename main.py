import os
import shopify
import psycopg2
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 

# Correction automatique de l'URL Postgres
raw_db_url = os.getenv("DATABASE_URL")
DATABASE_URL = raw_db_url.replace("postgres://", "postgresql://") if raw_db_url else None

SCOPES = ['write_script_tags', 'read_products']
# VERSION API MISE À JOUR (CRUCIAL POUR DÉCEMBRE 2025)
API_VERSION = "2025-10"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

# Servir les fichiers statiques
app.mount("/static", StaticFiles(directory="."), name="static")

# --- SÉCURITÉ & IFRAME SHOPIFY ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "frame-ancestors https://admin.shopify.com https://*.myshopify.com;"
    return response

# --- GESTION BASE DE DONNÉES ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
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
        print("✅ Base de données connectée et initialisée.")
    except Exception as e:
        print(f"❌ Erreur critique DB: {e}")

init_db()

def get_shop_data(shop_url):
    try:
        clean_shop = shop_url.replace("https://", "").replace("http://", "").strip("/")
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT access_token, credits FROM shops WHERE shop_url = %s", (shop_url,))
        data = cur.fetchone()
        
        if not data:
            cur.execute("SELECT access_token, credits FROM shops WHERE shop_url = %s", (clean_shop,))
            data = cur.fetchone()

        cur.close()
        conn.close()
        return data
    except Exception as e:
        print(f"Erreur lecture DB pour {shop_url}: {e}")
        return None

def update_credits(shop_url, amount):
    try:
        clean_shop = shop_url.replace("https://", "").replace("http://", "").strip("/")
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("UPDATE shops SET credits = credits + %s WHERE shop_url = %s", (amount, clean_shop))
        
        if cur.rowcount == 0:
            cur.execute("UPDATE shops SET credits = credits + %s WHERE shop_url = %s", (amount, shop_url))
            
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Erreur update crédits: {e}")

# --- ROUTES ---

@app.get("/")
def index(shop: str = None):
    if not shop: 
        return HTMLResponse("<h1>Erreur</h1><p>Paramètre 'shop' manquant.</p>", status_code=400)
    
    data = get_shop_data(shop)
    if not data:
        return RedirectResponse(f"/login?shop={shop}")

    return FileResponse('index.html')

@app.get("/login")
def login(shop: str):
    if not shop: return "Shop manquant", 400
    
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    # MISE À JOUR VERSION API ICI
    permission_url = shopify.Session(shop.strip(), API_VERSION).create_permission_url(SCOPES, f"{HOST}/auth/callback")
    
    return HTMLResponse(content=f"<script>window.top.location.href='{permission_url}'</script>")

@app.get("/auth/callback")
def auth_callback(request: Request):
    params = dict(request.query_params)
    if 'shop' not in params: return "Erreur shop", 400
    shop = params['shop']
    
    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        # MISE À JOUR VERSION API ICI
        session = shopify.Session(shop, API_VERSION)
        access_token = session.request_token(params)
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO shops (shop_url, access_token, credits) 
            VALUES (%s, %s, 50)
            ON CONFLICT (shop_url) 
            DO UPDATE SET access_token = EXCLUDED.access_token;
        """, (shop, access_token))
        conn.commit()
        cur.close()
        conn.close()
        
        clean_shop_name = shop.replace('.myshopify.com', '')
        return RedirectResponse(f"https://admin.shopify.com/store/{clean_shop_name}/apps/{SHOPIFY_API_KEY}")
        
    except Exception as e:
        return f"Erreur install: {str(e)}", 500

# --- API ---

@app.get("/api/get-credits")
def get_credits_api(shop: str):
    data = get_shop_data(shop)
    return {"credits": data[1] if data else 0}

class BuyRequest(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    data = get_shop_data(req.shop)
    if not data: raise HTTPException(401, "Session expirée")
    token = data[0]
    
    if req.pack_id == 'pack_10': price, credits, name = 4.99, 10, "Pack 10 Crédits"
    elif req.pack_id == 'pack_30': price, credits, name = 9.99, 30, "Pack 30 Crédits"
    else: price, credits, name = 19.99, 100, "Pack 100 Crédits"

    try:
        # MISE À JOUR VERSION API ICI
        session = shopify.Session(req.shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        charge = shopify.ApplicationCharge.create({
            "name": name,
            "price": price,
            "return_url": f"{HOST}/billing/callback?shop={req.shop}&credits={credits}",
            "test": True
        })
        return {"confirmation_url": charge.confirmation_url}
    except Exception as e:
        print(f"Erreur paiement: {e}")
        raise HTTPException(500, f"Erreur Shopify: {str(e)}")

@app.get("/billing/callback")
def billing_callback(shop: str, credits: int, charge_id: str):
    clean_shop = shop.replace("https://", "").replace("http://", "").strip("/")
    data = get_shop_data(clean_shop) or get_shop_data(shop)
    if not data: return f"Erreur critique : Boutique introuvable.", 400

    token = data[0]

    try:
        # MISE À JOUR VERSION API ICI
        session = shopify.Session(clean_shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        charge = shopify.ApplicationCharge.find(charge_id)
        
        if charge.status in ['accepted', 'active']:
            if charge.status == 'accepted': charge.activate()
            update_credits(clean_shop, int(credits))
            
            shop_name = clean_shop.replace('.myshopify.com', '')
            return RedirectResponse(f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}")
        else:
            return f"Paiement refusé (Statut: {charge.status})", 400

    except Exception as e:
        return f"Erreur paiement: {str(e)}", 500

class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    data = get_shop_data(req.shop)
    if not data: raise HTTPException(401, "Shop non identifié")
    if data[1] < 1: raise HTTPException(402, "Crédits insuffisants")

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
        final_url = str(output[0]) if isinstance(output, list) else str(output)
        update_credits(req.shop, -1)
        return {"result_image_url": final_url, "credits_remaining": data[1] - 1}
        
    except Exception as e:
        raise HTTPException(500, f"Erreur IA: {str(e)}")
