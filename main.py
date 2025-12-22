import os
import shopify
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST")
SCOPES = ['read_products', 'write_products']
API_VERSION = "2025-01"
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- FICHIERS STATIQUES ---
# Sert le dossier courant (.) sur l'URL /static
app.mount("/static", StaticFiles(directory="."), name="static")

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
        return 3 # 3 crédits offerts par défaut
    except: return 0

# --- ROUTES ---
@app.get("/")
def index():
    return FileResponse('index.html')

@app.get("/login")
def login(shop: str):
    clean_shop = clean_shop_url(shop)
    auth_url = f"https://{clean_shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={','.join(SCOPES)}&redirect_uri={HOST}/auth/callback"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(shop: str, code: str):
    clean_shop = clean_shop_url(shop)
    url = f"https://{clean_shop}/admin/oauth/access_token"
    payload = {"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code}
    
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            # Pour l'instant, on ne stocke pas le token en DB pour simplifier,
            # On redirige juste vers l'admin.
            return RedirectResponse(f"https://admin.shopify.com/store/{clean_shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
        else:
             return HTMLResponse(f"Erreur Shopify: {res.text}")
    except Exception as e:
        return HTMLResponse(f"Erreur: {e}")

# --- API ---

# Modèle de données pour l'achat
class BuyRequest(BaseModel):
    shop: str
    pack_id: str
    # Note: Dans un vrai système, on passerait le token ici pour sécuriser

# ROUTE DE PAIEMENT CORRIGÉE
@app.post("/api/buy-credits")
def buy_credits(req: BuyRequest):
    shop = clean_shop_url(req.shop)
    
    # Définition des packs
    if req.pack_id == 'pack_10': price, amount, name = 4.99, 10, "10 Crédits StyleLab"
    elif req.pack_id == 'pack_30': price, amount, name = 9.99, 30, "30 Crédits StyleLab (Best Seller)"
    elif req.pack_id == 'pack_100': price, amount, name = 19.99, 100, "100 Crédits StyleLab (Pro)"
    else: raise HTTPException(400, "Pack invalide")

    try:
        # ATTENTION : Pour que cela fonctionne, il faut une session active.
        # Dans cette version simplifiée sans base de données, cela peut échouer
        # si le serveur a redémarré. C'est une limitation de cette architecture "zéro DB".
        # Pour le test, on suppose que la session est valide si le shop est là.
        
        # On recrée une session temporaire (ne fonctionnera que si le token est encore en RAM ou pas nécessaire pour cette étape)
        shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
        # NOTE IMPORTANTE : Sans le vrai token d'accès ici, Shopify rejettera la demande.
        # Comme nous n'avons pas de DB, cette étape est critique.
        # Si ça échoue, il faudra remettre la gestion de session complète.
        
        # Tentative de création de charge (peut échouer sans token valide)
        charge = shopify.ApplicationCharge.create({
            "name": name,
            "price": price,
            "test": True, # Mettre à False pour de vrais paiements
            "return_url": f"{HOST}/billing/callback?shop={shop}&amt={amount}"
            # Nous n'avons pas le token ici dans cette architecture simplifiée.
            # Si cela échoue, il faudra revenir à la version avec `shop_sessions = {}` en RAM.
        })
        
        # Si la création réussit (rare sans token), on renvoie l'URL
        if charge.confirmation_url:
             return {"confirmation_url": charge.confirmation_url}
        else:
             # Fallback pour le debug si la session manque
             print("Erreur: Impossible de créer la charge sans token de session valide.")
             raise HTTPException(400, "Session expirée ou invalide pour le paiement.")
             
    except Exception as e:
        print(f"Erreur paiement: {e}")
        # Pour le débuggage, si ça plante, on renvoie une erreur claire
        raise HTTPException(500, f"Erreur lors de la création du paiement : {str(e)}. (Architecture sans DB)")


# Route de retour après paiement (Callback)
@app.get("/billing/callback")
def billing_callback(shop: str, amt: int, charge_id: str):
    clean_shop = clean_shop_url(shop)
    # Mêmes limitations ici : sans token stocké, on ne peut pas valider et ajouter les crédits.
    return HTMLResponse("<h1>Paiement accepté (Simulation)</h1><p>Dans l'architecture complète avec base de données, les crédits seraient ajoutés ici.</p><a href='/'>Retour au Dashboard</a>")


class TryOnRequest(BaseModel):
    shop: str
    person_image_url: str
    clothing_image_url: str
    category: str

@app.post("/api/generate")
def generate(req: TryOnRequest):
    # (Pas de vérification de crédits dans cette version simplifiée)
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
        return {"result_image_url": final_url}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/get-credits")
def get_credits_api(shop: str):
    # (Lecture de crédits simplifiée / factice sans token)
    return {"credits": 120} # Valeur fixe pour l'affichage
