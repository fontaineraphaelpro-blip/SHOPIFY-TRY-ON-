import os
import shopify
import requests
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import replicate

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST") # ex: https://shopify-try-on.onrender.com

SCOPES = ['write_script_tags', 'read_products', 'write_products']
API_VERSION = "2025-01" 
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

# CORS (Vital pour que le site client puisse parler au serveur)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mémoire vive pour les tokens
shop_sessions = {}

# --- LE CODE JAVASCRIPT DU WIDGET (STOCKÉ DANS PYTHON) ---
# On remplace l'URL API dynamiquement
WIDGET_JS_TEMPLATE = """
(function() {
    const API_URL = "REPLACE_WITH_HOST"; 
    
    // On ne lance le script que sur les pages produits
    if (!window.location.pathname.includes('/products/')) return;
    
    // Récupération automatique du shop
    let SHOP_URL = Shopify.shop;

    // STYLES
    const style = document.createElement('style');
    style.innerHTML = `
        .stylelab-float-btn {
            position: fixed; bottom: 20px; right: 20px;
            background: linear-gradient(135deg, #6366f1, #ec4899);
            color: white; padding: 15px 25px; border-radius: 50px;
            cursor: pointer; z-index: 2147483647;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            font-family: 'Arial', sans-serif; font-weight: bold;
            display: flex; align-items: center; gap: 10px;
            transition: transform 0.2s;
        }
        .stylelab-float-btn:hover { transform: scale(1.05); }
        .stylelab-modal {
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.5); z-index: 2147483647;
            justify-content: center; align-items: center; backdrop-filter: blur(5px);
        }
        .stylelab-content {
            background: white; padding: 30px; border-radius: 20px;
            width: 90%; max-width: 400px; text-align: center; position: relative;
            font-family: 'Arial', sans-serif; box-shadow: 0 20px 50px rgba(0,0,0,0.3);
        }
        .stylelab-close {
            position: absolute; top: 10px; right: 20px; font-size: 28px; cursor: pointer; color: #999;
        }
        .stylelab-upload-btn {
            background: #f8fafc; border: 2px dashed #cbd5e1; padding: 30px 20px;
            border-radius: 12px; margin: 20px 0; cursor: pointer; transition: 0.2s;
        }
        .stylelab-cta {
            background: #6366f1; color: white; border: none;
            padding: 15px 30px; border-radius: 50px; font-size: 16px; font-weight: bold;
            cursor: pointer; width: 100%; margin-top: 15px;
        }
        .stylelab-cta:disabled { background: #ccc; cursor: not-allowed; }
        .stylelab-preview { width: 100%; border-radius: 10px; display: none; margin-bottom: 15px; max-height: 300px; object-fit: contain; }
    `;
    document.head.appendChild(style);

    // UI ELEMENTS
    const btn = document.createElement('div');
    btn.className = 'stylelab-float-btn';
    btn.innerHTML = '<span>✨ Essayer ce vêtement</span>';
    btn.onclick = () => { document.querySelector('.stylelab-modal').style.display = 'flex'; };
    document.body.appendChild(btn);

    const modal = document.createElement('div');
    modal.className = 'stylelab-modal';
    modal.innerHTML = `
        <div class="stylelab-content">
            <span class="stylelab-close" onclick="this.closest('.stylelab-modal').style.display='none'">&times;</span>
            <h2 style="margin-top:0; color:#1f2937;">Cabine d'essayage IA</h2>
            <div class="stylelab-upload-btn" onclick="document.getElementById('sl-user-input').click()">
                <div id="sl-placeholder" style="color:#64748b;">📸 Cliquez pour ajouter votre photo</div>
                <img id="sl-user-preview" class="stylelab-preview">
            </div>
            <input type="file" id="sl-user-input" accept="image/*" style="display:none">
            <img id="sl-result" class="stylelab-preview" style="border: 2px solid #10b981; background:#f0fdf4;">
            <button id="sl-generate-btn" class="stylelab-cta">Générer l'essayage</button>
            <div id="sl-loading" style="display:none; margin-top:15px; color:#6366f1; font-weight:600;">✨ L'IA travaille... (15s)</div>
        </div>
    `;
    document.body.appendChild(modal);

    // LOGIC
    document.getElementById('sl-user-input').onchange = function(e) {
        if (e.target.files[0]) {
            const reader = new FileReader();
            reader.onload = (ev) => {
                document.getElementById('sl-user-preview').src = ev.target.result;
                document.getElementById('sl-user-preview').style.display = 'block';
                document.getElementById('sl-placeholder').style.display = 'none';
            };
            reader.readAsDataURL(e.target.files[0]);
        }
    };

    document.getElementById('sl-generate-btn').onclick = async function() {
        const userFile = document.getElementById('sl-user-input').files[0];
        if (!userFile) return alert("Ajoutez votre photo !");
        
        // Trouver image produit
        let productImgUrl = "";
        const ogImage = document.querySelector('meta[property="og:image"]');
        if (ogImage) productImgUrl = ogImage.content;
        else {
             const img = document.querySelector('.product__media img, .product-single__photo img, .product-image img');
             if(img) productImgUrl = img.src;
        }
        if (!productImgUrl) return alert("Image produit introuvable.");

        // UI Loading
        const btn = this;
        const loading = document.getElementById('sl-loading');
        btn.disabled = true; btn.style.display = 'none'; loading.style.display = 'block';

        try {
            const toBase64 = file => new Promise((res, rej) => {
                const r = new FileReader(); r.readAsDataURL(file); r.onload=()=>res(r.result); r.onerror=e=>rej(e);
            });
            const urlTob64 = async url => {
                try {
                    const r = await fetch(url); const b = await r.blob();
                    return new Promise(res => { const fr = new FileReader(); fr.readAsDataURL(b); fr.onloadend=()=>res(fr.result); });
                } catch(e) { return url; }
            };

            const userB64 = await toBase64(userFile);
            const prodB64 = await urlTob64(productImgUrl);

            const res = await fetch(`${API_URL}/api/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    shop: SHOP_URL,
                    person_image_url: userB64,
                    clothing_image_url: prodB64,
                    category: "upper_body"
                })
            });
            
            const data = await res.json();
            if (res.ok) {
                document.getElementById('sl-result').src = data.result_image_url;
                document.getElementById('sl-result').style.display = 'block';
                document.querySelector('.stylelab-upload-btn').style.display = 'none';
                loading.innerText = "✅ Terminé !";
            } else {
                alert("Erreur: " + (data.detail || "Erreur serveur"));
                btn.disabled = false; btn.style.display = 'block';
            }
        } catch(e) {
            console.error(e); alert("Erreur technique");
            btn.disabled = false; btn.style.display = 'block';
        } finally {
            loading.style.display = 'none';
        }
    };
})();
"""

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
        # On pointe vers la route Python qui sert le JS
        src = f"{HOST}/widget.js" 
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
    if clean_shop not in shop_sessions: return RedirectResponse(f"/login?shop={clean_shop}")
    return FileResponse('index.html')

# CETTE ROUTE REMPLACE LE FICHIER STATIC
@app.get("/widget.js")
def get_widget_js():
    # On injecte la vraie URL du serveur dans le JS
    js_content = WIDGET_JS_TEMPLATE.replace("REPLACE_WITH_HOST", HOST)
    return Response(content=js_content, media_type="application/javascript")

@app.get("/login")
def login(shop: str):
    clean_shop = clean_shop_url(shop)
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(clean_shop, API_VERSION)
    permission_url = session.create_permission_url(SCOPES, f"{HOST}/auth/callback")
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
    if not token: 
        raise HTTPException(400, "Maintenance: Veuillez ouvrir l'application dans l'admin Shopify.")

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
