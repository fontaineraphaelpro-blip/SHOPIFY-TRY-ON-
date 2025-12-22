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

SCOPES = ['write_script_tags', 'read_products', 'write_products']
API_VERSION = "2025-01" 
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# On sert le dossier static uniquement pour le widget.js
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mémoire vive
shop_sessions = {}

# --- UTILITAIRES ---
def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

def get_shopify_credits(shop_url, token):
    try:
        session = shopify.Session(shop_url, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        current_shop = shopify.Shop.current()
        metafields = current_shop.metafields()
        for m in metafields:
            if m.namespace == "stylelab" and m.key == "credits":
                return int(m.value)
        return 3 
    except Exception as e:
        print(f"Erreur credits: {e}")
        return 0

def update_shopify_credits(shop_url, token, new_amount):
    try:
        session = shopify.Session(shop_url, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        current_shop = shopify.Shop.current()
        metafields = current_shop.metafields()
        target = None
        for m in metafields:
            if m.namespace == "stylelab" and m.key == "credits":
                target = m
                break
        if target:
            target.value = new_amount
            target.save()
        else:
            current_shop.add_metafield(shopify.Metafield({
                "namespace": "stylelab", "key": "credits", "value": new_amount, "type": "integer"
            }))
    except Exception as e:
        print(f"Erreur save credits: {e}")

def inject_script_tag(shop_url, token):
    try:
        session = shopify.Session(shop_url, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        existing = shopify.ScriptTag.find()
        src = f"{HOST}/static/widget.js"
        if not any(s.src == src for s in existing):
            shopify.ScriptTag.create({"event": "onload", "src": src})
            print(f"Widget injecté sur {shop_url}")
    except Exception as e:
        print(f"Erreur script tag: {e}")

# --- ROUTES ---

@app.get("/")
def index(shop: str = None):
    if not shop: return HTMLResponse("<h1>Paramètre shop manquant</h1>")
    clean_shop = clean_shop_url(shop)
    
    # Si le serveur a redémarré (RAM vide), on force le login
    if clean_shop not in shop_sessions:
        return RedirectResponse(f"/login?shop={clean_shop}")

    return FileResponse('index.html')

@app.get("/login")
def login(shop: str):
    clean_shop = clean_shop_url(shop)
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(clean_shop, API_VERSION)
    permission_url = session.create_permission_url(SCOPES, f"{HOST}/auth/callback")
    
    # C'EST ICI QUE TU AVAIS L'ERREUR : J'ai bien mis le 'f' avant les guillemets
    return HTMLResponse(content=f"<script>window.top.location.href='{permission_url}'</script>")

@app.get("/auth/callback")
def auth_callback(request: Request):
    params = dict(request.query_params)
    shop = params.get('shop')
    code = params.get('code')
    clean_shop = clean_shop_url(shop)
    
    try:
        access_token_url = f"https://{clean_shop}/admin/oauth/access_token"
        payload = { "client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code }
        response = requests.post(access_token_url, json=payload)
        
        if response.status_code == 200:
            token = response.json().get('access_token')
            shop_sessions[clean_shop] = token
            
            # Init crédits et widget
            curr = get_shopify_credits(clean_shop, token)
            if curr == 0: update_shopify_credits(clean_shop, token, 3)
            inject_script_tag(clean_shop, token)
            
            return RedirectResponse(f"https://admin.shopify.com/store/{clean_shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
        else:
            return HTMLResponse(f"<h1>Erreur Shopify</h1><p>{response.text}</p>")
    except Exception as e:
        return HTMLResponse(f"<h1>Erreur Interne</h1><p>{str(e)}</p>")

# --- API ---

@app.get("/api/get-credits")
def get_credits_api(shop: str):
    clean_shop = clean_shop_url(shop)
    token = shop_sessions.get(clean_shop)
    # Si token perdu (redémarrage), on renvoie 401 pour forcer le reload client
    if not token: raise HTTPException(status_code=401, detail="Session expired")
    return {"credits": get_shopify_credits(clean_shop, token)}

class BuyRequest(BaseModel):
    shop: str
    pack_id: str

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    clean_shop = clean_shop_url(req.shop)
    token = shop_sessions.get(clean_shop)
    if not token: raise HTTPException(401, "Session expired")

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
    if not token: return RedirectResponse(f"/login?shop={clean_shop}")
    
    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(clean_shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        charge = shopify.ApplicationCharge.find(charge_id)
        if charge.status in ['accepted', 'active']:
            if charge.status == 'accepted': charge.activate()
            current = get_shopify_credits(clean_shop, token)
            update_shopify_credits(clean_shop, token, current + int(amt))
            return RedirectResponse(f"https://admin.shopify.com/store/{clean_shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
        return HTMLResponse("<h1>Paiement échoué</h1>")
    except Exception as e:
        return HTMLResponse(f"<h1>Erreur</h1><p>{e}</p>")

class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    clean_shop = clean_shop_url(req.shop)
    token = shop_sessions.get(clean_shop)
    
    # Si le serveur a redémarré, le widget client ne peut pas générer
    if not token: 
        raise HTTPException(400, "Maintenance: Veuillez ouvrir l'application dans l'admin Shopify pour reconnecter le système.")

    current = get_shopify_credits(clean_shop, token)
    if current < 1: raise HTTPException(402, "Crédits insuffisants")

    try:
        cat_map = {"tops": "upper_body", "bottoms": "lower_body", "one-pieces": "dresses"}
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": req.person_image_url,
                "garm_img": req.clothing_image_url,
                "garment_des": req.category, 
                "category": cat_map.get(req.category, "upper_body"),
                "crop": False, "seed": 42, "steps": 30
            }
        )
        final_url = str(output[0]) if isinstance(output, list) else str(output)
        update_shopify_credits(clean_shop, token, current - 1)
        return {"result_image_url": final_url, "credits_remaining": current - 1}
    except Exception as e:
        raise HTTPException(500, str(e))
