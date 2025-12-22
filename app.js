document.addEventListener("DOMContentLoaded", function() {
    
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    // On tente de récupérer le shop de l'URL, sinon du stockage local
    const shop = params.get('shop') || sessionStorage.getItem('shop');

    // On sauvegarde le shop si on l'a trouvé
    if(shop) sessionStorage.setItem('shop', shop);

    document.body.style.display = 'block';

    if (mode === 'client') {
        document.body.classList.add('client-mode');
    }

    // --- FONCTIONS ---

    window.preview = function(input, imgId, placeholderId) {
        const file = input.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                document.getElementById(imgId).src = e.target.result;
                document.getElementById(imgId).style.display = 'block';
                // On cache le placeholder (le texte et l'icône)
                if(placeholderId) document.getElementById(placeholderId).style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    };

    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const c = document.getElementById('cImg').files[0];
        
        if (!u || !c) return alert("Ajoutez les 2 photos !");

        const btn = document.getElementById('btnGo');
        btn.disabled = true;
        btn.innerText = "Génération...";

        const toBase64 = file => new Promise(r => {
            const reader = new FileReader();
            reader.readAsDataURL(file);
            reader.onload = () => r(reader.result);
        });

        try {
            // On utilise le shop récupéré plus haut, ou "demo" par défaut
            const currentShop = shop || "demo.myshopify.com";
            
            const res = await fetch('/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    shop: currentShop,
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
                // On cache le placeholder du résultat
                document.getElementById('phRes').style.display = 'none';
            } else {
                alert("Erreur: " + JSON.stringify(data));
            }
        } catch(e) {
            alert("Erreur technique: " + e.message);
        } finally {
            btn.disabled = false;
            btn.innerText = "Générer";
        }
    };

    // Fonction d'achat corrigée pour envoyer le shop
    window.buy = async function(packId) {
        const currentShop = shop;
        if (!currentShop) {
            alert("Erreur: Impossible de déterminer la boutique. Veuillez recharger l'application depuis Shopify.");
            return;
        }

        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    shop: currentShop,
                    pack_id: packId
                })
            });
            const data = await res.json();
            if(data.confirmation_url) {
                // Redirection vers la page de paiement Shopify
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Erreur lors de la création du paiement. (Vérifiez les logs serveur)");
            }
        } catch(e) {
            alert("Erreur de connexion au serveur de paiement.");
        }
    }
});
