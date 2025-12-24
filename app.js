window.buy = null;

document.addEventListener("DOMContentLoaded", async function() {
    const params = new URLSearchParams(window.location.search);
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    if(shop) sessionStorage.setItem('shop', shop);

    // --- FONCTION POUR OBTENIR LE TOKEN (SÉCURISÉE) ---
    async function getShopifyToken() {
        try {
            // 1. Essayer la méthode officielle App Bridge
            return await window.shopify.idToken();
        } catch (e) {
            // 2. Si ça échoue, extraire le token de l'URL (vu dans tes logs F12)
            const urlParams = new URLSearchParams(window.location.search);
            const tokenFromUrl = urlParams.get('id_token');
            if (tokenFromUrl) return tokenFromUrl;
            throw new Error("Impossible de récupérer le jeton de session");
        }
    }

    async function fetchCredits(s) {
        try {
            const token = await getShopifyToken();
            const res = await fetch(`/api/get-credits?shop=${s}`, {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.status === 401) {
                window.location.href = `/login?shop=${s}`;
                return;
            }
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) { console.error("Erreur Credits:", e); }
    }

    if (shop && !window.location.search.includes('mode=client')) {
        fetchCredits(shop);
    }

    // --- FONCTION D'ACHAT ---
    window.buy = async function(packId) {
        if(!shop) return alert("Shop ID missing");
        
        const btn = event.currentTarget.tagName === 'BUTTON' ? event.currentTarget : event.target.closest('button');
        const oldText = btn.innerText;
        btn.innerText = "Redirecting...";
        btn.disabled = true;

        try {
            const token = await getShopifyToken();
            
            const res = await fetch('/api/buy-credits', {
                method: 'POST', 
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ shop: shop, pack_id: packId })
            });

            const data = await res.json();
            
            if(data.confirmation_url) {
                // Utilisation de window.top.location pour sortir de l'iframe vers le paiement
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Erreur: " + (data.error || "Inconnue"));
                btn.innerText = oldText;
                btn.disabled = false;
            }
        } catch(e) {
            console.error("Erreur Achat:", e);
            alert("Erreur Shopify: " + e.message);
            btn.innerText = oldText;
            btn.disabled = false;
        }
    };
});
