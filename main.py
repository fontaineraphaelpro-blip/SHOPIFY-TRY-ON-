import os
import io
import time
import hmac
import hashlib
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import replicate
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

# ==========================================
# CONFIGURATION
# ==========================================
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/vton")
MODEL_ID = "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"

# ==========================================
# DATABASE SETUP (PostgreSQL)
# ==========================================
Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class Shop(Base):
    __tablename__ = "shops"
    domain = Column(String, primary_key=True)
    access_token = Column(String, nullable=False)
    credits = Column(Integer, default=0)
    lifetime_credits = Column(Integer, default=0)
    total_tryons = Column(Integer, default=0)
    total_atc = Column(Integer, default=0)
    max_tries_per_user = Column(Integer, default=5)
    widget_text = Column(String, default="Try It On Now ✨")
    widget_bg = Column(String, default="#000000")
    widget_color = Column(String, default="#ffffff")
    installed_at = Column(DateTime, default=datetime.utcnow)

class TryOnLog(Base):
    __tablename__ = "tryon_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    shop = Column(String, nullable=False)
    customer_ip = Column(String)
    product_id = Column(String)
    success = Column(Boolean, default=True)
    latency_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

class RateLimit(Base):
    __tablename__ = "rate_limits"
    id = Column(Integer, primary_key=True, autoincrement=True)
    shop = Column(String, nullable=False)
    customer_ip = Column(String, nullable=False)
    date = Column(String, nullable=False)  # Format: YYYY-MM-DD
    count = Column(Integer, default=0)

Base.metadata.create_all(engine)

# ==========================================
# FASTAPI APP
# ==========================================
app = FastAPI(title="VTON AI Backend", version="2.0")

# CORS minimal (App Proxy handled by Shopify)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://*.myshopify.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ==========================================
# HELPERS
# ==========================================
def verify_shopify_proxy(params: dict) -> bool:
    """Vérifie que la requête vient bien de Shopify App Proxy"""
    signature = params.pop('signature', None)
    if not signature:
        return False
    
    # Reconstruire la query string
    sorted_params = sorted(params.items())
    query_string = '&'.join([f"{k}={v}" for k, v in sorted_params])
    
    # Calculer le HMAC
    computed = hmac.new(
        SHOPIFY_API_SECRET.encode(),
        query_string.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(computed, signature)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# APP PROXY ROUTES (PUBLIC STOREFRONT)
# ==========================================

@app.get("/apps/tryon/widget.js")
async def serve_widget():
    """Sert le widget JavaScript optimisé"""
    js_content = """
(function() {
    'use strict';
    
    const WIDGET_CONFIG = {
        apiEndpoint: window.location.origin + '/apps/tryon/generate',
        buttonSelector: '[data-vton-button]',
        imageSelector: '[data-vton-image]'
    };
    
    class VTONWidget {
        constructor() {
            this.shop = window.Shopify?.shop || '';
            this.init();
        }
        
        init() {
            document.addEventListener('DOMContentLoaded', () => {
                this.injectButton();
            });
        }
        
        injectButton() {
            const productForm = document.querySelector('form[action*="/cart/add"]');
            if (!productForm) return;
            
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'vton-try-it-on';
            btn.innerHTML = '👗 Try It On';
            btn.onclick = () => this.openModal();
            
            productForm.insertAdjacentElement('beforebegin', btn);
        }
        
        async openModal() {
            // Modal implementation
            console.log('Open VTON modal');
        }
        
        async generate(personImage, garmentImage) {
            const formData = new FormData();
            formData.append('person_image', personImage);
            formData.append('garment_image', garmentImage);
            
            const response = await fetch(WIDGET_CONFIG.apiEndpoint, {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error('Generation failed');
            }
            
            return await response.json();
        }
    }
    
    new VTONWidget();
})();
"""
    return Response(
        content=js_content,
        media_type="application/javascript",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*"
        }
    )

class ProxyGenerateRequest(BaseModel):
    person_image_base64: str
    clothing_url: Optional[str] = None
    clothing_file_base64: Optional[str] = None
    product_id: Optional[str] = None

