document.addEventListener("DOMContentLoaded", function() {
    document.body.classList.add('loaded');
    
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image'); 
    
    if(shop) sessionStorage.setItem('shop', shop);

    if (mode === 'client') {
        document.body.classList.add('client-mode');
        const adminDash = document.getElementById('admin-dashboard');
        const studioInt = document.getElementById('studio-interface');
        const title = document.getElementById('client-title');
        
        if(adminDash) adminDash.style.display = 'none';
        if(studioInt) studioInt.style.display = 'block';
        if(title) title.style.display = 'block';

        if (autoProductImage) {
            const img = document.getElementById('prevC');
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
        if(shop) fetchCredits(shop);
    }

    // --- FONCTION VITALE : AUTO-RECONNEXION AVEC SESSION TOKENS ---
    async function fetchCredits(s) {
        try {
            // RÉCUPÉRATION DU JETON (Condition Shopify)
            const token = await window.shopify.idToken();

            const res = await fetch(`/api/get-credits?shop=${s}`, {
                headers: { "Authorization": `Bearer ${token}` }
            });

            if (res.status === 401) { 
                console.log("Session lost, reconnecting...");
                window.top.location.href = `/login?shop=${s}`; 
                return; 
            }
            const data = await res.json();
            const el = document.getElementById('credits'); 
            if(el) el.innerText = data.credits;
        } catch(e) { console.error("API Error", e); }
    }

    // --- PAIEMENT AVEC SESSION TOKENS ---
    window.buy = async function(packId) {
        if(!shop) return alert("Shop ID missing");
        
        let btn;
        if (event && event.target) btn = event.currentTarget.tagName === 'BUTTON' ? event.currentTarget : event.target.closest('button');
        if (!btn) btn = document.querySelector('.custom-input-group button');
        const oldText = btn ? btn.innerText : "Buy";
        if(btn) { btn.innerText = "Redirecting..."; btn.disabled = true; }

        try {
            // RÉCUPÉRATION DU JETON (Condition Shopify)
            const token = await window.shopify.idToken();

            const res = await fetch('/api/buy-credits', {
                method: 'POST', 
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ shop: shop, pack_id: packId })
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

    window.buyCustom = async function() {
        const amount = document.getElementById('customAmount').value;
        if(amount < 200) return alert("Min 200 credits");
        
        const token = await window.shopify.idToken();

        fetch('/api/buy-credits', {
             method: 'POST', 
             headers: {
                 'Content-Type': 'application/json',
                 'Authorization': `Bearer ${token}`
             },
             body: JSON.stringify({ shop: shop, pack_id: 'pack_custom', custom_amount: parseInt(amount) })
        }).then(async r => {
            if (r.status === 401) { window.top.location.href = `/login?shop=${shop}`; return; }
            const d = await r.json();
            if(d.confirmation_url) window.top.location.href = d.confirmation_url;
            else alert(d.error);
        });
    }

    // --- RESTE DU CODE (IA) ---
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
        if(resZone) resZone.scrollIntoView({ behavior: 'smooth' });
        
        const to64 = f => new Promise(r => { const rd = new FileReader(); rd.readAsDataURL(f); rd.onload=()=>r(rd.result); });

        try {
            let garmentData = cFile ? await to64(cFile) : autoProductImage;
            // Optionnel : Vous pourriez aussi envoyer le token ici pour être 100% sûr
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
});
