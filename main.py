import os
import hmac
import hashlib
import shopify
import requests
import replicate
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") 
# AJOUT DE METAFIELDS DANS LES SCOPES (OBLIGATOIRE POUR TES CRÉDITS)
SCOPES = ['read_products', 'write_products', 'read_metafields', 'write_metafields']
API_VERSION = "2024-01"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

# --- MIDDLEWARE DE SÉCURITÉ (CORRIGE LA PAGE BLANCHE) ---
# Autorise l'affichage dans l'iframe Shopify
@app.middleware("http")
async def add_csp_header(request: Request, call_next):
    response = await call_next(request)
    # Récupérer le shop depuis les params s'il existe
    shop = request.query_params.get("shop", "")
    
    # Politique de sécurité standard pour Shopify
    policy = f"frame-ancestors https://{shop} https://admin.shopify.com;"
    
    # Si on n'a pas de shop, on met une policy générique, sinon on cible le shop
    if shop:
        response.headers["Content-Security-Policy"] = policy
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stockage mémoire simple (Note: utilise une Base de données pour la vraie prod)
shop_sessions = {}

# --- FONCTIONS UTILITAIRES ---

def clean_shop_url(url):
    if not url: return ""
    return url.replace("https://", "").replace("http://", "").strip("/")

def verify_shopify_hmac(query_dict: dict) -> bool:
    """Vérifie que la requête vient bien de Shopify"""
    if "hmac" not in query_dict:
        return False
    
    hmac_received = query_dict["hmac"]
    # On retire le hmac des données à signer
    data = {k: v for k, v in query_dict.items() if k != "hmac"}
    # On trie les paramètres par ordre alphabétique
    msg = "&".join([f"{key}={value}" for key, value in sorted(data.items())])
    
    # Calcul de la signature
    digest = hmac.new(
        SHOPIFY_API_SECRET.encode('utf-8'),
        msg.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(digest, hmac_received)

# --- ROUTES STATIQUES ---
# Assure-toi que index.html, styles.css et app.js sont dans le MEME dossier que main.py

@app.get("/")
def index():
    return FileResponse('index.html')

@app.get("/styles.css")
def styles():
    return FileResponse('styles.css', media_type='text/css')

@app.get("/app.js")
def javascript():
    return FileResponse('app.js', media_type='application/javascript')

# --- AUTHENTIFICATION ---

@app.get("/login")
def login(shop: str):
    shop = clean_shop_url(shop)
    # Construction de l'URL d'autorisation officielle
    auth_url = (
        f"https://{shop}/admin/oauth/authorize?"
        f"client_id={SHOPIFY_API_KEY}&"
        f"scope={','.join(SCOPES)}&"
        f"redirect_uri={HOST}/auth/callback"
    )
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(request: Request):
    params = dict(request.query_params)
    shop = clean_shop_url(params.get("shop"))
    code = params.get("code")
    host = params.get("host")

    # 1. VÉRIFICATION DE SÉCURITÉ HMAC
    if not verify_shopify_hmac(params):
        return HTMLResponse("<h1>Security Error: HMAC Validation Failed</h1>", status_code=400)

    try:
        # 2. Échange du code contre le token
        url = f"https://{shop}/admin/oauth/access_token"
        payload = {
            "client_id": SHOPIFY_API_KEY, 
            "client_secret": SHOPIFY_API_SECRET, 
            "code": code
        }
        res = requests.post(url, json=payload)
        
        if res.status_code == 200:
            token = res.json().get('access_token')
            shop_sessions[shop] = token
            
            # Initialisation des crédits par défaut si c'est la première fois
            # (On ne le fait pas ici pour garder la rapidité, on le fera au besoin)

            # Redirection vers l'interface intégrée Shopify
            target_url = f"https://admin.shopify.com/store/{shop.replace('.myshopify.com', '')}/apps/{SHOPIFY_API_KEY}"
            if host:
                target_url += f"?host={host}"
                
            return RedirectResponse(target_url)
        
        return HTMLResponse(f"Token Error: {res.text}", status_code=400)
    except Exception as e:
        return HTMLResponse(content=f"Auth Error: {str(e)}", status_code=500)

# --- API CRÉDITS ---

@app.get("/api/get-credits")
def get_credits(shop: str):
    shop = clean_shop_url(shop)
    token = shop_sessions.get(shop)
    
    if not token: 
        # Code 401 déclenche le re-login côté JS
        raise HTTPException(status_code=401, detail="Session expired")

    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        # Récupération Metafield
        # Note: Metafield.find renvoie parfois une liste, parfois un objet
        mf = shopify.Metafield.find(namespace="stylelab", key="credits")
        
        val = 0
        if mf:
            # Gestion robuste du retour de l'API Shopify (liste vs objet unique)
            if isinstance(mf, list) and len(mf) > 0:
                val = int(mf[0].value)
            elif hasattr(mf, 'value'):
                val = int(mf.value)
                
        return {"credits": val}
    except Exception as e:
        # Si erreur (ex: pas de crédits encore définis), on renvoie 0
        print(f"Error getting credits: {e}")
        return {"credits": 0}

class BuyRequest(BaseModel):
    shop: str
    pack_id: str
    custom_amount: int = 0

@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    shop = clean_shop_url(req.shop)
    token = shop_sessions.get(shop)
    
    if not token: 
        raise HTTPException(status_code=401, detail="Session expired")

    # Définition des packs
    price, name, credits = 0, "", 0
    if req.pack_id == 'pack_10': price, name, credits = 4.99, "10 Credits", 10
    elif req.pack_id == 'pack_30': price, name, credits = 12.99, "30 Credits", 30
    elif req.pack_id == 'pack_100': price, name, credits = 29.99, "100 Credits", 100
    elif req.pack_id == 'pack_custom':
        credits = req.custom_amount
        if credits < 200: return JSONResponse({"error": "Min 200 credits"}, status_code=400)
        price = round(credits * 0.25, 2)
        name = f"{credits} Credits (Custom)"
    else: return JSONResponse({"error": "Invalid Pack"}, status_code=400)

    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        return_url = f"{HOST}/billing/callback?shop={shop}&amt={credits}"
        
        # CRÉATION DU PAIEMENT
        # IMPORTANT: "test": True permet de tester sans payer. 
        # Passe à False avant la vraie soumission si tu veux facturer pour de vrai.
        charge = shopify.ApplicationCharge.create({
            "name": name,
            "price": price,
            "test": True, 
            "return_url": return_url
        })
        
        return {"confirmation_url": charge.confirmation_url}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/billing/callback")
def billing_callback(shop: str, amt: int, charge_id: str):
    shop = clean_shop_url(shop)
    token = shop_sessions.get(shop)
    
    # Si session perdue durant le paiement -> re-login
    if not token: return RedirectResponse(f"/login?shop={shop}")

    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)

        charge = shopify.ApplicationCharge.find(charge_id)
        
        # Activation du paiement si accepté
        if charge.status != 'active':
            charge.activate()

        # Mise à jour des crédits
        mf_list = shopify.Metafield.find(namespace="stylelab", key="credits")
        curr = 0
        if mf_list:
             if isinstance(mf_list, list) and len(mf_list) > 0:
                curr = int(mf_list[0].value)
             elif hasattr(mf_list, 'value'):
                curr = int(mf_list.value)

        new_total = curr + amt
        
        # Sauvegarde
        meta = shopify.Metafield()
        meta.namespace = 'stylelab'
        meta.key = 'credits'
        meta.value = new_total
        meta.type = 'number_integer'
        meta.save()

        # Retour à l'admin
        admin_url = f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}"
        # Script JS pour briser la fenêtre de paiement et revenir à l'app
        return HTMLResponse(f"<script>window.top.location.href='{admin_url}';</script>")
        
    except Exception as e:
        return HTMLResponse(f"Billing Error: {e}")

