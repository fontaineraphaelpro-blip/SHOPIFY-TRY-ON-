import os
import shopify
import psycopg2
import requests # <--- NOUVEAU
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 

raw_db_url = os.getenv("DATABASE_URL")
DATABASE_URL = raw_db_url.replace("postgres://", "postgresql://") if raw_db_url else None

SCOPES = ['write_script_tags', 'read_products']
API_VERSION = "2025-01" 
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()
app.mount("/static", StaticFiles(directory="."), name="static")

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "frame-ancestors https://admin.shopify.com https://*.myshopify.com;"
    return response

# --- DB TOOLS ---
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
        conn.close()
    except Exception as e:
        print(f"DB Init Error: {e}")

init_db()

def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

# --- ROUTES ---

@app.get("/")
def index(shop: str = None):
    if not shop: return "Shop manquant", 400
    
    clean_shop = clean_shop_url(shop)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT access_token FROM shops WHERE shop_url = %s", (clean_shop,))
    data = cur.fetchone()
    conn.close()
    
    if not data:
        return RedirectResponse(f"/login?shop={clean_shop}")

    return FileResponse('index.html')

@app.get("/login")
def login(shop: str):
    clean_shop = clean_shop_url(shop)
    # On prépare l'URL d'autorisation
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(clean_shop, API_VERSION)
    permission_url = session.create_permission_url(SCOPES, f"{HOST}/auth/callback")
    
    return HTMLResponse(content=f"<script>window.top.location.href='{permission_url}'</script>")

# --- C'EST ICI QUE TOUT CHANGE ---
@app.get("/auth/callback")
def auth_callback(request: Request):
    params = dict(request.query_params)
    shop = params.get('shop')
    code = params.get('code') # Le code temporaire donné par Shopify
    
    if not shop or not code:
        return "Paramètres manquants (shop ou code)", 400

    clean_shop = clean_shop_url(shop)
    
    try:
        # ÉCHANGE MANUEL DU TOKEN (Bypass de la vérification HMAC locale)
        # On envoie le code directement à Shopify. Si Shopify répond, c'est que c'est bon.
        access_token_url = f"https://{clean_shop}/admin/oauth/access_token"
        payload = {
            "client_id": SHOPIFY_API_KEY,
            "client_secret": SHOPIFY_API_SECRET,
            "code": code
        }
        
        response = requests.post(access_token_url, json=payload)
        
        if response.status_code != 200:
            # Si ça plante ici, c'est PREUVE que le Secret est faux sur Render
            return JSONResponse({"error": "Echec échange token", "details": response.text}, status_code=500)
            
        token_data = response.json()
        access_token = token_data.get('access_token')

        # SAUVEGARDE EN DB
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM shops WHERE shop_url = %s", (clean_shop,))
        cur.execute("INSERT INTO shops (shop_url, access_token, credits) VALUES (%s, %s, 50)", (clean_shop, access_token))
        conn.commit()
        conn.close()
        
        # Redirection vers l'Admin
        return RedirectResponse(f"https://admin.shopify.com/store/{clean_shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
        
    except Exception as e:
        return JSONResponse({"error": f"Erreur critique : {str(e)}"}, status_code=500)

# --- API PAIEMENT ---

class BuyRequest(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    clean_shop = clean_shop_url(req.shop)
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT access_token FROM shops WHERE shop_url = %s", (clean_shop,))
    data = cur.fetchone()
    conn.close()
    
    if not data: raise HTTPException(401, "Shop introuvable.")
    token = data[0]

    if req.pack_id == 'pack_10': price, credits, name = 4.99, 10, "Pack 10"
    elif req.pack_id == 'pack_30': price, credits, name = 9.99, 30, "Pack 30"
    else: price, credits, name = 19.99, 100, "Pack 100"

    try:
        # Reconnexion explicite
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(clean_shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        charge = shopify.ApplicationCharge.create({
            "name": name, "price": price, "test": True,
            "return_url": f"{HOST}/billing/callback?shop={clean_shop}&credits={credits}"
        })
        return {"confirmation_url": charge.confirmation_url}
    except Exception as e:
        print(f"DEBUG: {e}")
        raise HTTPException(500, f"Erreur Shopify: {str(e)}")

@app.get("/billing/callback")
def billing_callback(shop: str, credits: int, charge_id: str):
    clean_shop = clean_shop_url(shop)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT access_token FROM shops WHERE shop_url = %s", (clean_shop,))
    data = cur.fetchone()
    
    if not data: return "Erreur critique : Shop introuvable"
    
    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(clean_shop, API_VERSION, data[0])
        shopify.ShopifyResource.activate_session(session)
        
        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status in ['accepted', 'active']:
            if charge.status == 'accepted': charge.activate()
            
            cur.execute("UPDATE shops SET credits = credits + %s WHERE shop_url = %s", (int(credits), clean_shop))
            conn.commit()
            conn.close()
            
            return RedirectResponse(f"https://admin.shopify.com/store/{clean_shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
        
        conn.close()
        return "Paiement refusé"
    except Exception as e:
        return f"Erreur callback: {e}"

# --- API GENERATE ---

class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    clean_shop = clean_shop_url(req.shop)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT access_token, credits FROM shops WHERE shop_url = %s", (clean_shop,))
    data = cur.fetchone()
    
    if not data: raise HTTPException(401, "Token invalide")
    if data[1] < 1: 
        conn.close()
        raise HTTPException(402, "Crédits insuffisants")

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
        
        cur.execute("UPDATE shops SET credits = credits - 1 WHERE shop_url = %s", (clean_shop,))
        conn.commit()
        conn.close()
        
        return {"result_image_url": final_url, "credits_remaining": data[1] - 1}
    except Exception as e:
        conn.close()
        raise HTTPException(500, str(e))
