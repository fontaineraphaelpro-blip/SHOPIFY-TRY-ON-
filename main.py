from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
import httpx, os, secrets

app = FastAPI()

API_KEY = os.environ.get("SHOPIFY_API_KEY")
API_SECRET = os.environ.get("SHOPIFY_API_SECRET")
API_VERSION = "2025-10"

PACK_PRICES = {"pack_10": 4.99, "pack_30": 12.99, "pack_100": 29.99}
PRICE_PER_CREDIT = 0.25

# ---------------------------
# OAuth Installation
# ---------------------------
@app.get("/auth")
async def install(shop: str):
    if not shop:
        raise HTTPException(400, "Missing shop param")
    state = secrets.token_urlsafe(16)
    redirect_uri = "https://YOUR_DOMAIN/auth/callback"
    scope = "read_products,write_products,read_metafields,write_metafields"
    install_url = f"https://{shop}/admin/oauth/authorize?client_id={API_KEY}&scope={scope}&redirect_uri={redirect_uri}&state={state}"
    return RedirectResponse(install_url)

@app.get("/auth/callback")
async def auth_callback(shop: str, code: str, state: str):
    token_url = f"https://{shop}/admin/oauth/access_token"
    payload = {"client_id": API_KEY, "client_secret": API_SECRET, "code": code}
    async with httpx.AsyncClient() as client:
        r = await client.post(token_url, json=payload)
        if r.status_code != 200:
            return JSONResponse({"error": r.text}, status_code=400)
        access_token = r.json().get("access_token")

    # Init credits
    metafield_payload = {"metafield":{"namespace":"custom_app","key":"credits","value":"0","type":"single_line_text_field"}}
    async with httpx.AsyncClient() as client:
        await client.post(f"https://{shop}/admin/api/{API_VERSION}/metafields.json",
                          headers={"X-Shopify-Access-Token": access_token,"Content-Type":"application/json"},
                          json=metafield_payload)

    redirect_app = f"https://{shop}/admin/apps/YOUR_APP_HANDLE?token={access_token}"
    return RedirectResponse(redirect_app)

# ---------------------------
# Admin Dashboard
# ---------------------------
@app.get("/", response_class=HTMLResponse)
async def index(shop: str = None, token: str = None):
    if not shop or not token:
        return HTMLResponse("<h1>Erreur : Shop ou token manquant</h1>")
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(html_path)

# ---------------------------
# Get Credits
# ---------------------------
@app.get("/api/get-credits")
async def get_credits(shop: str, token: str):
    headers = {"X-Shopify-Access-Token": token}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://{shop}/admin/api/{API_VERSION}/metafields.json", headers=headers)
        if r.status_code != 200:
            return JSONResponse({"credits": 0})
        credits = 0
        for mf in r.json().get("metafields", []):
            if mf["namespace"] == "custom_app" and mf["key"] == "credits":
                credits = int(mf["value"])
        return JSONResponse({"credits": credits})

# ---------------------------
# Buy Pack
# ---------------------------
@app.post("/api/buy-credits")
async def buy_credits(request: Request):
    data = await request.json()
    shop = data.get("shop")
    pack_id = data.get("pack_id")
    token = data.get("token")
    if not shop or not token or not pack_id:
        raise HTTPException(400,"Missing params")
    price = PACK_PRICES.get(pack_id, 5.0)
    charge_payload = {
        "application_charge":{
            "name": f"Pack {pack_id}",
            "price": price,
            "return_url": f"https://{shop}/admin/apps/YOUR_APP_HANDLE",
            "test": True
        }
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"https://{shop}/admin/api/{API_VERSION}/application_charges.json",
                              headers={"X-Shopify-Access-Token": token,"Content-Type":"application/json"},
                              json=charge_payload)
        if r.status_code not in [200,201]:
            return JSONResponse({"error": r.text}, status_code=400)
        confirmation_url = r.json()["application_charge"]["confirmation_url"]
        return JSONResponse({"confirmation_url": confirmation_url})

# ---------------------------
# Buy Custom Pack
# ---------------------------
@app.post("/api/buy-custom")
async def buy_custom(request: Request):
    data = await request.json()
    shop = data.get("shop")
    amount = int(data.get("amount"))
    token = data.get("token")
    if not shop or not token or not amount:
        raise HTTPException(400,"Missing params")
    total_price = round(amount * PRICE_PER_CREDIT,2)
    charge_payload = {
        "application_charge":{
            "name": f"Custom Pack {amount} credits",
            "price": total_price,
            "return_url": f"https://{shop}/admin/apps/YOUR_APP_HANDLE",
            "test": True
        }
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"https://{shop}/admin/api/{API_VERSION}/application_charges.json",
                              headers={"X-Shopify-Access-Token": token,"Content-Type":"application/json"},
                              json=charge_payload)
        if r.status_code not in [200,201]:
            return JSONResponse({"error": r.text}, status_code=400)
        confirmation_url = r.json()["application_charge"]["confirmation_url"]
        return JSONResponse({"confirmation_url": confirmation_url})

# ---------------------------
# Virtual Try-On AI
# ---------------------------
@app.post("/api/generate-tryon")
async def generate_tryon(user_image: UploadFile = File(...), garment_image: UploadFile = File(...)):
    # sauvegarde temporaire
    user_path = f"/tmp/{user_image.filename}"
    garment_path = f"/tmp/{garment_image.filename}"
    with open(user_path,"wb") as f: f.write(await user_image.read())
    with open(garment_path,"wb") as f: f.write(await garment_image.read())

    # TODO: appeler ton AI
    generated_image_url = "https://via.placeholder.com/400x600.png?text=Virtual+Try-On"
    return {"generated_image_url": generated_image_url}
