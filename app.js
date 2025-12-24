document.addEventListener("DOMContentLoaded", async () => {
    document.body.classList.add("loaded");

    const params = new URLSearchParams(window.location.search);
    const shop = params.get("shop");
    const token = params.get("token");

    if (!shop || !token) {
        document.body.innerHTML = "<h1>Erreur : App non authentifiée ou Shop manquant</h1>";
        return;
    }

    // --- Fetch credits ---
    async function fetchCredits() {
        const res = await fetch(`/api/get-credits?shop=${shop}&token=${token}`);
        const data = await res.json();
        document.getElementById("credits").innerText = data.credits || 0;
    }
    fetchCredits();

    // --- Buy Pack ---
    window.buy = async function(event, packId) {
        event.preventDefault();
        const btn = event.currentTarget;
        const oldText = btn.innerText;
        btn.innerText = "Redirecting...";
        btn.disabled = true;

        try {
            const res = await fetch("/api/buy-credits", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ shop, pack_id: packId, token })
            });
            const data = await res.json();
            if (data.confirmation_url) window.top.location.href = data.confirmation_url;
            else throw new Error(data.error || "Unknown error");
        } catch (e) {
            console.error(e);
            btn.innerText = oldText;
            btn.disabled = false;
            alert("Erreur achat pack");
        }
    };

    // --- Buy Custom Pack ---
    window.buyCustom = async () => {
        const amount = parseInt(document.getElementById("customAmount").value);
        if (isNaN(amount) || amount < 200) return alert("Montant min 200");

        const res = await fetch("/api/buy-custom", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ shop, amount, token })
        });
        const data = await res.json();
        if (data.confirmation_url) window.top.location.href = data.confirmation_url;
        else alert("Erreur custom pack");
    };
});
