document.addEventListener("DOMContentLoaded", function() {
    
    // UI Init
    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    // --- PARAMS & CONFIG ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image');
    // NOUVEAU: Récupérer le prix pour le tracking ROI
    const productPrice = parseFloat(params.get('price')) || 0;

    if(shop) {
        sessionStorage.setItem('shop', shop);
        if (mode === 'client') {
            initClientMode();
        } else {
            initAdminMode(shop);
        }
    }

    // --- AUTH FETCH ---
    async function getSessionToken() {
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
            if (res.status === 401) {
                if (shop) { window.top.location.href = `/login?shop=${shop}`; return null; }
            }
            return res;
        } catch (error) { throw error; }
    }

    // --- ADMIN MODE LOGIC ---
    async function initAdminMode(s) {
        // On récupère TOUTES les données d'un coup via la nouvelle route API
        const res = await authenticatedFetch(`/api/get-data?shop=${s}`);
        if (res && res.ok) {
            const data = await res.json();
            
            // 1. Stats de base & Alertes
            updateDashboardStats(data.credits);
            
            // 2. Statut VIP
            updateVIPStatus(data.lifetime);

            // 3. Stats ROI Réel
            updateROIStats(data.usage, data.revenue);

            // 4. Widget & Sécurité (Pré-remplissage)
            if(data.widget) {
                if(data.widget.text) document.getElementById('ws-text').value = data.widget.text;
                if(data.widget.bg) document.getElementById('ws-color').value = data.widget.bg;
                if(data.widget.color) document.getElementById('ws-text-color').value = data.widget.color;
                
                // Limite de sécurité
                if(data.security && data.security.max_tries) {
                    document.getElementById('ws-limit').value = data.security.max_tries;
                }
                
                window.updateWidgetPreview(); // Refresh visuel
            }
        }
    }

    function updateROIStats(usage, revenue) {
        const uEl = document.getElementById('roi-tryons');
        const rEl = document.getElementById('roi-revenue');
        if(uEl) uEl.innerText = usage;
        if(rEl) rEl.innerText = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(revenue);
    }

    function updateDashboardStats(credits) {
        const el = document.getElementById('credits');
        if(el) el.innerText = credits;

        // Smart Supply Logic
        const supplyCard = document.querySelector('.smart-supply-card');
        const alertBadge = document.querySelector('.alert-badge');
        const daysEl = document.querySelector('.rs-value');
        
        if (supplyCard && daysEl) {
            const daysLeft = Math.floor(credits / 5); // Simulation moyenne
            daysEl.innerText = daysLeft + (daysLeft === 1 ? " Day" : " Days");

            if (credits < 20) {
                supplyCard.style.background = "#fff0f0";
                alertBadge.innerText = "CRITICAL";
                alertBadge.style.background = "#dc2626";
            } else if (credits < 50) {
                supplyCard.style.background = "#fffbeb";
                alertBadge.innerText = "LOW STOCK";
                alertBadge.style.background = "#f59e0b";
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

    // --- SAVE SETTINGS (Widget + Limites) ---
    window.saveSettings = async function(btn) {
        const oldText = btn.innerText;
        btn.innerText = "Saving..."; btn.disabled = true;

        const settings = {
            shop: shop,
            text: document.getElementById('ws-text').value,
            bg: document.getElementById('ws-color').value,
            color: document.getElementById('ws-text-color').value,
            max_tries: parseInt(document.getElementById('ws-limit').value) // On sauvegarde la limite
        };

        try {
            const res = await authenticatedFetch('/api/save-settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(settings)
            });
            if(res.ok) {
                btn.innerText = "Saved! ✅";
                setTimeout(() => btn.innerText = oldText, 2000);
            } else {
                alert("Save failed");
            }
        } catch(e) { console.error(e); alert("Error saving"); }
        finally { btn.disabled = false; }
    };

    // --- TRACKING CONVERSION ---
    window.trackConversion = async function() {
        alert("Redirecting to Checkout..."); // Simulé pour l'UX
        
        if(shop && productPrice > 0) {
            try {
                await authenticatedFetch('/api/track-conversion', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ shop: shop, amount: productPrice })
                });
            } catch(e) { console.error("Tracking Error", e); }
        }
    };

    // --- CLIENT MODE ---
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

    // --- GENERATE (Avec gestion limite 429) ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        if (!uFile) return alert("Please upload your photo.");
        if (!autoProductImage && !cFile) return alert("Please upload a garment.");

        const oldText = btn.innerHTML;
        btn.disabled = true; 
        
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        document.getElementById('post-actions').style.display = 'none';

        const texts = ["Analyzing silhouette...", "Matching fabrics...", "Simulating drape...", "Rendering lighting..."];
        let step = 0;
        const textEl = document.getElementById('loader-text');
        const interval = setInterval(() => {
            if(step < texts.length) { textEl.innerText = texts[step]; step++; }
        }, 2500);

        try {
            const formData = new FormData();
            formData.append("shop", shop || "demo");
            formData.append("person_image", uFile);
            if (cFile) formData.append("clothing_file", cFile); 
            else formData.append("clothing_url", autoProductImage); 
            formData.append("category", "upper_body");

            const res = await authenticatedFetch('/api/generate', { method: 'POST', body: formData });

            clearInterval(interval);

            if (!res) return;
            // Gestion erreur LIMITE
            if (res.status === 429) { 
                alert("Daily try-on limit reached. Please come back tomorrow."); 
                document.getElementById('loader').style.display = 'none';
                return;
            }
            if (res.status === 402) { alert("Not enough credits!"); btn.disabled = false; btn.innerHTML = oldText; return; }
            if (!res.ok) throw new Error("Server Error");

            const data = await res.json();
            
            if(data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => {
                    ri.style.display = 'block';
                    document.getElementById('loader').style.display = 'none';
                    document.getElementById('post-actions').style.display = 'block';
                };
                if(data.new_credits !== undefined) {
                    // Update simple du compteur crédit si admin
                    const cel = document.getElementById('credits');
                    if(cel) cel.innerText = data.new_credits;
                }
            } else {
                alert("Error: " + (data.error || "Unknown"));
                document.getElementById('loader').style.display = 'none';
            }
        } catch(e) { 
            clearInterval(interval);
            console.error(e);
            alert("Network Error"); 
            document.getElementById('loader').style.display = 'none';
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldText; 
        }
    };

    window.buy = async function(packId, customAmount = 0, btnElement = null) {
        if(!shop) return alert("Shop ID missing.");
        const btn = btnElement;
        const oldText = btn ? btn.innerText : "...";
        if(btn) { btn.innerText = "Processing..."; btn.disabled = true; }

        try {
            const body = { shop: shop, pack_id: packId, custom_amount: customAmount };
            const res = await authenticatedFetch('/api/buy-credits', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
            });
            if (!res) return;
            const data = await res.json();
            if(data.confirmation_url) window.top.location.href = data.confirmation_url;
            else { alert("Error: " + (data.error || "Unknown")); if(btn) { btn.innerText = oldText; btn.disabled = false; } }
        } catch(e) {
            console.error(e); alert("Network Error"); if(btn) { btn.innerText = oldText; btn.disabled = false; }
        }
    };

    window.buyCustom = function(btnElement) {
        const amount = document.getElementById('customAmount').value;
        if(amount < 200) return alert("Min 200 credits");
        window.buy('pack_custom', parseInt(amount), btnElement);
    }
});