@app.post("/apps/tryon/generate")
async def proxy_generate(
    request: Request,
    req: ProxyGenerateRequest
):
    """
    Route App Proxy pour générer un try-on
    Accessible via: https://SHOP.myshopify.com/apps/tryon/generate
    """
    start_time = time.time()
    
    # 1. Extraire le shop depuis les query params Shopify
    params = dict(request.query_params)
    shop = params.get('shop', '').replace('.myshopify.com', '') + '.myshopify.com'
    
    if not shop:
        return JSONResponse({"error": "Shop parameter missing"}, status_code=400)
    
    # 2. Vérifier signature Shopify (optionnel mais recommandé)
    # if not verify_shopify_proxy(params):
    #     return JSONResponse({"error": "Invalid signature"}, status_code=403)
    
    db = next(get_db())
    
    # 3. Récupérer la config shop
    shop_record = db.query(Shop).filter(Shop.domain == shop).first()
    if not shop_record:
        return JSONResponse({"error": "Shop not found"}, status_code=404)
    
    # 4. Vérifier crédits
    if shop_record.credits < 1:
        return JSONResponse({"error": "Insufficient credits"}, status_code=402)
    
    # 5. Rate limiting par IP
    client_ip = request.client.host
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    rate_limit = db.query(RateLimit).filter(
        RateLimit.shop == shop,
        RateLimit.customer_ip == client_ip,
        RateLimit.date == today
    ).first()
    
    if not rate_limit:
        rate_limit = RateLimit(shop=shop, customer_ip=client_ip, date=today, count=0)
        db.add(rate_limit)
    
    if rate_limit.count >= shop_record.max_tries_per_user:
        return JSONResponse({"error": "Daily limit reached"}, status_code=429)
    
    try:
        # 6. Conversion Base64 -> BytesIO
        import base64
        person_bytes = base64.b64decode(req.person_image_base64)
        person_file = io.BytesIO(person_bytes)
        
        garment_input = None
        if req.clothing_file_base64:
            garment_bytes = base64.b64decode(req.clothing_file_base64)
            garment_input = io.BytesIO(garment_bytes)
        elif req.clothing_url:
            garment_input = req.clothing_url
            if garment_input.startswith("//"):
                garment_input = "https:" + garment_input
        else:
            return JSONResponse({"error": "No garment provided"}, status_code=400)
        
        # 7. Appel Replicate
        output = replicate.run(
            MODEL_ID,
            input={
                "human_img": person_file,
                "garm_img": garment_input,
                "garment_des": "upper_body",
                "category": "upper_body"
            }
        )
        
        result_url = str(output[0]) if isinstance(output, list) else str(output)
        
        # 8. Mise à jour stats
        shop_record.credits -= 1
        shop_record.total_tryons += 1
        rate_limit.count += 1
        
        latency = int((time.time() - start_time) * 1000)
        
        log = TryOnLog(
            shop=shop,
            customer_ip=client_ip,
            product_id=req.product_id,
            success=True,
            latency_ms=latency
        )
        db.add(log)
        db.commit()
        
        return JSONResponse({
            "result_image_url": result_url,
            "credits_remaining": shop_record.credits
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        
        log = TryOnLog(
            shop=shop,
            customer_ip=client_ip,
            product_id=req.product_id,
            success=False,
            latency_ms=int((time.time() - start_time) * 1000)
        )
        db.add(log)
        db.commit()
        
        return JSONResponse({"error": str(e)}, status_code=500)

# ==========================================
# ADMIN API ROUTES (Session Token Auth)
# ==========================================

def verify_session_token(authorization: str) -> Optional[str]:
    """Vérifie le Session Token Shopify et retourne le shop"""
    # Implementation complète avec JWT validation
    # Pour l'instant, extraction basique
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    # TODO: Decode JWT with Shopify public key
    # Pour l'instant, retourner None (à implémenter)
    return None

@app.get("/api/admin/dashboard")
async def get_dashboard(
    authorization: str = Header(None),
    shop: str = None
):
    """Dashboard analytics pour l'admin Shopify"""
    # shop = verify_session_token(authorization)
    # if not shop:
    #     raise HTTPException(status_code=401, detail="Unauthorized")
    
    if not shop:
        raise HTTPException(status_code=400, detail="Shop parameter required")
    
    db = next(get_db())
    shop_record = db.query(Shop).filter(Shop.domain == shop).first()
    
    if not shop_record:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Analytics
    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    logs_today = db.query(TryOnLog).filter(
        TryOnLog.shop == shop,
        TryOnLog.created_at >= today
    ).all()
    
    logs_week = db.query(TryOnLog).filter(
        TryOnLog.shop == shop,
        TryOnLog.created_at >= week_ago
    ).all()
    
    logs_month = db.query(TryOnLog).filter(
        TryOnLog.shop == shop,
        TryOnLog.created_at >= month_ago
    ).all()
    
    avg_latency = sum(log.latency_ms for log in logs_month) / len(logs_month) if logs_month else 0
    error_rate = sum(1 for log in logs_month if not log.success) / len(logs_month) if logs_month else 0
    
    return {
        "credits": shop_record.credits,
        "lifetime_credits": shop_record.lifetime_credits,
        "total_tryons": shop_record.total_tryons,
        "total_atc": shop_record.total_atc,
        "analytics": {
            "tryons_today": len(logs_today),
            "tryons_week": len(logs_week),
            "tryons_month": len(logs_month),
            "avg_latency_ms": int(avg_latency),
            "error_rate": round(error_rate * 100, 2),
            "conversion_rate": round((shop_record.total_atc / shop_record.total_tryons * 100) if shop_record.total_tryons > 0 else 0, 2)
        },
        "widget": {
            "text": shop_record.widget_text,
            "bg": shop_record.widget_bg,
            "color": shop_record.widget_color
        }
    }

@app.post("/api/admin/settings")
async def save_settings(
    request: Request,
    shop: str = None
):
    """Sauvegarde des settings widget"""
    if not shop:
        raise HTTPException(status_code=400, detail="Shop parameter required")
    
    data = await request.json()
    
    db = next(get_db())
    shop_record = db.query(Shop).filter(Shop.domain == shop).first()
    
    if not shop_record:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    shop_record.widget_text = data.get('text', shop_record.widget_text)
    shop_record.widget_bg = data.get('bg', shop_record.widget_bg)
    shop_record.widget_color = data.get('color', shop_record.widget_color)
    shop_record.max_tries_per_user = data.get('max_tries', shop_record.max_tries_per_user)
    
    db.commit()
    
    return {"success": True}

# ==========================================
# HEALTH CHECK
# ==========================================
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
