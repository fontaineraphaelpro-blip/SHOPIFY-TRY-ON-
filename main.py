from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
import httpx
import os

app = FastAPI()

SHOPIFY_API_VERSION = "2025-10"
API_KEY = os.environ.get("SHOPIFY_API_KEY")
API_SECRET = os.environ.get("SHOPIFY_API_SECRET")

# ---------------------------
# Middleware pour CSP / iframe Shopify
# ---------------------------
@app.middleware("http")
async def shopify_csp(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "frame-ancestors https://*.myshopify.com https://admin.shopify.com;"
    return response

# ---------------------------
# Page principale
# ---------------------------
@app.get("/", response_class=HTMLResponse)
async def index(shop: str = None, id_token: str = None):
    if not shop or not id_token:
        return HTMLResponse("<h1>Erreur : Shop ou id_token manquant</h1>")
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(html_path)

# ---------------------------
# Endpoint pour récupérer les crédits
# ---------------------------
@app.get("/api/get-credits")
async def get_credits(shop: str, authorization: str = None):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")

    token = authorization.replace("Bearer ", "")
    
    # On lit les metafields Shopify du shop pour récupérer les crédits
    metafields_url = f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}/metafields.json"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(metafields_url, headers=headers)
        if r.status_code != 200:
            return JSONResponse({"credits": 10})  # fallback
        data = r.json()
        credits = 10  # default
        for mf in data.get("metafields", []):
            if mf.get("key") == "credits":
                credits = int(mf.get("value", 10))
        return JSONResponse({"credits": credits})

# ---------------------------
# Endpoint pour acheter des crédits
# ---------------------------
@app.post("/api/buy-credits")
async def buy_credits(request: Request, authorization: str = None):
    data = await request.json()
    shop = data.get("shop")
    pack_id = data.get("pack_id")

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.replace("Bearer ", "")

    # Création d'un ApplicationCharge Shopify
    charge_payload = {
        "recurring_application_charge": {
            "name": f"Pack {pack_id}",
            "price": 5.0,  # tu peux adapter le prix selon le pack
            "return_url": f"https://{shop}/admin/apps/your-app",
            "test": True  # remove en prod
        }
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}/recurring_application_charges.json",
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            json=charge_payload
        )
        if r.status_code not in [200, 201]:
            return JSONResponse({"error": r.text}, status_code=400)
        charge = r.json().get("recurring_application_charge", {})
        confirmation_url = charge.get("confirmation_url")
        return JSONResponse({"confirmation_url": confirmation_url})

# ---------------------------
# Endpoint pour créer / mettre à jour les metafields
# ---------------------------
@app.post("/api/set-metafield")
async def set_metafield(shop: str, key: str, value: str, authorization: str = None):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.replace("Bearer ", "")

    # Création ou mise à jour du metafield
    metafield_payload = {
        "metafield": {
            "namespace": "custom_app",
            "key": key,
            "value": value,
            "type": "single_line_text_field"
        }
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}/metafields.json",
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            json=metafield_payload
        )
        if r.status_code not in [200, 201]:
            return JSONResponse({"error": r.text}, status_code=400)
        return JSONResponse({"success": True})
