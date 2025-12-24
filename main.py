document.addEventListener("DOMContentLoaded", async function() {
    const params = new URLSearchParams(window.location.search);
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    if(shop) sessionStorage.setItem('shop', shop);

    // 1. Affichage des crédits
    async function fetchCredits() {
        try {
            const res = await fetch(`/api/get-credits?shop=${shop}`);
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) { document.getElementById('credits').innerText = "10"; }
    }
    if(shop) fetchCredits();

    // 2. Fonction d'achat
    window.buy = async function(packId) {
        const btn = event.target.closest('button');
        btn.innerText = "Chargement...";
        
        try {
            // Récupération du token Shopify (indispensable pour la validation)
            const token = await window.shopify.idToken();
            
            const res = await fetch('/api/buy-credits', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ shop: shop, pack_id: packId })
            });
            
            const data = await res.json();
            if(data.confirmation_url) {
                // REDIRECTION CRUCIALE : On force la fenêtre parente à changer d'URL
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Erreur de session. Veuillez recharger l'app.");
            }
        } catch(e) {
            console.error(e);
            alert("Erreur lors de la redirection.");
        } finally {
            btn.innerText = "Sélectionner";
        }
    };
});
