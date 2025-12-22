document.addEventListener("DOMContentLoaded", function() {
    
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    
    if(shop) sessionStorage.setItem('shop', shop);
    document.body.classList.add('loaded');

    // LOGIQUE D'AFFICHAGE
    if (mode === 'client') {
        document.body.classList.add('client-mode');
        document.getElementById('client-title').style.display = 'block';
    } else {
        if(shop) fetchCredits(shop);
    }

    // FONCTION PREVIEW (Cache les icônes quand l'image est là)
    window.preview = function(inputId, imgId, txtId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                
                // Ajoute une classe pour dire qu'il y a une image (bordure solide)
                img.parentElement.classList.add('has-image');
                
                // Cache le texte et l'icône
                const card = img.parentElement;
                card.querySelectorAll('.upload-icon, .upload-text, .upload-sub').forEach(el => el.style.display = 'none');
            };
            reader.readAsDataURL(file);
        }
    };

    // GENERATION IA
    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const c = document.getElementById('cImg').files[0];
        
        if (!u || !c) return alert("Veuillez ajouter votre photo et celle du vêtement.");

        const btn = document.getElementById('btnGo');
        const resultZone = document.getElementById('resultZone');
        const loader = document.getElementById('loader');
        const resImg = document.getElementById('resImg');
        
        // UI LOADING
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Création en cours...';
        
        // Affiche la zone de résultat et le loader
        resultZone.style.display = 'flex';
        loader.style.display = 'block';
        resImg.style.display = 'none';

        // Scroll vers le bas pour voir le loader sur mobile
        resultZone.scrollIntoView({ behavior: 'smooth' });

        const toBase64 = f => new Promise(r => { const rd = new FileReader(); rd.readAsDataURL(f); rd.onload=()=>r(rd.result); });

        try {
            const res = await fetch('/api/generate', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop || "demo", person_image_url: await toBase64(u), clothing_image_url: await toBase64(c), category: "upper_body" })
            });
            const data = await res.json();
            
            if(data.result_image_url) {
                resImg.src = data.result_image_url;
                resImg.style.display = 'block';
                loader.style.display = 'none';
                
                if(mode !== 'client') fetchCredits(shop);
            } else {
                alert("Oups, l'IA a eu un petit souci. Réessayez !");
                resultZone.style.display = 'none'; // Cache si erreur
            }
        } catch(e) { 
            alert("Erreur de connexion."); 
            resultZone.style.display = 'none';
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = 'Essayer Maintenant <i class="fa-solid fa-wand-magic-sparkles"></i>';
        }
    };

    async function fetchCredits(s) {
        try {
            const res = await fetch(`/api/get-credits?shop=${s}`);
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) {}
    }

    // ACHAT (Ancienne méthode simple)
    window.buy = async function(packId) {
        if(!shop) return alert("Boutique non détectée");
        const btn = event.currentTarget.querySelector('button') || event.target;
        const oldText = btn.innerText;
        btn.innerText = "...";
        btn.disabled = true;

        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop, pack_id: packId })
            });
            const data = await res.json();
            if(data.confirmation_url) window.top.location.href = data.confirmation_url;
            else alert("Erreur : " + (data.error || "Inconnue"));
        } catch(e) {
            alert("Erreur réseau");
        } finally {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    }
});
