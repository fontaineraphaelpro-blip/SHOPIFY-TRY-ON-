document.addEventListener("DOMContentLoaded", function() {

    // --- FIX CRITIQUE : Récupération des paramètres Iframe ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode'); // 'client' ou null
    
    // On priorise le shop de l'URL (envoyé par le Liquid), sinon session
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    
    // Sauvegarde pour la navigation interne
    if (shop) sessionStorage.setItem('shop', shop);

    const autoProductImage = params.get('product_image');

    console.log("VTON Init - Shop:", shop, "| Mode:", mode);

    // --- AUTHENTIFICATION ---
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

    // --- INITIALISATION ---
    if(shop) {
        if (mode === 'client') initClientMode();
        else initAdminMode(shop);
    } else {
        console.warn("Aucun shop détecté. Le widget risque de ne pas fonctionner.");
    }

    // --- MODE CLIENT (STOREFRONT) ---
    function initClientMode() {
        console.log("Activation Mode Client");
        document.body.classList.add('client-mode'); // Déclenche le CSS
        
        // Cache brutalement le dashboard JS si besoin
        const adminZone = document.getElementById('admin-only-zone');
        if(adminZone) adminZone.style.display = 'none';

        // Gestion Image Produit Automatique
        if (autoProductImage) {
            const img = document.getElementById('prevC');
            if(img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                // Masque l'upload vêtement car inutile
                const garmentUploadBox = document.querySelector('label[for="cImg"]');
                if (garmentUploadBox) garmentUploadBox.style.display = 'none';
                
                // On agrandit la boite photo utilisateur pour équilibrer
                const userBox = document.querySelector('label[for="uImg"]');
                if (userBox && document.body.classList.contains('client-mode')) {
                    userBox.style.gridColumn = "span 2"; 
                }
            }
        }
        
        document.body.classList.add('loaded');
        document.body.style.opacity = "1";
    }

    // --- MODE ADMIN (DASHBOARD) ---
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
        document.body.classList.add('loaded');
        document.body.style.opacity = "1";
    }

    // --- FONCTIONS UTILITAIRES ---
    function updateDashboardStats(credits) {
        const el = document.getElementById('credits');
        if(el) el.innerText = credits;
        const daysEl = document.querySelector('.rs-value');
        if (daysEl) {
            let daysLeft = Math.floor(credits / 8); 
            if(daysLeft < 1) daysLeft = "< 1";
            daysEl.innerText = daysLeft + (daysLeft === "< 1" ? " Day" : " Days");
        }
    }

    function updateVIPStatus(lifetime) {
        const fill = document.querySelector('.vip-fill');
        const marker = document.querySelector('.vip-marker');
        let percent = (lifetime / 500) * 100;
        if(percent > 100) percent = 100;
        if(fill) fill.style.width = percent + "%";
        if(marker) marker.style.left = percent + "%";
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

    // --- ACTIONS BACKEND ---
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
        } catch(e) { console.error(e); alert("Error saving"); }
        finally { btn.disabled = false; }
    };

    window.trackATC = async function() {
        if(shop) {
            try {
                // En mode client, on utilise fetch simple car pas de session token
                const url = '/api/track-atc';
                const payload = JSON.stringify({ shop: shop });
                const headers = {'Content-Type': 'application/json'};
                
                if (mode === 'client') await fetch(url, { method: 'POST', headers: headers, body: payload });
                else await authenticatedFetch(url, { method: 'POST', headers: headers, body: payload });
                
                // Petit feedback visuel
                const btn = document.getElementById('shopBtn');
                btn.innerHTML = "Redirecting... <i class='fa-solid fa-check'></i>";
            } catch(e) { console.error("Tracking Error", e); }
        }
    };

    // --- FONCTION GENERATE PRINCIPALE ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');

        if (!shop) return alert("Erreur: Boutique non identifiée. Rechargement nécessaire.");
        if (!uFile) return alert("Veuillez ajouter votre photo.");
        // Si pas d'image auto ET pas de fichier uploadé
        if (!autoProductImage && !cFile) return alert("Veuillez ajouter un vêtement.");

        const oldText = btn.innerHTML;
        btn.disabled = true; 
        btn.innerHTML = "Generating...";

        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        document.getElementById('post-actions').style.display = 'none';

        const textEl = document.getElementById('loader-text');
        const texts = ["Analyzing silhouette...", "Matching fabrics...", "Simulating drape...", "Rendering lighting..."];
        let step = 0;
        const interval = setInterval(() => { if(step < texts.length) textEl.innerText = texts[step++]; }, 2500);

        try {
            const formData = new FormData();
            formData.append("shop", shop); // CRUCIAL
            formData.append("person_image", uFile);
            
            if(cFile) {
                formData.append("clothing_file", cFile);
            } else if (autoProductImage) {
                formData.append("clothing_url", autoProductImage);
            }
            formData.append("category", "upper_body");

            let res;
            if (mode === 'client') {
                // Mode client : Pas de Header Authorization Bearer
                res = await fetch('/api/generate', { method: 'POST', body: formData });
            } else {
                // Mode admin : Avec Token Session
                res = await authenticatedFetch('/api/generate', { method: 'POST', body: formData });
            }

            clearInterval(interval);

            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.error || "Server Error");
            }

            const data = await res.json();
            if(data.result_image_url){
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => { 
                    ri.style.display = 'block'; 
                    document.getElementById('loader').style.display = 'none'; 
                    document.getElementById('post-actions').style.display = 'block'; 
                };
            } else {
                throw new Error("No image URL returned");
            }

        } catch(e) { 
            clearInterval(interval); 
            console.error(e); 
            alert("Erreur: " + e.message); 
            document.getElementById('loader').style.display = 'none'; 
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldText; 
        }
    };
});
