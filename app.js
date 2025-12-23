document.addEventListener("DOMContentLoaded", function() {
    
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    
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

    // FONCTION UPLOAD
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

    // GENERATION IA
    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const c = document.getElementById('cImg').files[0];
        if (!u || !c) return alert("Veuillez mettre les 2 photos.");

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
                body: JSON.stringify({ shop: shop || "demo", person_image_url: await to64(u), clothing_image_url: await to64(c), category: "upper_body" })
            });
            const data = await res.json();
            
            if(data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.style.display = 'block';
                if(loader) loader.style.display = 'none';
                if(mode !== 'client') fetchCredits(shop);
            } else alert("Erreur IA");
        } catch(e) { alert("Erreur technique"); }
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

    // --- FONCTION PAIEMENT MISE À JOUR ---
    window.buy = async function(packId, customAmount = 0) {
        if(!shop) return alert("Erreur shop");
        
        let btn;
        if (event && event.target) {
             btn = event.currentTarget.tagName === 'BUTTON' ? event.currentTarget : event.currentTarget.querySelector('button');
             if(!btn) btn = event.target; // Fallback
        } else {
            // Si appelé via buyCustom sans event direct sur un bouton
            btn = document.querySelector('.custom-input-group button');
        }

        const oldText = btn ? btn.innerText : "Acheter";
        if(btn) {
            btn.innerText = "Redirection...";
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
                alert("Erreur: " + (data.error || "Inconnue"));
                if(btn) { btn.innerText = oldText; btn.disabled = false; }
            }
        } catch(e) {
            alert("Erreur réseau");
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
        window.buy('pack_custom', amount);
    }
});
