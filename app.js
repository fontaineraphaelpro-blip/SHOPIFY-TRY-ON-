document.addEventListener("DOMContentLoaded", function() {
    
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    
    if(shop) sessionStorage.setItem('shop', shop);
    document.body.classList.add('loaded');

    if (mode === 'client') {
        document.body.classList.add('client-mode');
        document.getElementById('client-title').style.display = 'block';
    } else {
        if(shop) fetchCredits(shop);
    }

    // UPLOAD
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
                    img.parentElement.querySelectorAll('span, i, div').forEach(el => {
                        if(el !== img) el.style.display = 'none';
                    });
                }
            };
            reader.readAsDataURL(file);
        }
    };

    // GENERATION
    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const c = document.getElementById('cImg').files[0];
        if (!u || !c) return alert("Photos manquantes");

        const btn = document.getElementById('btnGo');
        const resZone = document.getElementById('resZone');
        const loader = document.getElementById('loader');
        
        btn.disabled = true; btn.innerHTML = 'Traitement...';
        if(resZone) resZone.style.display = 'flex'; 
        if(loader) loader.style.display = 'block';

        const to64 = f => new Promise(r => { const rd = new FileReader(); rd.readAsDataURL(f); rd.onload=()=>r(rd.result); });

        try {
            const res = await fetch('/api/generate', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop || "demo", person_image_url: await to64(u), clothing_image_url: await to64(c), category: "upper_body" })
            });
            const data = await res.json();
            
            if(data.result_image_url) {
                document.getElementById('resImg').src = data.result_image_url;
                document.getElementById('resImg').style.display = 'block';
                if(loader) loader.style.display = 'none';
                if(mode !== 'client') fetchCredits(shop);
            } else alert("Erreur IA");
        } catch(e) { alert("Erreur"); }
        finally { btn.disabled = false; btn.innerHTML = 'Essayer Maintenant ✨'; }
    };

    // --- ICI LA MAGIE : On vérifie la connexion dès le chargement ---
    async function fetchCredits(s) {
        try {
            const res = await fetch(`/api/get-credits?shop=${s}`);
            
            // Si le serveur a oublié (401), on recharge la page MAINTENANT
            if (res.status === 401) {
                console.log("Auto-réparation de la session...");
                window.top.location.href = `/login?shop=${s}`;
                return;
            }

            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) {}
    }

    // ACHAT INSTANTANÉ
    window.buy = async function(packId) {
        if(!shop) return;
        
        const btn = event.currentTarget.querySelector('button') || event.target;
        btn.innerText = "Redirection...";
        btn.disabled = true;

        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop, pack_id: packId })
            });

            // Si jamais la session a sauté entre temps
            if(res.status === 401) {
                window.top.location.href = `/login?shop=${shop}`;
                return;
            }

            const data = await res.json();
            
            if(data.confirmation_url) {
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Erreur: " + (data.error || "Inconnue"));
                btn.innerText = "Réessayer";
                btn.disabled = false;
            }
        } catch(e) {
            alert("Erreur réseau");
            btn.disabled = false;
        }
    }
});
