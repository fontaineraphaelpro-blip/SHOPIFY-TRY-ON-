import os
import io
import time
import sqlite3
import shopify
import replicate
from typing import Optional, Dict
from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# --- CONFIGURATION ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN") 

# MODÈLE CORRIGÉ (Version stable vérifiée)
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()

# Autoriser toutes les origines (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=".")

# --- MIDDLEWARE CRITIQUE POUR L'IFRAME ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    shop = request.query_params.get("shop")
    if shop:
        policy = f"frame-ancestors https://{shop} https://admin.shopify.com https://*.myshopify.com;"
    else:
        policy = "frame-ancestors *;"
    response.headers["Content-Security-Policy"] = policy
    response.headers["X-Frame-Options"] = "ALLOWALL"
    return response

# --- DATABASE ---
def get_token_db(shop):
    try:
        with sqlite3.connect("database.db") as conn:
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS shops (domain TEXT PRIMARY KEY, token TEXT)")
            cur.execute("SELECT token FROM shops WHERE domain = ?", (shop,))
            row = cur.fetchone()
            return row[0] if row else None
    except: return None

def clean_shop(url):
    return url.replace("https://", "").replace("http://", "").strip("/") if url else ""

# --- ROUTES ---
@app.get("/styles.css")
def styles(): return FileResponse('styles.css', media_type='text/css')

@app.get("/app.js")
def javascript(): return HTMLResponse("") 

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --- API GENERATE ---
@app.post("/api/generate")
async def generate(
    shop: str = Form(...),
    person_image: UploadFile = File(...),
    clothing_url: str = Form(...)
):
    print(f"🚀 REÇU: Shop={shop} | Vêtement={clothing_url}")
    
    shop = clean_shop(shop)
    token = get_token_db(shop)
    
    if not token:
        print("⚠️ Token manquant (Debug Mode)")

    try:
        person_bytes = await person_image.read()
        
        print(f"🤖 Envoi à Replicate ({MODEL_ID})...")
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": io.BytesIO(person_bytes),
                "garm_img": clothing_url,
                "garment_des": "upper_body",
                "category": "upper_body",
                "crop": False,
                "seed": 42,
                "steps": 30 
            }
        )
        
        result_url = str(output[0]) if isinstance(output, list) else str(output)
        print(f"✅ SUCCÈS: {result_url}")

        return {"result_image_url": result_url}

    except Exception as e:
        print(f"🔥 CRASH: {str(e)}")
        # Affiche l'erreur exacte dans le widget pour comprendre
        return JSONResponse({"error": f"Erreur IA: {str(e)}"}, status_code=500)

