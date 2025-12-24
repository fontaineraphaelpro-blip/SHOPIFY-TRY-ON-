document.addEventListener("DOMContentLoaded", async () => {
    const params = new URLSearchParams(window.location.search);
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    if (!shop) {
        document.body.innerHTML = "<h2>Missing shop parameter. Open from Shopify Admin</h2>";
        return;
    }
    sessionStorage.setItem('shop', shop);

    const AppBridge = window['app-bridge'];
    const createApp = AppBridge.default;
    const app = createApp({
        apiKey: "TON_API_KEY_SHOPIFY",
        shopOrigin: shop,
        forceRedirect: true
    });

    const getSessionToken = window['app-bridge-utils'].getSessionToken;

    async function fetchCredits() {
        try {
            const token = await getSessionToken(app);
            const res = await fetch(`/api/get-credits?shop=${shop}`, {
                headers: { "Authorization": `Bearer ${token}` }
            });
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) {
            console.error("Erreur crédits:", e);
            document.getElementById('credits').innerText = "Error"; 
        }
    }

    await fetchCredits();

    window.buy = async function(packId) {
        const token = await getSessionToken(app);

        try {
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
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Erreur achat");
            }
        } catch(e) {
            console.error("Erreur Achat:", e);
        }
    };
});
