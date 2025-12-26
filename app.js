document.addEventListener("DOMContentLoaded", function() {

    // --- 1. CONFIGURATION ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode'); 
    const shop = params.get('shop'); 
    const autoProductImage = params.get('product_image');

    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    // --- 2. GESTION DES MODES ---
    if (mode === 'client') {
        console.log("👋 Mode Client (Widget) détecté pour :", shop);
        document.body.classList.add('client-mode');
        const adminZone = document.getElementById('admin-only-zone');
        if (adminZone) adminZone.style.display = 'none';

        if (autoProductImage) {
            const img = document.getElementById('prevC');
            if (img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                const emptyState = img.parentElement.querySelector('.empty-state');
                if (emptyState) emptyState.style.display = 'none';
            }
        }
    } else {
        console.log("👑 Mode Admin détecté");
        if (shop) initAdminMode(shop);
    }

    // --- 3. FONCTIONS ---
    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                const emptyState = img.parentElement.querySelector('.empty-state');
                if (emptyState) emptyState.style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    };

    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        if (!shop) return alert("Erreur technique : Boutique inconnue.");
        if (!uFile) return alert("Veuillez ajouter votre photo (Étape 1).");
        if (!autoProductImage && !cFile) return alert("Veuillez ajouter un vêtement (Étape 2).");

        const oldText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = "Création du look... <i class='fa-solid fa-spinner fa-spin'></i>";
        
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        
        try {
            const formData = new FormData();
            formData.append("shop", shop);
            formData.append("person_image", uFile);
            
            if (autoProductImage) {
                formData.append("clothing_url", autoProductImage);
            } else {
                formData.append("clothing_file", cFile);
            }

            let res;
            if (mode === 'client') {
                // Fetch public pour le widget
                res = await fetch('/api/generate', { method: 'POST', body: formData });
            } else {
                // Fetch sécurisé pour l'admin
                res = await authenticatedFetch('/api/generate', { method: 'POST', body: formData });
            }

            if (!res.ok) {
                const errTxt = await res.text();
                let errMsg = "Erreur inconnue";
                try { errMsg = JSON.parse(errTxt).error; } catch(e) { errMsg = errTxt; }
                throw new Error("Erreur Serveur : " + errMsg);
            }

            const data = await res.json();
            if (data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => {
                    document.getElementById('loader').style.display = 'none';
                    ri.style.display = 'block';
                    ri.scrollIntoView({behavior: "smooth", block: "center"});
                };
            } else {
                throw new Error("Aucune image reçue.");
            }

        } catch (e) {
            console.error(e);
            alert("Oups ! " + e.message);
            document.getElementById('loader').style.display = 'none';
        } finally {
            btn.disabled = false;
            btn.innerHTML = oldText;
        }
    };

    // --- 4. FONCTIONS ADMIN ---
    async function getSessionToken() {
        if (window.shopify && window.shopify.id) return await shopify.id.getToken();
        return null;
    }

    async function authenticatedFetch(url, options = {}) {
        try {
            const token = await getSessionToken();
            const headers = options.headers || {};
            if (token) headers['Authorization'] = `Bearer ${token}`;
            return fetch(url, { ...options, headers });
        } catch (e) { throw e; }
    }

    async function initAdminMode(s) {
        try {
            const res = await authenticatedFetch(`/api/get-data?shop=${s}`);
            if (res.ok) {
                const data = await res.json();
                if(document.getElementById('credits')) document.getElementById('credits').innerText = data.credits;
                if(document.getElementById('stat-tryons')) document.getElementById('stat-tryons').innerText = data.usage;
            }
        } catch (e) { console.log("Init Admin Error", e); }
    }
    
    window.buy = async function(packId, amount, btn) {
        const oldText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = 'Patientez...';
        try {
            const res = await authenticatedFetch('/api/buy-credits', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ shop: shop, pack_id: packId, custom_amount: parseInt(amount) })
            });
            const data = await res.json();
            if (data.confirmation_url) window.top.location.href = data.confirmation_url; 
            else alert("Erreur création paiement");
        } catch (e) { alert("Erreur réseau"); }
        finally { btn.disabled = false; btn.innerHTML = oldText; }
    };
    
    window.buyCustom = function(btn) {
        const val = document.getElementById('customAmount').value;
        window.buy('pack_custom', val, btn);
    };
});
