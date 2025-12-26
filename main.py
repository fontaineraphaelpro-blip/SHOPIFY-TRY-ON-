import os, io, time, sqlite3, shopify, requests, replicate, binascii
from typing import Optional, Dict
from fastapi import FastAPI, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST_URL = os.getenv("HOST_URL", "").rstrip('/')
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()
templates = Jinja2Templates(directory=".")

# --- DATABASE PERSISTANTE ---
def init_db():
    with sqlite3.connect("database.db") as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS shops (domain TEXT PRIMARY KEY, token TEXT NOT NULL)")
init_db()

def get_token_db(shop):
    with sqlite3.connect("database.db") as conn:
        cur = conn.cursor()
        cur.execute("SELECT token FROM shops WHERE domain = ?", (shop,))
        row = cur.fetchone()
        return row[0] if row else None

# --- UTILS SHOPIFY ---
def get_shopify_session(shop, token):
    shopify.Session.setup(api_key=SHOPIFY_API_KEY, secret=SHOPIFY_API_SECRET)
    session = shopify.Session(shop, "2024-10", token)
    shopify.ShopifyResource.activate_session(session)

def get_meta(namespace, key, default=0):
    try:
        m = shopify.Metafield.find(namespace=namespace, key=key)
        return int(float(m[0].value)) if m else default
    except: return default

def set_meta(namespace, key, value, vtype="integer"):
    try:
        m = shopify.Metafield({'namespace': namespace, 'key': key, 'value': value, 'type': vtype})
        m.save()
    except Exception as e: print(f"Meta Error: {e}")

# --- CORS ---
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- ROUTES AUTH ---
@app.get("/login")
def login(shop: str):
    shop = shop.replace("https://", "").replace("http://", "").strip("/")
    redirect_uri = f"{HOST_URL}/auth/callback"
    permission_url = shopify.Session(shop, "2024-10").create_permission_url(["write_products", "read_products"], redirect_uri)
    return RedirectResponse(permission_url)

@app.get("/auth/callback")
def auth_callback(request: Request):
    params = dict(request.query_params)
    shop = params.get("shop")
    session = shopify.Session(shop, "2024-10")
    token = session.request_token(params)
    with sqlite3.connect("database.db") as conn:
        conn.execute("INSERT OR REPLACE INTO shops VALUES (?, ?)", (shop, token))
    return RedirectResponse(f"https://admin.shopify.com/store/{shop.split('.')[0]}/apps/{SHOPIFY_API_KEY}")

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "api_key": SHOPIFY_API_KEY})

# --- API DATA ---
@app.get("/api/get-data")
async def get_data(shop: str):
    token = get_token_db(shop)
    if not token: raise HTTPException(401)
    get_shopify_session(shop, token)
    return {"credits": get_meta("vton", "wallet", 10)}

# --- LE MOTEUR IA (DEBUGGÉ) ---
@app.post("/api/generate")
async def generate(
    shop: str = Form(...),
    person_image: UploadFile = File(...),
    clothing_url: str = Form(...)
):
    token = get_token_db(shop)
    if not token: return JSONResponse({"error": "Init required"}, 401)
    
    get_shopify_session(shop, token)
    credits = get_meta("vton", "wallet", 10)
    if credits < 1: return JSONResponse({"error": "No credits"}, 402)

    try:
        # FIX : Lecture correcte des bytes pour Replicate
        p_img_content = await person_image.read()
        
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": io.BytesIO(p_img_content), # On "rembobine" l'image
                "garm_img": clothing_url,
                "garment_des": "upper_body",
                "category": "upper_body",
                "crop": False
            }
        )
        
        # Débit crédit
        set_meta("vton", "wallet", credits - 1)
        
        res_url = str(output[0]) if isinstance(output, list) else str(output)
        return {"result_image_url": res_url}
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)
