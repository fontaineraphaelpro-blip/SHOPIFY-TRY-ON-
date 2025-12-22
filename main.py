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

# Correction automatique de l'URL Postgres pour Python (Render donne postgres:// mais on veut postgresql://)
raw_db_url = os.getenv("DATABASE_URL")
DATABASE_URL = raw_db_url.replace("postgres://", "postgresql://") if raw_db_url else None

SCOPES = ['write_script_tags', 'read_products']
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

# Servir les fichiers statiques (CSS, JS, Images)
app.mount("/static", StaticFiles(directory="."), name="static")

# --- SÉCURITÉ & IFRAME SHOPIFY ---
# Ce middleware permet à ton app de s'afficher DANS l'admin Shopify sans être bloquée
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "frame-ancestors https://admin.shopify.com https://*.myshopify.com;"
    return response

# --- GESTION BASE DE DONNÉES (PostgreSQL) ---
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

# Lancement de la DB au démarrage
init_db()

def get_shop_data(shop_url):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT access_token, credits FROM shops WHERE shop_url = %s", (shop_url,))
        data = cur.fetchone()
        cur.close()
        conn.close()
        return data
    except Exception as e:
        print(f"Erreur lecture DB pour {shop_url}: {e}")
        return None

def update_credits(shop_url, amount):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE shops SET credits = credits + %s WHERE shop_url = %s", (amount, shop_url))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Erreur mise à jour crédits: {e}")

# --- ROUTES D'INSTALLATION & AUTHENTIFICATION ---

@app.get("/")
def index(shop: str = None):
    if not shop: 
        return HTMLResponse("<h1>Erreur</h1><p>Paramètre 'shop' manquant. Ouvrez l'app depuis Shopify.</p>", status_code=400)
    
    # AUTO-RÉPARATION : Si le shop n'est pas dans la base, on lance l'installation
    data = get_shop_data(shop)
    if not data:
        print(f"⚠️ Shop inconnu ({shop}). Redirection vers l'installation...")
        return RedirectResponse(f"/login?shop={shop}")

    return FileResponse('index.html')

@app.get("/login")
def login(shop: str):
    if not shop: return "Shop manquant", 400
    
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    permission_url = shopify.Session(shop.strip(), "2024-01").create_permission_url(SCOPES, f"{HOST}/auth/callback")
    
    # On force la sortie de l'iframe pour aller sur la page de login Shopify (Sécurité obligatoire)
    return HTMLResponse(content=f"<script>window.top.location.href='{permission_url}'</script>")

@app.get("/auth/callback")
def auth_callback(request: Request):
    # --- FIX CRITIQUE HMAC ---
    # On récupère TOUS les paramètres de l'URL (hmac, shop, timestamp, code...)
    params = dict(request.query_params)
    
    if 'shop' not in params:
        return "Erreur : Paramètre shop manquant", 400
    
    shop = params['shop']
    
    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, "2024-01")
        
        # On passe TOUS les paramètres pour que Shopify valide la signature de sécurité (HMAC)
        access_token = session.request_token(params)
        
        # Enregistrement en Base de Données
        conn = get_db_connection()
        cur = conn.cursor()
        # Upsert (Insérer ou Mettre à jour)
        cur.execute("""
            INSERT INTO shops (shop_url, access_token, credits) 
            VALUES (%s, %s, 50)
            ON CONFLICT (shop_url) 
            DO UPDATE SET access_token = EXCLUDED.access_token;
        """, (shop, access_token))
        conn.commit()
        cur.close()
        conn.close()
        
        # Redirection vers l'admin Shopify
        clean_shop_name = shop.replace('.myshopify.com', '')
        admin_url = f"https://admin.shopify.com/store/{clean_shop_name}/apps/{SHOPIFY_API_KEY}"
        return RedirectResponse(admin_url)
        
    except Exception as e:
        print(f"❌ ERREUR INSTALLATION: {str(e)}")
        return f"Erreur lors de l'installation : {str(e)}", 500

# --- API (PAIEMENT & GÉNÉRATION) ---

@app.get("/api/get-credits")
def get_credits_api(shop: str):
    data = get_shop_data(shop)
    # Si pas de data, on renvoie 0 sans planter
    return {"credits": data[1] if data else 0}

class BuyRequest(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    data = get_shop_data(req.shop)
    if not data: 
        raise HTTPException(401, "Session expirée. Rafraichissez la page.")
    
    token = data[0]
    
    # Configuration des packs
    if req.pack_id == 'pack_10': 
        price, credits, name = 4.99, 10, "Pack 10 Crédits"
    elif req.pack_id == 'pack_30': 
        price, credits, name = 9.99, 30, "Pack 30 Crédits"
    else: 
        price, credits, name = 19.99, 100, "Pack 100 Crédits"

    try:
        session = shopify.Session(req.shop, "2024-01", token)
        shopify.ShopifyResource.activate_session(session)
        
        charge = shopify.ApplicationCharge.create({
            "name": name,
            "price": price,
            "return_url": f"{HOST}/billing/callback?shop={req.shop}&credits={credits}",
            "test": True # Mettre à False pour passer en vrai paiement
        })
        return {"confirmation_url": charge.confirmation_url}
    except Exception as e:
        print(f"Erreur paiement: {e}")
        raise HTTPException(500, f"Erreur Shopify: {str(e)}")

@app.get("/billing/callback")
def billing_callback(shop: str, credits: int, charge_id: str):
    data = get_shop_data(shop)
    if not data: return RedirectResponse(f"/?shop={shop}&error=db_error")

    try:
        session = shopify.Session(shop, "2024-01", data[0])
        shopify.ShopifyResource.activate_session(session)
        
        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status == 'accepted':
            charge.activate()
            update_credits(shop, int(credits))
            return RedirectResponse(f"/?shop={shop}&success=true")
        else:
            return RedirectResponse(f"/?shop={shop}&error=declined")
    except Exception as e:
        return RedirectResponse(f"/?shop={shop}&error={str(e)}")

class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    data = get_shop_data(req.shop)
    if not data: raise HTTPException(401, "Shop non identifié")
    
    credits_dispo = data[1]
    if credits_dispo < 1:
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
        
        # Débit du crédit
        update_credits(req.shop, -1)
        
        return {
            "result_image_url": final_url,
            "credits_remaining": credits_dispo - 1
        }
        
    except Exception as e:
        print(f"Erreur Replicate: {e}")
        raise HTTPException(500, f"Erreur IA: {str(e)}")
