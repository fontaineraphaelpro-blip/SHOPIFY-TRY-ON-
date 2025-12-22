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

    // --- UPLOAD ---
    window.preview = function(inputId, imgId, txtId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                // Cache les textes
                const zone = img.parentElement;
                const texts = zone.querySelectorAll('span, i');
                texts.forEach(el => el.style.display = 'none');
            };
            reader.readAsDataURL(file);
        }
    };

    // --- GENERATION ---
    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const c = document.getElementById('cImg').files[0];
        if (!u || !c) return alert("Veuillez mettre les 2 photos.");

        const btn = document.getElementById('btnGo');
        const loader = document.getElementById('loader');
        
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Traitement...';
        if(loader) loader.style.display = 'block';

        const toBase64 = f => new Promise(r => { const rd = new FileReader(); rd.readAsDataURL(f); rd.onload=()=>r(rd.result); });

        try {
            const res = await fetch('/api/generate', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop || "demo", person_image_url: await toBase64(u), clothing_image_url: await toBase64(c), category: "upper_body" })
            });
            const data = await res.json();
            
            if(data.result_image_url) {
                const resImg = document.getElementById('resImg');
                resImg.src = data.result_image_url;
                resImg.style.display = 'block';
                if(loader) loader.style.display = 'none';
                if(mode !== 'client') fetchCredits(shop);
            } else {
                alert("Erreur IA");
            }
        } catch(e) { alert("Erreur technique"); } 
        finally { btn.disabled = false; btn.innerHTML = 'Générer l\'essayage'; }
    };

    async function fetchCredits(s) {
        try {
            const res = await fetch(`/api/get-credits?shop=${s}`);
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) {}
    }

    // --- ACHAT (AVEC RECONNEXION AUTO) ---
    window.buy = async function(packId) {
        if(!shop) return alert("Shop non détecté");
        
        const btn = event.currentTarget;
        const oldText = btn.innerText;
        btn.innerText = "...";
        btn.disabled = true;

        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop, pack_id: packId })
            });

            // SI LE TOKEN EST PERDU (401), ON RECONNECTE AUTO
            if (res.status === 401) {
                console.log("Token perdu, reconnexion...");
                window.top.location.href = `https://shopify-try-on.onrender.com/login?shop=${shop}`;
                return;
            }

            const data = await res.json();
            if(data.confirmation_url) window.top.location.href = data.confirmation_url;
            else alert("Erreur: " + (data.error || "Inconnue"));
        } catch(e) {
            alert("Erreur connexion");
        } finally {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
});
