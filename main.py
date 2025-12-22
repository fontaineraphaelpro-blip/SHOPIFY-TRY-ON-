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
HOST = os.getenv("HOST") 

SCOPES = ['write_script_tags', 'read_products', 'write_products']
API_VERSION = "2025-01" 
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

# Autoriser la boutique à parler au serveur (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

shop_sessions = {}

# --- WIDGET CLIENT (JAVASCRIPT) ---
# Ce code est envoyé au navigateur du client
WIDGET_JS = """
(function() {
    const API_URL = "REPLACE_HOST";
    
    if (!window.location.pathname.includes('/products/')) return;
    
    // 1. CSS
    const s = document.createElement('style');
    s.innerHTML = `
        .sl-btn { position: fixed; bottom: 20px; right: 20px; background: linear-gradient(135deg, #6366f1, #ec4899); color: white; padding: 15px 25px; border-radius: 50px; cursor: pointer; z-index: 2147483647; font-family: sans-serif; font-weight: bold; box-shadow: 0 10px 25px rgba(0,0,0,0.2); transition: transform 0.2s; display: flex; gap: 10px; align-items: center; }
        .sl-btn:hover { transform: scale(1.05); }
        .sl-modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 2147483647; justify-content: center; align-items: center; backdrop-filter: blur(5px); }
        .sl-content { background: white; padding: 30px; border-radius: 20px; width: 90%; max-width: 400px; text-align: center; position: relative; font-family: sans-serif; box-shadow: 0 20px 50px rgba(0,0,0,0.3); }
        .sl-close { position: absolute; top: 10px; right: 20px; font-size: 28px; cursor: pointer; color: #999; }
        .sl-upload { background:#f8fafc; border: 2px dashed #cbd5e1; padding: 20px; border-radius: 10px; margin: 20px 0; cursor: pointer; transition:0.2s; }
        .sl-upload:hover { background:#eef2ff; border-color:#6366f1; }
        .sl-go { background: #6366f1; color: white; border: none; padding: 15px 30px; border-radius: 50px; font-weight: bold; cursor: pointer; width: 100%; font-size: 16px; margin-top:10px; }
        .sl-img { width: 100%; display: none; border-radius: 10px; margin-bottom: 15px; max-height:300px; object-fit:contain; }
        .sl-txt { color: #64748b; font-size: 14px; }
    `;
    document.head.appendChild(s);

    // 2. BOUTON
    const btn = document.createElement('div');
    btn.className = 'sl-btn';
    btn.innerHTML = '<span>✨ Essayer virtuellement</span>';
    btn.onclick = () => document.querySelector('.sl-modal').style.display = 'flex';
    document.body.appendChild(btn);

    // 3. MODALE
    const modal = document.createElement('div');
    modal.className = 'sl-modal';
    modal.innerHTML = `
        <div class="sl-content">
            <span class="sl-close" onclick="this.closest('.sl-modal').style.display='none'">&times;</span>
            <h2 style="margin:0 0 5px 0; color:#1f2937;">Cabine d'Essayage</h2>
            <div class="sl-upload" onclick="document.getElementById('sl-in').click()">
                <div id="sl-placeholder" class="sl-txt">📸 Cliquez pour ajouter votre photo</div>
                <img id="sl-prev" class="sl-img">
            </div>
            <input type="file" id="sl-in" accept="image/*" style="display:none">
            <img id="sl-res" class="sl-img" style="border:2px solid #10b981; background:#f0fdf4;">
            <button id="sl-go" class="sl-go">Générer l'essayage</button>
            <div id="sl-load" style="display:none; margin-top:15px; color:#6366f1; font-weight:bold;">✨ L'IA travaille... (15s)</div>
        </div>
    `;
    document.body.appendChild(modal);

    // 4. LOGIQUE
    document.getElementById('sl-in').onchange = e => {
        if(e.target.files[0]) {
            const r = new FileReader();
            r.onload = ev => {
                document.getElementById('sl-prev').src = ev.target.result;
                document.getElementById('sl-prev').style.display = 'block';
                document.getElementById('sl-placeholder').style.display = 'none';
            };
            r.readAsDataURL(e.target.files[0]);
        }
    };

    document.getElementById('sl-go').onclick = async function() {
        const file = document.getElementById('sl-in').files[0];
        if(!file) return alert("Merci d'ajouter votre photo !");
        
        let prodImg = "";
        const meta = document.querySelector('meta[property="og:image"]');
        if(meta) prodImg = meta.content;
        else { const i = document.querySelector('.product__media img, .product-single__photo img'); if(i) prodImg = i.src; }
        
        if(!prodImg) return alert("Impossible de trouver l'image du produit.");

        this.disabled = true; this.style.opacity = '0.7'; 
        document.getElementById('sl-load').style.display = 'block';

        const toBase64 = f => new Promise(r => { const fr=new FileReader(); fr.onload=()=>r(fr.result); fr.readAsDataURL(f); });
        const urlTo64 = async u => { try { const r=await fetch(u); const b=await r.blob(); return await toBase64(b); } catch(e){ return u; } };

        try {
            const u64 = await toBase64(file);
            const p64 = await urlTo64(prodImg);
            
            const req = await fetch(API_URL + '/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    shop: Shopify.shop,
                    person_image_url: u64,
                    clothing_image_url: p64,
                    category: 'upper_body'
                })
            });
            const data = await req.json();
            
            if(req.ok) {
                document.getElementById('sl-res').src = data.result_image_url;
                document.getElementById('sl-res').style.display = 'block';
                document.querySelector('.sl-upload').style.display = 'none';
                document.getElementById('sl-load').innerHTML = "✅ Essayage terminé !";
                document.getElementById('sl-load').style.color = "#10b981";
                this.style.display = 'none';
            } else {
                alert("Oups : " + (data.detail || "Erreur technique"));
                this.disabled = false; this.style.opacity = '1';
                document.getElementById('sl-load').style.display = 'none';
            }
        } catch(e) { 
            console.error(e); alert("Erreur de connexion au serveur."); 
            this.disabled = false; this.style.opacity = '1';
            document.getElementById('sl-load').style.display = 'none';
        }
    };
})();
"""

