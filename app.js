document.addEventListener("DOMContentLoaded", function() {
    
    // --- INITIALISATION ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    
    if(shop) sessionStorage.setItem('shop', shop);

    // Fade in
    document.body.classList.add('loaded');

    // Gestion Mode Client vs Admin
    if (mode === 'client') {
        document.body.classList.add('client-mode');
        document.getElementById('client-title').style.display = 'block';
    } else {
        if(shop) fetchCredits(shop);
    }

    // --- UPLOAD & PREVIEW ---
    window.preview = function(inputId, imgId, txtId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block'; // Affiche l'image
                
                // Cache les textes et icônes
                const zone = img.parentElement;
                const texts = zone.querySelectorAll('span, i');
                texts.forEach(el => el.style.display = 'none');
            };
            reader.readAsDataURL(file);
        }
    };

    // --- GENERATION IA ---
    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const c = document.getElementById('cImg').files[0];
        
        if (!u || !c) return alert("⚠️ Veuillez ajouter les 2 photos avant de générer.");

        const btn = document.getElementById('btnGo');
        const loader = document.getElementById('loader');
        const txtRes = document.getElementById('txtRes');
        const iconRes = document.querySelector('.result-zone .zone-icon');

        // UI Loading State
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Création en cours...';
        loader.style.display = 'block';
        txtRes.style.display = 'none';
        iconRes.style.display = 'none';

        const toBase64 = f => new Promise(r => { const rd = new FileReader(); rd.readAsDataURL(f); rd.onload=()=>r(rd.result); });

        try {
            const res = await fetch('/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    shop: shop || "demo",
                    person_image_url: await toBase64(u),
                    clothing_image_url: await toBase64(c),
                    category: "upper_body"
                })
            });
            const data = await res.json();
            
            if(data.result_image_url) {
                const resImg = document.getElementById('resImg');
                resImg.src = data.result_image_url;
                resImg.style.display = 'block';
                loader.style.display = 'none';
                
                if(mode !== 'client') fetchCredits(shop); // Update crédits si admin
            } else {
                alert("Erreur IA : " + JSON.stringify(data));
                resetUI();
            }
        } catch(e) {
            alert("Erreur technique : " + e.message);
            resetUI();
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-bolt"></i> Générer l\'essayage';
        }

        function resetUI() {
            loader.style.display = 'none';
            txtRes.style.display = 'block';
            iconRes.style.display = 'block';
        }
    };

    // --- CREDITS & ACHAT ---
    async function fetchCredits(s) {
        try {
            const res = await fetch(`/api/get-credits?shop=${s}`);
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) {}
    }

    window.buy = async function(packId) {
        if(!shop) return alert("Erreur: Impossible de détecter la boutique.");
        
        const btn = event.currentTarget;
        const oldHtml = btn.innerHTML;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
        btn.disabled = true;

        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop, pack_id: packId })
            });
            const data = await res.json();
            
            if(data.confirmation_url) {
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Erreur : " + (data.error || "Inconnue"));
            }
        } catch(e) {
            alert("Erreur connexion serveur.");
        } finally {
            btn.innerHTML = oldHtml;
            btn.disabled = false;
        }
    }
});
