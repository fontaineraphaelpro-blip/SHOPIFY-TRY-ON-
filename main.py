document.addEventListener("DOMContentLoaded", async function() {
    const params = new URLSearchParams(window.location.search);
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    if(shop) sessionStorage.setItem('shop', shop);

    // Initialisation
    async function fetchCredits(s) {
        try {
            // Shopify injecte parfois le token dans l'URL, on le récupère en priorité
            let token = new URLSearchParams(window.location.search).get('id_token');
            if (!token && window.shopify) {
                token = await window.shopify.idToken();
            }

            const res = await fetch(`/api/get-credits?shop=${s}`, {
                headers: { "Authorization": `Bearer ${token}` }
            });
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits || 10;
        } catch(e) { 
            console.error(e);
            document.getElementById('credits').innerText = "10"; // Fallback visuel
        }
    }

    if(shop) fetchCredits(shop);

    window.buy = async function(packId) {
        const btn = event.currentTarget.tagName === 'BUTTON' ? event.currentTarget : event.target.closest('button');
        btn.innerText = "Redirecting...";
        
        try {
            const token = await window.shopify.idToken();
            const res = await fetch('/api/buy-credits', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ shop: shop, pack_id: packId })
            });
            const data = await res.json();
            if(data.confirmation_url) {
                window.top.location.href = data.confirmation_url;
            }
        } catch(e) { alert("Error: " + e); btn.innerText = "Select"; }
    };
});