# --- BACKEND ---

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
    except: return 0

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
    except: pass

def inject_script_tag(shop_url, token):
    try:
        session = shopify.Session(shop_url, API_VERSION, token)
        shopify.ShopifyResource.activate_session(session)
        existing = shopify.ScriptTag.find()
        src = f"{HOST}/widget.js"
        if not any(s.src == src for s in existing):
            shopify.ScriptTag.create({"event": "onload", "src": src})
            print(f"✅ Widget client injecté sur {shop_url}")
    except Exception as e:
        print(f"Erreur injection: {e}")

# --- ROUTES ---

@app.get("/")
def index(shop: str = None):
    if not shop: return HTMLResponse("Paramètre shop manquant")
    clean_shop = clean_shop_url(shop)
    if clean_shop not in shop_sessions:
        return RedirectResponse(f"/login?shop={clean_shop}")
    return FileResponse('index.html')

@app.get("/widget.js")
def get_widget_js():
    return Response(content=WIDGET_JS.replace("REPLACE_HOST", HOST), media_type="application/javascript")

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
        url = f"https://{clean_shop}/admin/oauth/access_token"
        payload = { "client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code }
        res = requests.post(url, json=payload)
        
        if res.status_code == 200:
            token = res.json().get('access_token')
            shop_sessions[clean_shop] = token
            curr = get_shopify_credits(clean_shop, token)
            if curr == 0: update_shopify_credits(clean_shop, token, 3)
            inject_script_tag(clean_shop, token)
            return RedirectResponse(f"https://admin.shopify.com/store/{clean_shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")
        else:
            return HTMLResponse(f"Erreur Shopify: {res.text}")
    except Exception as e:
        return HTMLResponse(f"Erreur: {e}")

# --- API ---

@app.get("/api/get-credits")
def get_credits_api(shop: str):
    clean_shop = clean_shop_url(shop)
    token = shop_sessions.get(clean_shop)
    if not token: raise HTTPException(401, "Reload needed")
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
    except: return HTMLResponse("Erreur")

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
        raise HTTPException(400, "Maintenance serveur")

    current = get_shopify_credits(clean_shop, token)
    if current < 1: raise HTTPException(402, "Crédits épuisés")

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
