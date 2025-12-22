import os
import shopify
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 

SCOPES = ['write_script_tags', 'read_products', 'write_products'] # Ajouté pour gérer les Metafields
API_VERSION = "2025-01" 
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()
app.mount("/static", StaticFiles(directory="."), name="static")

# --- MÉMOIRE VIVE (Remplaçant de la DB pour les tokens) ---
# Format : { "boutique.myshopify.com": "shpat_xxxxxxxxxxx" }
shop_sessions = {}

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "frame-ancestors https://admin.shopify.com https://*.myshopify.com;"
    return response

# --- UTILITAIRES ---

def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

def get_shopify_credits(shop_url, token):
    """ Récupère les crédits stockés dans les Metafields Shopify """
    try:
        session = shopify.Session(shop_url, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        # On cherche le metafield "credits" dans le namespace "stylelab"
        # On attache les crédits à l'objet "Shop"
        current_shop = shopify.Shop.current()
        metafields = current_shop.metafields()
        
        for m in metafields:
            if m.namespace == "stylelab" and m.key == "credits":
                return int(m.value)
        
        # Si pas trouvé, on initialise à 3 crédits gratuits
        return 3
    except Exception as e:
        print(f"Erreur lecture crédits: {e}")
        return 0

def update_shopify_credits(shop_url, token, new_amount):
    """ Enregistre les crédits dans Shopify """
    try:
        session = shopify.Session(shop_url, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        current_shop = shopify.Shop.current()
        metafields = current_shop.metafields()
        target_metafield = None
        
        for m in metafields:
            if m.namespace == "stylelab" and m.key == "credits":
                target_metafield = m
                break
        
        if target_metafield:
            target_metafield.value = new_amount
            target_metafield.save()
        else:
            # Création du champ s'il n'existe pas
            current_shop.add_metafield(shopify.Metafield({
                "namespace": "stylelab",
                "key": "credits",
                "value": new_amount,
                "type": "integer"
            }))
            
        print(f"✅ Crédits mis à jour pour {shop_url} : {new_amount}")
    except Exception as e:
        print(f"❌ Erreur sauvegarde crédits: {e}")

# --- ROUTES ---

@app.get("/")
def index(shop: str = None):
    if not shop: return "Paramètre shop manquant", 400
    clean_shop = clean_shop_url(shop)
    
    # Si on n'a pas le token en mémoire, on redirige pour se reconnecter
    if clean_shop not in shop_sessions:
        return RedirectResponse(f"/login?shop={clean_shop}")

    return FileResponse('index.html')

@app.get("/login")
def login(shop: str):
    clean_shop = clean_shop_url(shop)
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(clean_shop, API_VERSION)
    
    # On demande les droits pour écrire les metafields (crédits)
    permission_url = session.create_permission_url(SCOPES, f"{HOST}/auth/callback")
    
    return HTMLResponse(content=f"<script>window.top.location.href='{permission_url}'</script>")

@app.get("/auth/callback")
def auth_callback(request: Request):
    params = dict(request.query_params)
    shop = params.get('shop')
    code = params.get('code')
    clean_shop = clean_shop_url(shop)
    
    try:
        # Échange manuel du token (bypass HMAC strict)
        access_token_url = f"https://{clean_shop}/admin/oauth/access_token"
        payload = {
            "client_id": SHOPIFY_API_KEY,
            "client_secret": SHOPIFY_API_SECRET,
            "code": code
        }
        response = requests.post(access_token_url, json=payload)
        
        if response.status_code == 200:
            token = response.json().get('access_token')
            
            # STOCKAGE EN MÉMOIRE (Plus de DB)
            shop_sessions[clean_shop] = token
            print(f"🔑 Token en mémoire pour {clean_shop}")
            
            # On initialise les crédits dans Shopify si besoin
            current_credits = get_shopify_credits(clean_shop, token)
            if current_credits == 0: # Si nouveau
                update_shopify_credits(clean_shop, token, 3) # 3 offerts
            
            return RedirectResponse(f"https://admin.shopify.com/store/{clean_shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
        else:
            return f"Erreur Shopify: {response.text}", 500
            
    except Exception as e:
        return f"Erreur Auth: {e}", 500

# --- API ---

@app.get("/api/get-credits")
def get_credits_api(shop: str):
    clean_shop = clean_shop_url(shop)
    token = shop_sessions.get(clean_shop)
    
    if not token: 
        # Si le serveur a redémarré, on renvoie 401 pour que le frontend recharge la page
        # ce qui relancera le login silencieux
        raise HTTPException(401, "Reload needed")
        
    credits = get_shopify_credits(clean_shop, token)
    return {"credits": credits}

class BuyRequest(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    clean_shop = clean_shop_url(req.shop)
    token = shop_sessions.get(clean_shop)
    
    if not token: raise HTTPException(401, "Reload needed")

    if req.pack_id == 'pack_10': price, amount, name = 4.99, 10, "10 Crédits"
    elif req.pack_id == 'pack_30': price, amount, name = 9.99, 30, "30 Crédits"
    else: price, amount, name = 19.99, 100, "100 Crédits"

    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(clean_shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        charge = shopify.ApplicationCharge.create({
            "name": name, "price": price, "test": True,
            "return_url": f"{HOST}/billing/callback?shop={clean_shop}&amt={amount}"
        })
        return {"confirmation_url": charge.confirmation_url}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/billing/callback")
def billing_callback(shop: str, amt: int, charge_id: str):
    clean_shop = clean_shop_url(shop)
    token = shop_sessions.get(clean_shop)
    
    if not token: return RedirectResponse(f"/login?shop={clean_shop}") # Re-login si besoin
    
    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(clean_shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status in ['accepted', 'active']:
            if charge.status == 'accepted': charge.activate()
            
            # On récupère les crédits actuels et on ajoute
            current = get_shopify_credits(clean_shop, token)
            update_shopify_credits(clean_shop, token, current + int(amt))
            
            return RedirectResponse(f"https://admin.shopify.com/store/{clean_shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
            
        return "Paiement échoué"
    except Exception as e:
        return f"Erreur: {e}"

class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    clean_shop = clean_shop_url(req.shop)
    token = shop_sessions.get(clean_shop)
    
    if not token: raise HTTPException(401, "Reload needed")
    
    current_credits = get_shopify_credits(clean_shop, token)
    if current_credits < 1: raise HTTPException(402, "Pas assez de crédits")

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
        
        # Débit
        update_shopify_credits(clean_shop, token, current_credits - 1)
        
        return {"result_image_url": final_url, "credits_remaining": current_credits - 1}
    except Exception as e:
        raise HTTPException(500, str(e))
