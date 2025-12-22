import os
import shopify
import psycopg2
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import replicate

# --- CONFIG ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 
raw_db_url = os.getenv("DATABASE_URL")
DATABASE_URL = raw_db_url.replace("postgres://", "postgresql://") if raw_db_url else None
SCOPES = ['write_script_tags', 'read_products']
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()
app.mount("/static", StaticFiles(directory="."), name="static")

# --- MIDDLEWARE POUR AUTORISER L'IFRAME SHOPIFY ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # C'est LA ligne qui permet à l'app de s'afficher DANS Shopify admin
    response.headers["Content-Security-Policy"] = "frame-ancestors https://admin.shopify.com https://*.myshopify.com;"
    return response

# --- DB ---
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
        print("✅ DB OK")
    except Exception as e:
        print(f"❌ Erreur DB: {e}")

init_db()

def get_shop_data(shop_url):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT access_token, credits FROM shops WHERE shop_url = %s", (shop_url,))
        data = cur.fetchone()
        conn.close()
        return data
    except:
        return None

def update_credits(shop_url, amount):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE shops SET credits = credits + %s WHERE shop_url = %s", (amount, shop_url))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erreur update crédits: {e}")

# --- ROUTES ---

@app.get("/")
def index(shop: str = None):
    if not shop: return "Erreur: Paramètre shop manquant", 400
    
    # Auto-repair : Si le shop n'est pas en base, on lance l'install
    data = get_shop_data(shop)
    if not data:
        print(f"⚠️ Shop inconnu {shop}, redirection install...")
        return RedirectResponse(f"/login?shop={shop}")

    return FileResponse('index.html')

@app.get("/login")
def login(shop: str):
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    permission_url = shopify.Session(shop.strip(), "2024-01").create_permission_url(SCOPES, f"{HOST}/auth/callback")
    
    # Sortie de l'iframe pour l'auth (Sécurité Shopify)
    return HTMLResponse(content=f"<script>window.top.location.href='{permission_url}'</script>")

@app.get("/auth/callback")
def auth_callback(shop: str, code: str):
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(shop, "2024-01")
    try:
        token = session.request_token(dict(code=code))
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO shops (shop_url, access_token, credits) 
            VALUES (%s, %s, 50)
            ON CONFLICT (shop_url) DO UPDATE SET access_token = EXCLUDED.access_token;
        """, (shop, token))
        conn.commit()
        conn.close()
        
        # Retour à l'admin Shopify
        return RedirectResponse(f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
    except Exception as e:
        return f"Erreur install: {e}", 500

# --- API ---
class BuyRequest(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    data = get_shop_data(req.shop)
    if not data: raise HTTPException(401, "Shop introuvable")
    
    token = data[0]
    if req.pack_id == 'pack_10': price, credits, name = 4.99, 10, "Pack 10"
    elif req.pack_id == 'pack_30': price, credits, name = 9.99, 30, "Pack 30"
    else: price, credits, name = 19.99, 100, "Pack 100"

    session = shopify.Session(req.shop, "2024-01", token)
    shopify.ShopifyResource.activate_session(session)
    charge = shopify.ApplicationCharge.create({
        "name": name, "price": price, "test": True,
        "return_url": f"{HOST}/billing/callback?shop={req.shop}&credits={credits}"
    })
    return {"confirmation_url": charge.confirmation_url}

@app.get("/billing/callback")
def billing_callback(shop: str, credits: int, charge_id: str):
    session = shopify.Session(shop, "2024-01", get_shop_data(shop)[0])
    shopify.ShopifyResource.activate_session(session)
    charge = shopify.ApplicationCharge.find(charge_id)
    if charge.status == 'accepted':
        charge.activate()
        update_credits(shop, int(credits))
        return RedirectResponse(f"/?shop={shop}")
    return RedirectResponse(f"/?shop={shop}&error=failed")

@app.get("/api/get-credits")
def get_credits_api(shop: str):
    data = get_shop_data(shop)
    return {"credits": data[1] if data else 0}

class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    data = get_shop_data(req.shop)
    if not data: raise HTTPException(401, "Shop introuvable")
    if data[1] < 1: raise HTTPException(402, "Pas assez de crédits")

    category_map = {"tops": "upper_body", "bottoms": "lower_body", "one-pieces": "dresses"}
    output = replicate.run(MODEL_ID, input={
        "human_img": req.person_image_url, "garm_img": req.clothing_image_url,
        "garment_des": req.category, "category": category_map.get(req.category, "upper_body"),
        "crop": False, "seed": 42, "steps": 30
    })
    
    update_credits(req.shop, -1)
    return {"result_image_url": str(output), "credits_remaining": data[1] - 1}
