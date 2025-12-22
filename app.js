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
            const r = new FileReader();
            r.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                img.parentElement.classList.add('has-image');
                img.parentElement.querySelectorAll('i, .upload-text').forEach(el => el.style.display = 'none');
            };
            r.readAsDataURL(file);
        }
    };

    // GENERATE
    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const c = document.getElementById('cImg').files[0];
        if (!u || !c) return alert("Veuillez mettre les 2 photos.");

        const btn = document.getElementById('btnGo');
        const resZone = document.getElementById('resZone');
        const loader = document.getElementById('loader');
        
        btn.disabled = true; btn.innerHTML = 'Traitement...';
        resZone.style.display = 'flex'; 

        const to64 = f => new Promise(r => { const rd = new FileReader(); rd.readAsDataURL(f); rd.onload=()=>r(rd.result); });

        try {
            const res = await fetch('/api/generate', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop || "demo", person_image_url: await toBase64(u), clothing_image_url: await toBase64(c), category: "upper_body" })
            });
            const data = await res.json();
            
            if(data.result_image_url) {
                document.getElementById('resImg').src = data.result_image_url;
                document.getElementById('resImg').style.display = 'block';
                loader.style.display = 'none';
                if(mode !== 'client') fetchCredits(shop);
            } else alert("Erreur IA");
        } catch(e) { alert("Erreur technique"); resZone.style.display = 'none'; }
        finally { btn.disabled = false; btn.innerHTML = 'Essayer Maintenant ✨'; }
    };

    async function fetchCredits(s) {
        try {
            const res = await fetch(`/api/get-credits?shop=${s}`);
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) {}
    }

    // --- CORRECTION DU BUG DE PAIEMENT ---
    window.buy = async function(packId) {
        if(!shop) return alert("Erreur : Boutique non détectée. Rechargez la page.");
        
        // On cible le bouton quel que soit l'endroit du clic
        const card = event.currentTarget; 
        const btn = card.querySelector('button') || event.target;
        const oldText = btn.innerText;
        
        btn.innerText = "...";
        btn.disabled = true;

        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop, pack_id: packId })
            });
            
            // Si le serveur dit "401" (Session perdue), on redirige vers le login
            if (res.status === 401) {
                console.log("Session expirée, reconnexion...");
                window.top.location.href = `https://shopify-try-on.onrender.com/login?shop=${shop}`;
                return;
            }

            const data = await res.json();
            if(data.confirmation_url) {
                window.top.location.href = data.confirmation_url;
            } else {
                // Affiche l'erreur réelle (detail ou error)
                alert("Erreur Paiement : " + (data.detail || data.error || "Inconnue"));
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
