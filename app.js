document.addEventListener("DOMContentLoaded", function() {
    
    // 1. GESTION IMMÉDIATE DE L'ÉCRAN BLANC
    document.body.classList.add('loaded');

    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image'); 
    
    if(shop) sessionStorage.setItem('shop', shop);

    // MODE CLIENT (WIDGET)
    if (mode === 'client') {
        document.body.classList.add('client-mode');
        // On cache le dashboard admin et on montre l'interface studio
        const adminDash = document.getElementById('admin-dashboard');
        const studioInt = document.getElementById('studio-interface');
        const title = document.getElementById('client-title');
        
        if(adminDash) adminDash.style.display = 'none';
        if(studioInt) studioInt.style.display = 'block';
        if(title) title.style.display = 'block';

        // Auto-chargement image produit
        if (autoProductImage) {
            const img = document.getElementById('prevC');
            const card = document.getElementById('card-garment');
            if(img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                if(img.parentElement) {
                    img.parentElement.classList.add('has-image');
                    const els = img.parentElement.querySelectorAll('i, .upload-text, .upload-icon, .upload-sub');
                    els.forEach(el => el.style.display = 'none');
                }
            }
        }
    } else {
        // MODE ADMIN
        if(shop) fetchCredits(shop);
    }

    // FONCTIONS UPLOAD ET IA
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

    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        
        if (!u || (!cFile && !autoProductImage)) return alert("Please upload your photo.");

        const btn = document.getElementById('btnGo');
        const resZone = document.getElementById('resZone');
        const loader = document.getElementById('loader');
        
        btn.disabled = true; btn.innerHTML = 'Processing...';
        if(resZone) resZone.style.display = 'flex';
        if(loader) loader.style.display = 'block';

        const to64 = f => new Promise(r => { const rd = new FileReader(); rd.readAsDataURL(f); rd.onload=()=>r(rd.result); });

        try {
            let garmentData = cFile ? await to64(cFile) : autoProductImage;
            const res = await fetch('/api/generate', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop || "demo", person_image_url: await to64(u), clothing_image_url: garmentData, category: "upper_body" })
            });
            const data = await res.json();
            
            if(data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.style.display = 'block';
                if(loader) loader.style.display = 'none';
                if(mode !== 'client') fetchCredits(shop);
            } else alert("AI Error: " + (data.error || "Unknown"));
        } catch(e) { alert("Error: " + e); }
        finally { btn.disabled = false; btn.innerHTML = 'Test This Outfit Now <i class="fa-solid fa-wand-magic-sparkles"></i>'; }
    };

    // LOGIQUE CRÉDITS (CORRIGÉE)
    async function fetchCredits(s) {
        try {
            const res = await fetch(`/api/get-credits?shop=${s}`);
            if (res.status === 401) { window.top.location.href = `/login?shop=${s}`; return; }
            const data = await res.json();
            // Ton HTML a l'ID "credits", pas "credits-count". Je corrige ici.
            const el = document.getElementById('credits'); 
            if(el) el.innerText = data.credits;
        } catch(e) { console.error("Credit fetch error", e); }
    }

    window.buy = async function(packId) {
        if(!shop) return alert("Shop ID missing");
        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop, pack_id: packId })
            });
            const data = await res.json();
            if(data.confirmation_url) window.top.location.href = data.confirmation_url;
            else alert("Error: " + (data.error || "Unknown"));
        } catch(e) { alert("Network Error"); }
    }

    window.buyCustom = function() {
        const amount = document.getElementById('customAmount').value;
        if(amount < 200) return alert("Min 200 credits");
        // On réutilise la même logique mais avec une route adaptée dans buy
        // Note: J'ai adapté la fonction buy ci-dessus pour simplifier, 
        // voici l'appel spécifique pour le custom qui tape sur la meme route API
        fetch('/api/buy-credits', {
             method: 'POST', headers: {'Content-Type': 'application/json'},
             body: JSON.stringify({ shop: shop, pack_id: 'pack_custom', custom_amount: parseInt(amount) })
        })
        .then(r=>r.json())
        .then(d=>{ if(d.confirmation_url) window.top.location.href = d.confirmation_url; });
    }
});
