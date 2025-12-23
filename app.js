document.addEventListener("DOMContentLoaded", function() {
    
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    
    if(shop) sessionStorage.setItem('shop', shop);
    document.body.classList.add('loaded');

    // SETUP INITIAL (ADMIN VS CLIENT)
    if (mode === 'client') {
        document.body.classList.add('client-mode');
        const t = document.getElementById('client-title');
        if(t) t.style.display = 'block';
    } else {
        if(shop) fetchCredits(shop);
    }

    // FONCTION UPLOAD (PREVIEW)
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

    // GENERATION IA (APPEL API)
    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const c = document.getElementById('cImg').files[0];
        if (!u || !c) return alert("Please upload both photos.");

        const btn = document.getElementById('btnGo');
        const resZone = document.getElementById('resZone');
        const loader = document.getElementById('loader');
        
        btn.disabled = true; btn.innerHTML = 'Processing...';
        if(resZone) resZone.style.display = 'flex';
        if(loader) loader.style.display = 'block';
        if(resZone) resZone.scrollIntoView({ behavior: 'smooth' });

        const to64 = f => new Promise(r => { const rd = new FileReader(); rd.readAsDataURL(f); rd.onload=()=>r(rd.result); });

        try {
            const res = await fetch('/api/generate', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    shop: shop || "demo", 
                    person_image_url: await to64(u), 
                    clothing_image_url: await to64(c), 
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

    // --- GESTION DES CRÉDITS ---
    async function fetchCredits(s) {
        try {
            const res = await fetch(`/api/get-credits?shop=${s}`);
            if (res.status === 401) {
                window.top.location.href = `/login?shop=${s}`;
                return;
            }
            const data = await res.json();
            const el = document.getElementById('credits');
            if(el) el.innerText = data.credits;
        } catch(e) {}
    }

    // --- FONCTION PAIEMENT MISE À JOUR (CUSTOM PACK) ---
    window.buy = async function(packId, customAmount = 0) {
        if(!shop) return alert("Shop ID missing");
        
        let btn;
        // Détecter le bouton cliqué même si on clique sur l'enfant
        if (event && event.target) {
            btn = event.currentTarget.tagName === 'BUTTON' ? event.currentTarget : event.target.closest('button');
        } 
        // Si appelé manuellement sans event
        if (!btn) btn = document.querySelector('.custom-input-group button');

        const oldText = btn ? btn.innerText : "Buy";
        if(btn) {
            btn.innerText = "Redirecting...";
            btn.disabled = true;
        }

        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    shop: shop, 
                    pack_id: packId,
                    custom_amount: parseInt(customAmount) 
                })
            });

            if (res.status === 401) {
                window.top.location.href = `/login?shop=${shop}`;
                return;
            }

            const data = await res.json();
            
            if(data.confirmation_url) {
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Error: " + (data.error || "Unknown"));
                if(btn) { btn.innerText = oldText; btn.disabled = false; }
            }
        } catch(e) {
            alert("Network Error");
            if(btn) { btn.innerText = oldText; btn.disabled = false; }
        }
    }

    // NOUVELLE FONCTION POUR CUSTOM PACK
    window.buyCustom = function() {
        const amount = document.getElementById('customAmount').value;
        if(amount < 200) {
            alert("Minimum order for custom pack is 200 credits.");
            return;
        }
        // Appel manuel à buy avec le bon ID
        window.buy('pack_custom', amount);
    }
});
