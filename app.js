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
        
        btn.disabled = true; btn.innerHTML = 'Traitement en cours...';
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
                // Si on est admin, on met à jour les crédits (simulation décompte)
                if(mode !== 'client') fetchCredits(shop);
            } else alert("Erreur IA");
        } catch(e) { alert("Erreur technique"); }
        finally { btn.disabled = false; btn.innerHTML = 'Essayer Maintenant ✨'; }
    };

    // --- GESTION DES CRÉDITS & SESSION ---
    async function fetchCredits(s) {
        try {
            const res = await fetch(`/api/get-credits?shop=${s}`);
            
            // SI LA SESSION EST PERDUE (401), ON RECHARGE LA PAGE IMMÉDIATEMENT
            if (res.status === 401) {
                console.log("Session perdue, reconnexion auto...");
                window.top.location.href = `/login?shop=${s}`;
                return;
            }

            const data = await res.json();
            const el = document.getElementById('credits');
            if(el) el.innerText = data.credits;
        } catch(e) {}
    }

    // --- FONCTION PAIEMENT ROBUSTE ---
    window.buy = async function(packId) {
        if(!shop) return alert("Erreur shop");
        
        const btn = event.currentTarget.querySelector('button') || event.target;
        const oldText = btn.innerText;
        btn.innerText = "Redirection...";
        btn.disabled = true;

        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop, pack_id: packId })
            });

            // Si ça échoue ici (401), on redirige vers le login pour réparer
            if (res.status === 401) {
                window.top.location.href = `/login?shop=${shop}`;
                return;
            }

            const data = await res.json();
            
            if(data.confirmation_url) {
                // On part payer chez Shopify
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Erreur: " + (data.error || "Inconnue"));
                btn.innerText = oldText;
                btn.disabled = false;
            }
        } catch(e) {
            alert("Erreur réseau");
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
});
