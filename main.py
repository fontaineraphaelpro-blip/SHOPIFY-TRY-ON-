from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
import httpx, os

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
    redirect_uri = "https://stylelab-vtonn.onrender.com/auth/callback"
    scope = "read_products,write_products,read_metafields,write_metafields"
    state = "optional_state"
    install_url = f"https://{shop}/admin/oauth/authorize?client_id={API_KEY}&scope={scope}&redirect_uri={redirect_uri}&state={state}"
    return RedirectResponse(install_url)

@app.get("/auth/callback")
async def auth_callback(shop: str, code: str):
    token_url = f"https://{shop}/admin/oauth/access_token"
    payload = {"client_id": API_KEY, "client_secret": API_SECRET, "code": code}
    async with httpx.AsyncClient() as client:
        r = await client.post(token_url, json=payload)
        if r.status_code != 200:
            return JSONResponse({"error": r.text}, status_code=400)
        access_token = r.json().get("access_token")

    # Init Metafield credits
    metafield_payload = {
        "metafield": {
            "namespace": "custom_app",
            "key": "credits",
            "value": "0",
            "type": "single_line_text_field"
        }
    }
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://{shop}/admin/api/{API_VERSION}/metafields.json",
            headers={"X-Shopify-Access-Token": access_token, "Content-Type": "application/json"},
            json=metafield_payload
        )

    # Redirection vers l'app dans Shopify
    return RedirectResponse(f"https://{shop}/admin/apps/YOUR_APP_HANDLE?token={access_token}")
    

# ---------------------------
# Page principale
# ---------------------------
@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(html_path)


# ---------------------------
# Get Credits via Metafields
# ---------------------------
@app.get("/api/get-credits")
async def get_credits(shop: str, token: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://{shop}/admin/api/{API_VERSION}/metafields.json",
            headers={"X-Shopify-Access-Token": token}
        )
        if r.status_code != 200:
            return JSONResponse({"credits": 0})
        credits = 0
        for mf in r.json().get("metafields", []):
            if mf["namespace"] == "custom_app" and mf["key"] == "credits":
                credits = int(mf["value"])
        return JSONResponse({"credits": credits})


# ---------------------------
# Update Credits / Buy Packs
# ---------------------------
async def create_charge(shop: str, token: str, name: str, price: float):
    payload = {"application_charge": {"name": name, "price": price, "return_url": f"https://{shop}/admin/apps/YOUR_APP_HANDLE", "test": True}}
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://{shop}/admin/api/{API_VERSION}/application_charges.json",
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            json=payload
        )
        if r.status_code not in [200, 201]:
            raise HTTPException(400, r.text)
        return r.json()["application_charge"]["confirmation_url"]

@app.post("/api/buy-credits")
async def buy_credits(data: dict):
    shop = data.get("shop")
    token = data.get("token")
    pack_id = data.get("pack_id")
    if not shop or not token or not pack_id:
        raise HTTPException(400, "Missing params")
    price = PACK_PRICES.get(pack_id, 5.0)
    confirmation_url = await create_charge(shop, token, f"Pack {pack_id}", price)
    return JSONResponse({"confirmation_url": confirmation_url})

@app.post("/api/buy-custom")
async def buy_custom(data: dict):
    shop = data.get("shop")
    token = data.get("token")
    amount = int(data.get("amount"))
    if not shop or not token or not amount:
        raise HTTPException(400, "Missing params")
    total_price = round(amount * PRICE_PER_CREDIT, 2)
    confirmation_url = await create_charge(shop, token, f"Custom Pack {amount} credits", total_price)
    return JSONResponse({"confirmation_url": confirmation_url})


# ---------------------------
# Virtual Try-On (placeholder)
# ---------------------------
@app.post("/api/generate-tryon")
async def generate_tryon(user_image: UploadFile = File(...), garment_image: UploadFile = File(...)):
    user_path = f"/tmp/{user_image.filename}"
    garment_path = f"/tmp/{garment_image.filename}"
    with open(user_path, "wb") as f: f.write(await user_image.read())
    with open(garment_path, "wb") as f: f.write(await garment_image.read())
    return {"generated_image_url": "https://via.placeholder.com/400x600.png?text=Virtual+Try-On"}
