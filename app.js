document.addEventListener("DOMContentLoaded", async () => {
    document.body.classList.add("loaded");

    const params = new URLSearchParams(window.location.search);
    const shop = params.get("shop") || sessionStorage.getItem("shop");
    const idToken = params.get("id_token");

    if (!shop || !idToken) {
        document.body.innerHTML = "<h1>Erreur : App non authentifiée ou Shop manquant</h1>";
        return;
    }

    sessionStorage.setItem("shop", shop);

    // --- FONCTION POUR OBTENIR LE TOKEN (ici idToken) ---
    async function getShopifyToken() {
        return idToken;
    }

    // --- AFFICHAGE DES CRÉDITS ---
    async function fetchCredits() {
        try {
            const token = await getShopifyToken();
            const res = await fetch(`/api/get-credits?shop=${shop}`, {
                headers: { "Authorization": `Bearer ${token}` }
            });

            if (res.status === 401) {
                window.top.location.href = `/login?shop=${shop}`;
                return;
            }

            const data = await res.json();
            const creditElem = document.getElementById("credits");
            if (creditElem) creditElem.innerText = data.credits;
        } catch (e) {
            console.error("Erreur crédits:", e);
            const creditElem = document.getElementById("credits");
            if (creditElem) creditElem.innerText = "10";
        }
    }

    fetchCredits();

    // --- ACHAT DE PACK ---
    window.buy = async function(packId, event) {
        if (!shop) return alert("Shop ID missing");

        const btn = event.currentTarget.tagName === "BUTTON"
            ? event.currentTarget
            : event.target.closest("button");
        const oldText = btn.innerText;
        btn.innerText = "Redirecting...";
        btn.disabled = true;

        try {
            const token = await getShopifyToken();
            const res = await fetch("/api/buy-credits", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({ shop, pack_id: packId })
            });

            const data = await res.json();

            if (data.confirmation_url) {
                // Sortie de l'iframe
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Erreur: " + (data.error || "Inconnue"));
                btn.innerText = oldText;
                btn.disabled = false;
            }
        } catch (e) {
            console.error("Erreur Achat:", e);
            btn.innerText = oldText;
            btn.disabled = false;
        }
    };

    // --- PACK CUSTOM ---
    window.buyCustom = async () => {
        const customAmount = parseInt(document.getElementById("customAmount").value);
        if (isNaN(customAmount) || customAmount < 1) return alert("Entrez un montant valide");
        // Pour l'instant on redirige vers un pack personnalisé (tu peux créer un endpoint /api/buy-custom)
        alert("Fonction Custom Pack non implémentée. Montant: " + customAmount);
    };
});
