document.addEventListener("DOMContentLoaded", function() {
    
    // UI Init
    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    // --- RÉCUPÉRATION DES PARAMÈTRES URL ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode'); // 'client' (widget) ou null (admin)
    let shop = params.get('shop');
    const autoProductImage = params.get('product_image');

    // Sauvegarde et récupération du shop en session pour éviter les pertes au rafraîchissement
    try {
        if(!shop) shop = sessionStorage.getItem('shop');
        if(shop) sessionStorage.setItem('shop', shop);
    } catch(e) { console.log("SessionStorage inaccessible"); }

    // --- 1. SÉCURITÉ & TOKENS ---
    async function getSessionToken() {
        // En mode client (widget), on ne cherche pas de token Shopify Admin
        if (mode === 'client') return null; 
        
        if (window.shopify && window.shopify.id) {
            return await shopify.id.getToken();
        }
        return null;
    }

    async function authenticatedFetch(url, options = {}) {
        try {
            const token = await getSessionToken();
            const headers = options.headers || {};
            if (token) headers['Authorization'] = `Bearer ${token}`;
            
            const res = await fetch(url, { ...options, headers });
            
            // Si l'admin reçoit une erreur 401, on le redirige vers le login
            if (res.status === 401 && mode !== 'client') {
                if (shop) window.top.location.href = `/login?shop=${shop}`;
                return null;
            }
            return res;
        } catch (error) { throw error; }
    }

    // --- 2. INITIALISATION SELON LE MODE ---
    if(shop) {
        if (mode === 'client') initClientMode();
        else initAdminMode(shop);
    }

    // --- 3. LOGIQUE ADMIN (DASHBOARD) ---
    async function initAdminMode(s) {
        const res = await authenticatedFetch(`/api/get-data?shop=${s}`);
        if (res && res.ok) {
            const data = await res.json();
            
            // Mise à jour des compteurs (+1) et crédits
            const safeCredits = data.credits || 0;
            const safeLifetime = data.lifetime || 0;
            const safeUsage = data.usage || 0;
            const safeATC = data.atc || 0;

            updateDashboardStats(safeCredits);
            updateVIPStatus(safeLifetime);
            
            const tryEl = document.getElementById('stat-tryons');
            const atcEl = document.getElementById('stat-atc');
            if(tryEl) tryEl.innerText = safeUsage;
            if(atcEl) atcEl.innerText = safeATC;

            // Pré-remplissage Widget Studio
            if(data.widget) {
                document.getElementById('ws-text').value = data.widget.text || "Try It On Now ✨";
                document.getElementById('ws-color').value = data.widget.bg || "#000000";
                document.getElementById('ws-text-color').value = data.widget.color || "#ffffff";
                if(data.security) document.getElementById('ws-limit').value = data.security.max_tries || 5;
                window.updateWidgetPreview();
            }
        }
    }

    function updateDashboardStats(credits) {
        const el = document.getElementById('credits');
        if(el) el.innerText = credits;
        const supplyCard = document.querySelector('.smart-supply-card');
        const alertBadge = document.querySelector('.alert-badge');
        const daysEl = document.querySelector('.rs-value');
        if (supplyCard && daysEl) {
            let daysLeft = Math.floor(credits / 8); 
            if(daysLeft < 1) daysLeft = "< 1";
            daysEl.innerText = daysLeft + (daysLeft === "< 1" ? " Day" : " Days");
            if (credits < 20) {
                supplyCard.style.background = "#fff0f0";
                alertBadge.innerText = "CRITICAL";
                alertBadge.style.background = "#dc2626";
            } else {
                supplyCard.style.background = "#f0fdf4";
                alertBadge.innerText = "HEALTHY";
                alertBadge.style.background = "#16a34a";
            }
        }
    }

    function updateVIPStatus(lifetime) {
        const fill = document.querySelector('.vip-fill');
        const marker = document.querySelector('.vip-marker');
        let percent = (lifetime / 500) * 100;
        if(percent > 100) percent = 100;
        if(fill) fill.style.width = percent + "%";
        if(marker) marker.style.left = percent + "%";
        if(lifetime >= 500) {
            const title = document.querySelector('.vip-title strong');
            if(title) title.innerText = "Gold Member";
        }
    }

    window.saveSettings = async function(btn) {
        const oldText = btn.innerText;
        btn.innerText = "Saving..."; btn.disabled = true;
        const settings = {
            shop: shop,
            text: document.getElementById('ws-text').value,
            bg: document.getElementById('ws-color').value,
            color: document.getElementById('ws-text-color').value,
            max_tries: parseInt(document.getElementById('ws-limit').value) || 5
        };
        try {
            const res = await authenticatedFetch('/api/save-settings', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(settings)
            });
            if(res.ok) { btn.innerText = "Saved! ✅"; setTimeout(() => btn.innerText = oldText, 2000); } 
            else { alert("Save failed"); }
        } catch(e) { alert("Error saving"); }
        finally { btn.disabled = false; }
    };

    // --- 4. LOGIQUE CLIENT (WIDGET) ---
    function initClientMode() {
        document.body.classList.add('client-mode');
        const adminZone = document.getElementById('admin-only-zone');
        if(adminZone) adminZone.style.display = 'none';
        if (autoProductImage) {
            const img = document.getElementById('prevC');
            if(img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                if(img.parentElement) img.parentElement.querySelector('.empty-state').style.display = 'none';
            }
        }
    }

    // Tracking Ajout Panier (+1)
    window.trackATC = async function() {
        alert("Item added to cart!"); 
        if(shop) {
            try {
                // Fetch simple car le client n'a pas besoin de session admin
                await fetch('/api/track-atc', {
                    method: 'POST', 
                    headers: {'Content-Type': 'application/json'}, 
                    body: JSON.stringify({ shop: shop })
                });
            } catch(e) { console.error("Tracking Error", e); }
        }
    };

    // Prévisualisation des photos uploadées
    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                const content = img.parentElement.querySelector('.empty-state');
                if(content) content.style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    };

    // Mise à jour visuelle du bouton dans l'admin
    window.updateWidgetPreview = function() {
        const text = document.getElementById('ws-text').value;
        const color = document.getElementById('ws-color').value;
        const textColor = document.getElementById('ws-text-color').value;
        const btn = document.getElementById('ws-preview-btn');
        if(btn) {
            btn.style.backgroundColor = color;
            btn.style.color = textColor;
            const span = btn.querySelector('span');
            if(span) span.innerText = text;
        }
    }

    // --- 5. LE COEUR : GÉNÉRATION IA ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        if (!uFile) return alert("Please upload your photo.");
        if (!autoProductImage && !cFile) return alert("Please upload a garment.");

        // On bloque le bouton
        const oldText = btn.innerHTML;
        btn.disabled = true; 
        
        // On affiche le loader
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        document.getElementById('post-actions').style.display = 'none';

        // Texte de progression
        const textEl = document.getElementById('loader-text');
        textEl.innerText = "Uploading data...";

        try {
            const formData = new FormData();
            formData.append("shop", shop); // Crucial pour débiter le bon admin
            formData.append("person_image", uFile);
            if (cFile) formData.append("clothing_file", cFile); 
            else formData.append("clothing_url", autoProductImage); 
            formData.append("category", "upper_body");

            // Appel API (Direct fetch pour le client, authenticated pour l'admin)
            let res;
            if (mode === 'client') {
                res = await fetch('/api/generate', { method: 'POST', body: formData });
            } else {
                res = await authenticatedFetch('/api/generate', { method: 'POST', body: formData });
            }

            if (!res || !res.ok) {
                const errorData = await res.json();
                throw new Error(errorData.error || "Server Error");
            }

            textEl.innerText = "The AI is working...";
            const data = await res.json();
            
            if(data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => {
                    ri.style.display = 'block';
                    document.getElementById('loader').style.display = 'none';
                    document.getElementById('post-actions').style.display = 'block';
                };
            } else {
                throw new Error("No image returned");
            }
        } catch(e) { 
            console.error(e);
            alert("Error: " + e.message); 
            document.getElementById('loader').style.display = 'none';
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldText; 
        }
    };

    // --- 6. ACHATS CRÉDITS ---
    window.buy = async function(packId, customAmount = 0, btnElement = null) {
        if(!shop) return alert("Shop ID missing.");
        const body = { shop: shop, pack_id: packId, custom_amount: customAmount };
        try {
            const res = await authenticatedFetch('/api/buy-credits', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
            });
            const data = await res.json();
            if(data.confirmation_url) window.top.location.href = data.confirmation_url;
        } catch(e) { alert("Billing Error"); }
    };
    
    window.buyCustom = function(btn) { 
        const amt = document.getElementById('customAmount').value;
        if(amt < 200) return alert("Min 200 credits");
        window.buy('pack_custom', parseInt(amt), btn); 
    };
});
