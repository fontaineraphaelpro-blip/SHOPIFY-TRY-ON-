import os
import io
import time
import shopify
import requests
import replicate
from typing import Optional, Dict
from fastapi import FastAPI, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, MetaData, Table, select

# --- CONFIG ---
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
HOST = os.getenv("HOST", "https://ton-app.onrender.com").rstrip('/')
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

app = FastAPI()
templates = Jinja2Templates(directory=".")

# --- DB SETUP (Minimaliste pour éviter les crashs) ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if not DATABASE_URL: DATABASE_URL = "sqlite:///./local_storage.db"

engine = create_engine(DATABASE_URL)
metadata = MetaData()
shops_table = Table("shops", metadata, Column("domain", String, primary_key=True), Column("token", String))
metadata.create_all(engine)

# --- MIDDLEWARE & CORS (LA CLÉ DU PROBLÈME) ---
# On autorise TOUT pour être sûr que le navigateur ne bloque pas
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- FIX SÉCURITÉ IFRAME ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "frame-ancestors https://*.myshopify.com https://admin.shopify.com;"
    return response

# --- ROUTES ---

# 1. Route de Test (Pour vérifier si le serveur est vivant)
@app.get("/api/health")
def health():
    return {"status": "alive"}

# 2. Gestion explicite de OPTIONS (Pour calmer le navigateur)
@app.options("/api/generate")
def options_generate():
    return JSONResponse(content={"ok": "go"}, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*"
    })

# 3. La génération (Logique blindée)
@app.post("/api/generate")
async def generate(
    shop: str = Form(...),
    person_image: UploadFile = File(...),
    clothing_url: Optional[str] = Form(None),
    clothing_file: Optional[UploadFile] = File(None)
):
    print(f"🔥 REQUÊTE REÇUE pour {shop}")
    
    try:
        # 1. Lecture Images
        person_bytes = await person_image.read()
        
        garment_file = None
        if clothing_url:
            c_url = str(clothing_url)
            if c_url.startswith("//"): c_url = "https:" + c_url
            print(f"📥 Téléchargement URL: {c_url}")
            resp = requests.get(c_url, timeout=10)
            if resp.status_code == 200:
                garment_file = io.BytesIO(resp.content)
            else:
                return JSONResponse({"error": "Impossible de télécharger le vêtement"}, status_code=400)
        elif clothing_file:
            print("📥 Fichier vêtement reçu")
            g_bytes = await clothing_file.read()
            garment_file = io.BytesIO(g_bytes)
        
        if not garment_file:
             return JSONResponse({"error": "Pas de vêtement fourni"}, status_code=400)

        # 2. Envoi Replicate
        print("🚀 Envoi à Replicate...")
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": io.BytesIO(person_bytes),
                "garm_img": garment_file,
                "category": "upper_body"
            }
        )
        
        if not output: return JSONResponse({"error": "L'IA n'a rien renvoyé"}, status_code=500)
        
        res_url = str(output[0]) if isinstance(output, list) else str(output)
        print(f"✅ SUCCÈS: {res_url}")
        
        return {"result_image_url": res_url}

    except Exception as e:
        print(f"❌ CRASH: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

# --- ESSENTIELS FRONTEND ---
@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "api_key": SHOPIFY_API_KEY})

@app.get("/login")
def login(shop: str):
    return RedirectResponse(f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope=read_products&redirect_uri={HOST}/auth/callback")

@app.get("/auth/callback")
def callback(shop: str, code: str):
    # Sauvegarde simplifiée pour débloquer
    with engine.connect() as conn:
        try:
            url = f"https://{shop}/admin/oauth/access_token"
            r = requests.post(url, json={"client_id": SHOPIFY_API_KEY, "client_secret": SHOPIFY_API_SECRET, "code": code})
            token = r.json().get('access_token')
            # Sauvegarde brute
            try: conn.execute(shops_table.insert().values(domain=shop, token=token))
            except: conn.execute(shops_table.update().where(shops_table.c.domain == shop).values(token=token))
            conn.commit()
        except: pass
    return RedirectResponse(f"https://admin.shopify.com/store/{shop.replace('.myshopify.com','')}/apps/{SHOPIFY_API_KEY}")

@app.get("/api/get-data")
def get_data(): return {"credits": 999, "usage": 0} # Crédits illimités pour le test
@app.post("/api/buy-credits")
def buy(): return {"confirmation_url": "https://google.com"} # Fake buy pour test
