document.addEventListener("DOMContentLoaded", function() {
    
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    
    // NOUVEAU : On récupère l'image du produit depuis l'URL (envoyée par Shopify)
    const autoProductImage = params.get('product_image'); 
    
    if(shop) sessionStorage.setItem('shop', shop);
    document.body.classList.add('loaded');

    // SETUP INITIAL
    if (mode === 'client') {
        document.body.classList.add('client-mode');
        const t = document.getElementById('client-title');
        if(t) t.style.display = 'block';
    } else {
        if(shop) fetchCredits(shop);
    }

    // --- LOGIQUE AUTOMATIQUE "PRODUIT DÉJÀ LÀ" ---
    if (autoProductImage) {
        console.log("Auto-detect product:", autoProductImage);
        const img = document.getElementById('prevC');
        const card = document.getElementById('card-garment'); // On va ajouter cet ID au HTML
        
        // 1. On affiche l'image directement
        img.src = autoProductImage;
        img.style.display = 'block';
        
        // 2. On stylise la carte pour dire "C'est sélectionné !"
        if(img.parentElement) {
            img.parentElement.classList.add('has-image');
            // On cache les textes d'upload
            const els = img.parentElement.querySelectorAll('i, .upload-text, .upload-icon, .upload-sub');
            els.forEach(el => el.style.display = 'none');
        }

        // 3. On verrouille le clic (optionnel, ou on laisse changer si le client veut)
        // Ici je change le texte pour confirmer que c'est le produit actuel
        if(card) {
            // Création d'un petit badge "Current Product"
            const badge = document.createElement('div');
            badge.innerHTML = '<i class="fa-solid fa-check-circle"></i> This Product';
            badge.style.cssText = "position:absolute; bottom:10px; left:0; right:0; text-align:center; color:white; font-weight:bold; text-shadow:0 2px 4px rgba(0,0,0,0.5);";
            card.appendChild(badge);
        }
    }

    // FONCTION UPLOAD (Classique)
    window.preview = function(inputId, imgId, txtId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                if(img.parentElement) {
                    img.parentElement.classList.add('has-image');
                    const els = img.parentElement.querySelectorAll('i, .upload-text, .upload-icon, .upload-sub');
                    els.forEach(el => el.style.display = 'none');
                }
            };
            reader.readAsDataURL(file);
        }
    };

    // GENERATION IA (INTELLIGENTE)
    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        
        // Vérification : On a besoin de l'humain + (Vêtement fichier OU Vêtement URL Auto)
        if (!u || (!cFile && !autoProductImage)) {
            return alert("Please upload your photo."); // Le message change car le vêtement est peut-être déjà là
        }

        const btn = document.getElementById('btnGo');
        const resZone = document.getElementById('resZone');
        const loader = document.getElementById('loader');
        
        btn.disabled = true; btn.innerHTML = 'Processing...';
        if(resZone) resZone.style.display = 'flex';
        if(loader) loader.style.display = 'block';
        if(resZone) resZone.scrollIntoView({ behavior: 'smooth' });

        const to64 = f => new Promise(r => { const rd = new FileReader(); rd.readAsDataURL(f); rd.onload=()=>r(rd.result); });

        try {
            // LOGIQUE HYBRIDE :
            // Si on a un fichier uploadé, on le convertit.
            // Sinon, on utilise l'URL automatique.
            let garmentData = "";
            if (cFile) {
                garmentData = await to64(cFile);
            } else {
                garmentData = autoProductImage; // On envoie l'URL directe à Replicate (C'est plus rapide !)
            }

            const res = await fetch('/api/generate', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    shop: shop || "demo", 
                    person_image_url: await to64(u), 
                    clothing_image_url: garmentData, // URL ou Base64, le backend gère les deux
                    category: "upper_body" 
                })
            });
            const data = await res.json();
            
            if(data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.style.display = 'block';
                if(loader) loader.style.display = 'none';
                if(mode !== 'client') fetchCredits(shop);
            } else alert("AI Error: " + (data.error || "Unknown"));
        } catch(e) { alert("Technical Error: " + e); }
        finally { btn.disabled = false; btn.innerHTML = 'Try On Now ✨'; }
    };

    // ... (Le reste : fetchCredits, buy, buyCustom reste identique) ...
    async function fetchCredits(s) {
        try {
            const res = await fetch(`/api/get-credits?shop=${s}`);
            if (res.status === 401) { window.top.location.href = `/login?shop=${s}`; return; }
            const data = await res.json();
            const el = document.getElementById('credits');
            if(el) el.innerText = data.credits;
        } catch(e) {}
    }

    window.buy = async function(packId, customAmount = 0) {
        if(!shop) return alert("Shop ID missing");
        let btn;
        if (event && event.target) { btn = event.currentTarget.tagName === 'BUTTON' ? event.currentTarget : event.target.closest('button'); } 
        if (!btn) btn = document.querySelector('.custom-input-group button');
        const oldText = btn ? btn.innerText : "Buy";
        if(btn) { btn.innerText = "Redirecting..."; btn.disabled = true; }

        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop, pack_id: packId, custom_amount: parseInt(customAmount) })
            });
            if (res.status === 401) { window.top.location.href = `/login?shop=${shop}`; return; }
            const data = await res.json();
            if(data.confirmation_url) { window.top.location.href = data.confirmation_url; } 
            else { alert("Error: " + (data.error || "Unknown")); if(btn) { btn.innerText = oldText; btn.disabled = false; } }
        } catch(e) { alert("Network Error"); if(btn) { btn.innerText = oldText; btn.disabled = false; } }
    }
    window.buyCustom = function() {
        const amount = document.getElementById('customAmount').value;
        if(amount < 200) { alert("Minimum order for custom pack is 200 credits."); return; }
        window.buy('pack_custom', amount);
    }
});
