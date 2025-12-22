document.addEventListener("DOMContentLoaded", function() {
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    if(shop) sessionStorage.setItem('shop', shop);

    document.body.classList.add('loaded');
    if (mode === 'client') document.body.classList.add('client-mode');

    // --- FONCTION ACHAT RÉACTIVÉE ---
    window.buy = async function(packId) {
        if(!shop) return alert("Erreur: Shop non détecté. Rechargez depuis Shopify.");
        
        const btn = event.target;
        const originalText = btn.innerText;
        btn.innerText = "Chargement...";
        btn.disabled = true;

        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ shop: shop, pack_id: packId })
            });
            const data = await res.json();
            
            if(data.confirmation_url) {
                // Redirection vers Shopify pour payer
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Erreur paiement: " + (data.error || "Inconnue"));
            }
        } catch(e) {
            alert("Erreur technique paiement");
        } finally {
            btn.innerText = originalText;
            btn.disabled = false;
        }
    }

    // --- RESTE DU CODE (Upload, Preview, etc.) ---
    window.preview = function(input, imgId, phId) {
        const file = input.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                document.getElementById(imgId).src = e.target.result;
                document.getElementById(imgId).style.display = 'block';
                if(phId) document.getElementById(phId).style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    };

    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const c = document.getElementById('cImg').files[0];
        if (!u || !c) return alert("Photos manquantes !");
        
        const btn = document.getElementById('btnGo');
        btn.disabled = true; btn.innerText = "Génération...";
        
        const toBase64 = f => new Promise(r => { 
            const reader = new FileReader(); reader.readAsDataURL(f); reader.onload=()=>r(reader.result); 
        });

        try {
            const res = await fetch('/api/generate', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    shop: shop || "demo",
                    person_image_url: await toBase64(u),
                    clothing_image_url: await toBase64(c),
                    category: "upper_body"
                })
            });
            const data = await res.json();
            if(data.result_image_url) {
                document.getElementById('resImg').src = data.result_image_url;
                document.getElementById('resImg').style.display = 'block';
                document.getElementById('phRes').style.display = 'none';
            } else alert("Erreur: " + JSON.stringify(data));
        } catch(e) { alert("Erreur technique"); }
        finally { btn.disabled = false; btn.innerText = "Générer"; }
    };
});