# --- API IA ---

class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    shop = clean_shop_url(req.shop)
    token = shop_sessions.get(shop)
    
    # Vérification des crédits avant de lancer l'IA
    if not token: raise HTTPException(status_code=401, detail="Session expired")
    
    # 1. VÉRIFIER CRÉDIT
    try:
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        session = shopify.Session(shop, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        
        mf_list = shopify.Metafield.find(namespace="stylelab", key="credits")
        current_credits = 0
        if mf_list:
             if isinstance(mf_list, list) and len(mf_list) > 0:
                current_credits = int(mf_list[0].value)
             elif hasattr(mf_list, 'value'):
                current_credits = int(mf_list.value)
        
        if current_credits < 1:
            return JSONResponse({"error": "Not enough credits. Please top up."}, status_code=402)
            
    except Exception as e:
        return JSONResponse({"error": "Could not verify credits."}, status_code=500)

    # 2. LANCER REPLICATE
    try:
        clothing_url = req.clothing_image_url
        # Correction d'URL Shopify fréquente (commence par //)
        if clothing_url.startswith("//"): 
            clothing_url = "https:" + clothing_url
            
        output = replicate.run(MODEL_ID, input={
            "human_img": req.person_image_url, 
            "garm_img": clothing_url,
            "garment_des": req.category, 
            "category": "upper_body"
        })
        
        # 3. DÉBITER CRÉDIT
        new_total = current_credits - 1
        meta = shopify.Metafield()
        meta.namespace = 'stylelab'
        meta.key = 'credits'
        meta.value = new_total
        meta.type = 'number_integer'
        meta.save()

        result_url = str(output[0]) if isinstance(output, list) else str(output)
        return {"result_image_url": result_url, "new_credits": new_total}
        
    except Exception as e:
        print(f"AI Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# --- WEBHOOKS (OBLIGATOIRES GDPR SHOPIFY) ---
@app.post("/webhooks/customers/data_request")
def w1(): return {"ok": True}
@app.post("/webhooks/customers/redact")
def w2(): return {"ok": True}
@app.post("/webhooks/shop/redact")
def w3(): return {"ok": True}
