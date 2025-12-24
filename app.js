document.addEventListener("DOMContentLoaded", async function() {
    document.body.classList.add('loaded');
    
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image'); 
    
    if(shop) sessionStorage.setItem('shop', shop);

    if (mode === 'client') {
        document.getElementById('admin-dashboard').style.display = 'none';
        document.getElementById('studio-interface').style.display = 'block';
        document.getElementById('client-title').style.display = 'block';
    } else {
        if(shop) fetchCredits(shop);
    }

    async function fetchCredits(s) {
        try {
            const token = await window.shopify.idToken();
            const res = await fetch(`/api/get-credits?shop=${s}`, {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.status === 401) return; 
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) { console.error("Erreur Credits:", e); }
    }

    // --- LA FONCTION CORRIGÉE ---
    window.buy = async function(packId) {
        if(!shop) return alert("Shop ID missing");
        
        let btn = event.currentTarget.tagName === 'BUTTON' ? event.currentTarget : event.target.closest('button');
        const oldText = btn.innerText;
        btn.innerText = "Redirecting...";
        btn.disabled = true;

        try {
            const token = await window.shopify.idToken();
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
                // SOLUTION : Redirection forcée via App Bridge pour sortir de l'iframe
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

    window.buyCustom = async function() {
        const amount = document.getElementById('customAmount').value;
        try {
            const token = await window.shopify.idToken();
            const res = await fetch('/api/buy-credits', {
                 method: 'POST', 
                 headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                 body: JSON.stringify({ shop: shop, pack_id: 'pack_custom', custom_amount: parseInt(amount) })
            });
            const data = await res.json();
            if(data.confirmation_url) window.top.location.href = data.confirmation_url;
        } catch(e) { console.error(e); }
    };

    // ... (Le reste de tes fonctions preview et generate ne changent pas)
});
