import os
import shopify
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST")
SCOPES = ['read_products', 'write_products']
API_VERSION = "2024-01"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="."), name="static")

# Mémoire tampon pour les tokens
shop_sessions = {}

def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

# --- ROUTES ---
@app.get("/")
def index():
    return FileResponse('index.html')

@app.get("/login")
def login(shop: str):
    shop = clean_shop_url(shop)
    auth_url = f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={','.join(SCOPES)}&redirect_uri={HOST}/auth/callback"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(shop: str, code: str):
    shop = clean_shop_url(shop)
    url = f"https://{shop}/admin/oauth/access_token"
    payload = {"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code}
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            token = res.json().get('access_token')
            shop_sessions[shop] = token
            # Redirection vers l'admin Shopify
            return RedirectResponse(f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
    except: pass
    return HTMLResponse("Erreur Connexion")

# --- API ---

class BuyRequest(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    shop = clean_shop_url(req.shop)
    token = shop_sessions.get(shop)
    
    if not token:
        # Erreur 401 pour forcer le JS à reconnecter le client
        raise HTTPException(status_code=401, detail="Session expirée")

    # Définition des packs
    if req.pack_id == 'pack_10': price, name, credits = 4.99, "10 Crédits", 10
    elif req.pack_id == 'pack_30': price, name, credits = 9.99, "30 Crédits", 30
    elif req.pack_id == 'pack_100': price, name, credits = 19.99, "100 Crédits", 100
    else: return {"error": "Pack inconnu"}

    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        # On passe le nombre de crédits dans l'URL de retour pour savoir quoi ajouter
        return_url = f"{HOST}/billing/callback?shop={shop}&amt={credits}"
        
        charge = shopify.ApplicationCharge.create({
            "name": name,
            "price": price,
            "test": True, # Mets False pour de vrais paiements
            "return_url": return_url
        })
        
        if charge.confirmation_url:
            return {"confirmation_url": charge.confirmation_url}
        return {"error": "Erreur création charge"}
    except Exception as e:
        return {"error": str(e)}

# --- CALLBACK PAIEMENT & AJOUT CRÉDITS ---
@app.get("/billing/callback")
def billing_callback(shop: str, amt: int, charge_id: str):
    shop = clean_shop_url(shop)
    token = shop_sessions.get(shop)
    
    if not token:
        # Si on a perdu la session pendant le paiement, on demande de se reconnecter
        return RedirectResponse(f"/login?shop={shop}")

    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)

        # 1. Valider le paiement (Important !)
        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status != 'active':
            charge.activate()

        # 2. Récupérer les crédits actuels (via Metafields)
        current_shop = shopify.Shop.current()
        # On cherche le metafield "credits"
        credits_field = shopify.Metafield.find(namespace="stylelab", key="credits")
        
        current_credits = 0
        if credits_field:
            # Si on en trouve un (c'est une liste), on prend le premier
            if isinstance(credits_field, list) and len(credits_field) > 0:
                current_credits = int(credits_field[0].value)
            elif not isinstance(credits_field, list):
                current_credits = int(credits_field.value)

        # 3. Ajouter les nouveaux crédits
        new_total = current_credits + amt
        
        # 4. Sauvegarder dans Shopify (C'est ça qui persiste !)
        metafield = shopify.Metafield()
        metafield.namespace = "stylelab"
        metafield.key = "credits"
        metafield.value = new_total
        metafield.type = "number_integer"
        current_shop.add_metafield(metafield)

        # 5. Redirection finale vers l'App dans Shopify
        shop_name = shop.replace(".myshopify.com", "")
        admin_url = f"https://admin.shopify.com/store/{shop_name}/apps/{SHOPIFY_API_KEY}"
        return HTMLResponse(f"<script>window.top.location.href='{admin_url}';</script>")

    except Exception as e:
        return HTMLResponse(f"Erreur lors de l'ajout des crédits : {e}")

# --- API LECTURE CRÉDITS ---
@app.get("/api/get-credits")
def get_credits(shop: str):
    shop = clean_shop_url(shop)
    token = shop_sessions.get(shop)
    
    # Si pas de token, on signale au JS de recharger
    if not token:
        raise HTTPException(status_code=401, detail="Session expirée")

    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        # Lecture des Metafields
        credits = 0
        mf = shopify.Metafield.find(namespace="stylelab", key="credits")
        if mf:
            if isinstance(mf, list) and len(mf) > 0: credits = int(mf[0].value)
            elif not isinstance(mf, list): credits = int(mf.value)
            
        return {"credits": credits}
    except:
        return {"credits": 0} # Par défaut

# --- API GENERATION ---
class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    # (Logique IA inchangée)
    try:
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": req.person_image_url,
                "garm_img": req.clothing_image_url,
                "garment_des": req.category, 
                "category": "upper_body",
                "crop": False, "seed": 42, "steps": 30
            }
        )
        url = str(output[0]) if isinstance(output, list) else str(output)
        return {"result_image_url": url}
    except Exception as e:
        return {"error": str(e)}
