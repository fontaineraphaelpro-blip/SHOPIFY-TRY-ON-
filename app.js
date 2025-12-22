document.addEventListener("DOMContentLoaded", function() {
    
    // 1. RECUPERATION DES PARAMETRES
    const params = new URLSearchParams(window.location.search);
    const SHOP = params.get('shop') || sessionStorage.getItem('shop');
    const MODE = params.get('mode'); // 'client' ou null

    if(SHOP) sessionStorage.setItem('shop', SHOP);

    // 2. LOGIQUE D'AFFICHAGE (LE COEUR DU PROBLEME)
    if (MODE === 'client') {
        // C'EST LE CLIENT SUR LA BOUTIQUE
        document.body.classList.add('client-mode');
        document.getElementById('client-title').style.display = 'block'; // Affiche titre "Cabine"
        document.body.style.display = 'block'; // Affiche la page
    } else {
        // C'EST TOI (ADMIN)
        if(SHOP) {
            fetchCredits(); // On ne charge les crédits que pour l'admin
            document.body.style.display = 'block';
        } else {
            document.body.innerHTML = "<h1 style='text-align:center; margin-top:50px'>Accès Admin Refusé (Shop manquant)</h1>";
            document.body.style.display = 'block';
        }
    }

    // 3. FONCTIONS (Crédits, Achat, IA)
    
    window.preview = function(inputId, imgId, phId) {
        const file = document.getElementById(inputId).files[0];
        if(file) {
            const r = new FileReader();
            r.onload = e => {
                document.getElementById(imgId).src = e.target.result;
                document.getElementById(imgId).style.display = 'block';
                document.getElementById(phId).style.display = 'none';
            };
            r.readAsDataURL(file);
        }
    }

    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const c = document.getElementById('cImg').files[0];
        if(!u || !c) return alert("Veuillez ajouter les 2 photos.");

        const btn = document.getElementById('btnGo');
        const load = document.getElementById('loading');
        
        btn.disabled = true; 
        load.style.display = 'block';

        const to64 = f => new Promise(r => { const fr=new FileReader(); fr.onload=()=>r(fr.result); fr.readAsDataURL(f); });

        try {
            const res = await fetch('/api/generate', {
                method: 'POST', 
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({
                    shop: SHOP, 
                    person_image_url: await to64(u), 
                    clothing_image_url: await to64(c), 
                    category: "upper_body"
                })
            });
            const data = await res.json();
            
            if(res.ok) {
                document.getElementById('resImg').src = data.result_image_url;
                document.getElementById('resImg').style.display = 'block';
                if(MODE !== 'client') fetchCredits(); // Mise à jour crédits (Admin seulement)
            } else {
                alert("Erreur: " + (data.detail || "Erreur inconnue"));
            }
        } catch(e) {
            console.error(e);
            alert("Erreur technique");
        } finally {
            btn.disabled = false;
            load.style.display = 'none';
        }
    }

    async function fetchCredits() {
        try {
            const res = await fetch(`/api/get-credits?shop=${SHOP}`);
            if(res.status === 401) return window.location.reload();
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) { console.error(e); }
    }

    window.buy = async function(packId) {
        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST', 
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({shop: SHOP, pack_id: packId})
            });
            const data = await res.json();
            if(data.confirmation_url) window.top.location.href = data.confirmation_url;
        } catch(e) { alert("Erreur connexion paiement"); }
    }
});
