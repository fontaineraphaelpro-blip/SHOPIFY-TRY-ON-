import os
import io
import time
import sqlite3
import shopify
import requests
import replicate
from typing import Optional, Dict
from fastapi import FastAPI, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# --- CONFIG ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST", "https://ton-app.onrender.com").rstrip('/')
# "write_products" permet de lire/écrire, "offline_access" est implicite mais crucial
SCOPES = ['read_products', 'write_products', 'read_themes', 'write_themes']
API_VERSION = "2024-10"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()
templates = Jinja2Templates(directory=".")
RATE_LIMIT_DB: Dict[str, Dict] = {} 

# --- GESTION CORS (CRUCIAL POUR LE CLIENT) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. BASE DE DONNÉES (TOKEN PERMANENT) ---
def init_db():
    with sqlite3.connect("database.db") as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS shops (domain TEXT PRIMARY KEY, token TEXT)")
        conn.commit()
init_db()

def save_token_db(shop, token):
    with sqlite3.connect("database.db") as conn:
        conn.execute("INSERT OR REPLACE INTO shops (domain, token) VALUES (?, ?)", (shop, token))
        conn.commit()
        print(f"💾 TOKEN SAUVEGARDÉ pour {shop}")

def get_token_db(shop):
    try:
        with sqlite3.connect("database.db") as conn:
            cur = conn.cursor()
            cur.execute("SELECT token FROM shops WHERE domain = ?", (shop,))
            row = cur.fetchone()
            if row: return row[0]
            print(f"⚠️ AUCUN TOKEN TROUVÉ pour {shop} dans la DB.")
            return None
    except Exception as e:
        print(f"❌ Erreur DB: {e}")
        return None

# --- 2. LOGIQUE SHOPIFY (SERVICE ACCOUNT) ---
def activate_shop_session(shop):
    """Récupère le token et active la session serveur."""
    token = get_token_db(shop)
    if not token:
        return False
    
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    # On crée une session 'offline' (sans utilisateur)
    session = shopify.Session(shop, API_VERSION, token)
    shopify.ShopifyResource.activate_session(session)
    return True

def get_metafield(namespace, key, default=0):
    try:
        metafields = shopify.Metafield.find(namespace=namespace, key=key)
        if metafields:
            return metafields[0].value
    except: pass
    return default

def set_metafield(namespace, key, value, type_val):
    try:
        metafield = shopify.Metafield()
        metafield.namespace = namespace
        metafield.key = key
        metafield.value = value
        metafield.type = type_val
        metafield.save()
    except Exception as e: 
        print(f"⚠️ Erreur Metafield: {e}")

def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    shop = request.query_params.get("shop")
    return templates.TemplateResponse("index.html", { "request": request, "shop": shop, "api_key": SHOPIFY_API_KEY })

@app.get("/styles.css")
def styles(): return FileResponse('styles.css', media_type='text/css')
@app.get("/app.js")
def javascript(): return FileResponse('app.js', media_type='application/javascript')

# --- AUTH (OBLIGATOIRE UNE FOIS POUR AVOIR LE TOKEN) ---
@app.get("/login")
def login(shop: str):
    shop = clean_shop_url(shop)
    # access_mode=offline est par défaut, mais on s'assure d'avoir un token permanent
    auth_url = f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={','.join(SCOPES)}&redirect_uri={HOST}/auth/callback"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(request: Request):
    params = dict(request.query_params)
    shop = clean_shop_url(params.get("shop"))
    code = params.get("code")
    
    url = f"https://{shop}/admin/oauth/access_token"
    payload = {"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code}
    
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            data = res.json()
            token = data.get('access_token')
            save_token_db(shop, token) # <--- C'est ici qu'on remplit le coffre-fort
            
            # On redirige vers l'admin Shopify pour montrer que ça marche
            target_url = f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}"
            return RedirectResponse(target_url)
        else:
            return HTMLResponse(f"Erreur Token Shopify: {res.text}", status_code=400)
    except Exception as e:
        return HTMLResponse(f"Erreur Serveur: {str(e)}", status_code=500)

# --- API DATA (DASHBOARD) ---
@app.get("/api/get-data")
def get_data_route(shop: str):
    shop = clean_shop_url(shop)
    if not activate_shop_session(shop):
        return JSONResponse({"error": "Shop non connecté. Re-installez l'app."}, status_code=401)
        
    try:
        credits = int(float(get_metafield("virtual_try_on", "wallet", 0)))
        total_tryons = int(float(get_metafield("virtual_try_on", "total_tryons", 0)))
        
        # Valeurs par défaut widget
        w_text = get_metafield("vton_widget", "btn_text", "Try It On Now ✨")
        
        return {"credits": credits, "usage": total_tryons, "widget": {"text": w_text}}
    except Exception as e:
        print(f"Error data: {e}")
        return {"credits": 0}

# --- GENERATE (LE COEUR DU SYSTÈME) ---
@app.post("/api/generate")
async def generate(
    request: Request,
    shop: str = Form(...),
    person_image: UploadFile = File(...),
    clothing_url: Optional[str] = Form(None),
    clothing_file: Optional[UploadFile] = File(None)
):
    print(f"🚀 GENERATE START pour {shop}")
    
    # 1. AUTHENTIFICATION SILENCIEUSE
    # On n'utilise PAS la session utilisateur, mais le token DB
    shop = clean_shop_url(shop)
    if not activate_shop_session(shop):
        print(f"❌ ECHEC AUTH: Pas de token en base pour {shop}")
        return JSONResponse({"error": "Authentication failed. Merchant must open app once."}, status_code=403)

    # 2. VÉRIFICATION CRÉDITS
    try:
        credits = int(float(get_metafield("virtual_try_on", "wallet", 0)))
        if credits < 1:
            return JSONResponse({"error": "No credits left"}, status_code=402)
    except:
        credits = 0
        
    # 3. PRÉPARATION IMAGES
    try:
        person_bytes = await person_image.read()
        person_file = io.BytesIO(person_bytes)
        
        garment_input = None
        # Priorité URL (Widget)
        if clothing_url and len(str(clothing_url)) > 5:
            garment_input = str(clothing_url)
            if garment_input.startswith("//"): garment_input = "https:" + garment_input
        elif clothing_file:
            garment_bytes = await clothing_file.read()
            garment_input = io.BytesIO(garment_bytes)
        else:
             return JSONResponse({"error": "No garment"}, status_code=400)

        # 4. APPEL REPLICATE
        print("🤖 Envoi à Replicate...")
        output = replicate.run(MODEL_ID, input={
            "human_img": person_file, 
            "garm_img": garment_input,
            "category": "upper_body"
        })
        
        result_url = str(output[0]) if isinstance(output, list) else str(output)
        print(f"✅ SUCCÈS: {result_url}")

        # 5. DÉBIT
        set_metafield("virtual_try_on", "wallet", credits - 1, "integer")
        
        return {"result_image_url": result_url}

    except Exception as e:
        print(f"❌ CRASH: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# Ajout des options pour CORS
@app.options("/api/generate")
async def options_generate():
    return JSONResponse(content={"ok":True}, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"})
