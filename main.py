import os
import shopify
import psycopg2
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import replicate
from urllib.parse import quote

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 
# Astuce : On force le format postgresql:// pour éviter les bugs Render
raw_db_url = os.getenv("DATABASE_URL")
DATABASE_URL = raw_db_url.replace("postgres://", "postgresql://") if raw_db_url else None

SCOPES = ['write_script_tags', 'read_products']
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()
app.mount("/static", StaticFiles(directory="."), name="static")

# --- GESTION DB ---
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
        print("✅ DB Connectée.")
    except Exception as e:
        print(f"❌ Erreur DB: {e}")

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
    except:
        return None

def update_credits(shop_url, amount):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE shops SET credits = credits + %s WHERE shop_url = %s", (amount, shop_url))
    conn.commit()
    conn.close()

# --- INTELLIGENCE DE REDIRECTION (LE FIX FIABLE) ---
# Si l'installation échoue dans l'iframe, ce script JS force la fenêtre à se recharger en top-level
def escape_iframe(redirect_url):
    return HTMLResponse(content=f"""
        <script>
            window.top.location.href = "{redirect_url}";
        </script>
    """)

# --- ROUTES PRINCIPALES ---

@app.get("/")
def index(shop: str = None):
    # 1. Si pas de paramètre shop, erreur
    if not shop: return "Paramètre ?shop= manquant", 400
    
    # 2. VÉRIFICATION AUTO-RÉPARATION
    # On regarde si le shop est dans la DB
    data = get_shop_data(shop)
    
    if not data:
        # 🚨 LE SHOP N'EST PAS ENREGISTRÉ -> ON LANCE L'INSTALLATION AUTO
        print(f"⚠️ Shop inconnu ({shop}). Lancement auto-installation...")
        return RedirectResponse(f"/login?shop={shop}")

    # 3. Si tout est bon, on affiche l'app
    return FileResponse('index.html')

@app.get("/login")
def login(shop: str):
    if not shop: return "Shop manquant", 400
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    
    # URL de callback
    redirect_uri = f"{HOST}/auth/callback"
    permission_url = shopify.Session(shop.strip(), "2024-01").create_permission_url(SCOPES, redirect_uri)
    
    # On utilise le script JS pour sortir de l'iframe si besoin (sécurité Shopify)
    return escape_iframe(permission_url)

@app.get("/auth/callback")
def auth_callback(shop: str, code: str):
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(shop, "2024-01")
    try:
        access_token = session.request_token(dict(code=code))
        
        # SAUVEGARDE EN BÉTON ARMÉ
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO shops (shop_url, access_token, credits) 
            VALUES (%s, %s, 50)
            ON CONFLICT (shop_url) 
            DO UPDATE SET access_token = EXCLUDED.access_token;
        """, (shop, access_token))
        conn.commit()
        conn.close()
        
        # Redirection finale vers l'app
        return RedirectResponse(f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
        
    except Exception as e:
        return f"Erreur fatale installation: {e}", 500

# --- API (PAIEMENT & IA) ---

@app.get("/api/get-credits")
def get_credits_api(shop: str):
    data = get_shop_data(shop)
    if not data: return {"credits": 0} # Pas d'erreur, juste 0
    return {"credits": data[1]}

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest): # Assure-toi d'avoir importé BuyRequest (code précédent)
    # ... (Garde ton code de paiement ici, il était bon)
    # Si tu as besoin je te le remets complet
    pass 
    # NOTE: J'ai abrégé ici pour la lisibilité, garde ton bloc PAIEMENT d'avant
    # Mais AJOUTE cette ligne au début :
    data = get_shop_data(req.shop)
    if not data: raise HTTPException(401, "Shop non trouvé - Rafraichissez la page")
    # ... suite du code

# (Garde tes routes /api/generate et classes Pydantic comme avant)
# AJOUTE JUSTE CE BLOC à la fin pour que ça compile :
class BuyRequest(BaseModel):
    shop: str
    pack_id: str
    
class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

# ... (Copie-colle tes fonctions generate et buy_credits complètes ici)
