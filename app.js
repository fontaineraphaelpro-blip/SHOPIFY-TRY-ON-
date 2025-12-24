document.addEventListener("DOMContentLoaded", async function() {
    const params = new URLSearchParams(window.location.search);
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    if(shop) sessionStorage.setItem('shop', shop);

    // --- FONCTION POUR OBTENIR LE TOKEN ---
    async function getShopifyToken() {
        if (window.shopify && window.shopify.idToken) {
            return await window.shopify.idToken();
        }
        // Fallback sur l'URL si App Bridge n'est pas encore prêt
        return new URLSearchParams(window.location.search).get('id_token');
    }

    // --- AFFICHAGE DES CRÉDITS ---
    async function fetchCredits(s) {
        try {
            const token = await getShopifyToken();
            const res = await fetch(`/api/get-credits?shop=${s}`, {
                headers: { "Authorization": `Bearer ${token}` }
            });
            
            if (res.status === 401) {
                window.top.location.href = `/login?shop=${s}`;
                return;
            }
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) { 
            console.error("Erreur crédits:", e);
            document.getElementById('credits').innerText = "10"; 
        }
    }

    if(shop) fetchCredits(shop);

    // --- FONCTION D'ACHAT CORRIGÉE ---
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
                // IMPORTANT: window.top.location force la sortie de l'iframe
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Erreur: " + (data.error || "Inconnue"));
                btn.innerText = oldText;
                btn.disabled = false;
            }
        } catch(e) {
            console.error("Erreur Achat:", e);
            btn.innerText = oldText;
            btn.disabled = false;
        }
    };
});
