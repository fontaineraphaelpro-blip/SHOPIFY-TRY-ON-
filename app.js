document.addEventListener("DOMContentLoaded", function() {

    // --- CONFIGURATION ---
    // Votre URL backend Render
    const API_BASE_URL = "https://stylelab-vtonn.onrender.com";

    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image');

    // DÉTECTION DU SHOP
    if (!shop && typeof window.Shopify !== 'undefined' && window.Shopify.shop) {
        shop = window.Shopify.shop;
    }
    if (!shop && mode === 'client') {
        shop = window.location.hostname;
    }

    try {
        if(shop) sessionStorage.setItem('shop', shop);
        else shop = sessionStorage.getItem('shop');
    } catch(e) {}

    // --- FONCTION UTILITAIRE : CONVERSION FICHIER -> BASE64 ---
    const toBase64 = file => new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve(reader.result);
        reader.onerror = error => reject(error);
    });

    async function getSessionToken() {
        if (window.shopify && window.shopify.id) return await shopify.id.getToken();
        return null;
    }

    async function authenticatedFetch(url, options = {}) {
        try {
            const token = await getSessionToken();
            const headers = options.headers || {};
            if (token) headers['Authorization'] = `Bearer ${token}`;
            
            const res = await fetch(url, { ...options, headers });
            if (res.status === 401 && shop && mode !== 'client') { 
                window.top.location.href = `/login?shop=${shop}`; 
                return null; 
            }
            return res;
        } catch (error) { throw error; }
    }

    if(shop) {
        if (mode === 'client') initClientMode();
        else initAdminMode(shop);
    } else {
        console.warn("Shop ID not found.");
    }

    // --- DASHBOARD (Admin) ---
    async function initAdminMode(s) {
        const res = await authenticatedFetch(`/api/get-data?shop=${s}`);
        if (res && res.ok) {
            const data = await res.json();
            updateDashboardStats(data.credits || 0);
            updateVIPStatus(data.lifetime || 0);

            const tryEl = document.getElementById('stat-tryons');
            const atcEl = document.getElementById('stat-atc');
            if(tryEl) tryEl.innerText = data.usage || 0;
            if(atcEl) atcEl.innerText = data.atc || 0;

            if(data.widget) {
                document.getElementById('ws-text').value = data.widget.text || "Try It On Now ✨";
                document.getElementById('ws-color').value = data.widget.bg || "#000000";
                document.getElementById('ws-text-color').value = data.widget.color || "#ffffff";
                if(data.security) document.getElementById('ws-limit').value = data.security.max_tries || 5;
                if(window.updateWidgetPreview) window.updateWidgetPreview();
            }
        }
    }

    function updateDashboardStats(credits) {
        const el = document.getElementById('credits');
        if(el) el.innerText = credits;
    }

    function updateVIPStatus(lifetime) {
        // Logique visuelle VIP (simplifiée pour la réponse)
    }

    window.saveSettings = async function(btn) {
        // Votre logique de sauvegarde existante
    };

    window.trackATC = async function() {
        if(shop) {
            try {
                const url = mode === 'client' ? `${API_BASE_URL}/api/track-atc` : '/api/track-atc';
                await fetch(url, {
                    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ shop: shop })
                });
            } catch(e) { console.error("Tracking Error", e); }
        }
    };

    function initClientMode() {
        document.body.classList.add('client-mode');
        const adminZone = document.getElementById('admin-only-zone');
        if(adminZone) adminZone.style.display = 'none';
        
        if (autoProductImage) {
            const img = document.getElementById('prevC');
            if(img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                if(img.parentElement.querySelector('.empty-state')) {
                    img.parentElement.querySelector('.empty-state').style.display = 'none';
                }
            }
        }
    }

    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if(file) {
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
        // Votre logique de preview existante
    }

    // --- C'EST ICI QUE TOUT SE JOUE : LA NOUVELLE FONCTION GENERATE ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        if (!uFile) return alert("Please upload your photo.");
        if (!autoProductImage && !cFile) return alert("Please upload a garment.");

        const oldText = btn.innerHTML;
        btn.disabled = true; 
        btn.innerHTML = "Generating...";

        // UI Reset
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        document.getElementById('post-actions').style.display = 'none';

        // Loader animation
        const textEl = document.getElementById('loader-text');
        const texts = ["Analyzing silhouette...", "Matching fabrics...", "Simulating drape...", "Rendering lighting..."];
        let step = 0;
        const interval = setInterval(() => { if(step < texts.length) textEl.innerText = texts[step++]; }, 2500);

        try {
            // 1. CONVERSION IMAGE CLIENT EN BASE64
            const personImageBase64 = await toBase64(uFile);
            
            // 2. PRÉPARATION DU VÊTEMENT (Base64 ou URL)
            let clothingImagePayload;
            if (cFile) {
                clothingImagePayload = await toBase64(cFile); // Admin upload manual
            } else {
                clothingImagePayload = autoProductImage; // Shopify URL
            }

            // 3. CRÉATION DU PACKET JSON
            const payload = {
                shop: shop,
                person_image: personImageBase64,
                clothing_image: clothingImagePayload,
                category: "upper_body" // ou 'dresses', 'lower_body' selon besoin
            };

            const headers = { 'Content-Type': 'application/json' };
            let res;

            // 4. ENVOI DE LA REQUÊTE
            if (mode === 'client') {
                console.log("Mode Client: Envoi direct à Render");
                res = await fetch(`${API_BASE_URL}/api/generate`, { 
                    method: 'POST', 
                    headers: headers,
                    body: JSON.stringify(payload) 
                });
            } else {
                console.log("Mode Admin: Envoi via Proxy");
                res = await authenticatedFetch('/api/generate', { 
                    method: 'POST', 
                    headers: headers,
                    body: JSON.stringify(payload) 
                });
            }

            clearInterval(interval);

            if (!res) throw new Error("No connection to server");

            // Gestion erreurs Credits / Rate Limit
            if (res.status === 429) { alert("Daily limit reached."); document.getElementById('loader').style.display = 'none'; return; }
            if (res.status === 402) { alert("Not enough credits!"); return; }
            
            if (!res.ok) {
                const errText = await res.text();
                // Essai de parsing JSON d'erreur, sinon texte brut
                try {
                    const errObj = JSON.parse(errText);
                    throw new Error(errObj.error || "Server Error");
                } catch(e) { throw new Error(`Server Error (${res.status}): ${errText}`); }
            }

            const data = await res.json();
            
            // Replicate renvoie parfois un tableau, parfois une string
            let finalUrl = data.result_image_url;
            if(Array.isArray(data.output)) finalUrl = data.output[0];
            else if(data.output) finalUrl = data.output;

            if(finalUrl){
                const ri = document.getElementById('resImg');
                ri.src = finalUrl;
                ri.onload = () => { 
                    ri.style.display = 'block'; 
                    document.getElementById('loader').style.display = 'none'; 
                    document.getElementById('post-actions').style.display = 'block'; 
                };
            } else { 
                throw new Error("No image URL returned by AI");
            }

        } catch(e) { 
            clearInterval(interval); 
            console.error("GENERATION ERROR:", e); 
            alert("Error: " + e.message); 
            document.getElementById('loader').style.display = 'none'; 
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldText; 
        }
    };
});
