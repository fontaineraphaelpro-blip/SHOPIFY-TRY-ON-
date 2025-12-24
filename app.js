document.addEventListener("DOMContentLoaded", () => {
    document.body.classList.add("loaded");

    // --- Vérifie si embedded et récupère id_token ---
    const urlParams = new URLSearchParams(window.location.search);
    const idToken = urlParams.get("id_token");
    const shop = urlParams.get("shop");

    if (!idToken || !shop) {
        document.body.innerHTML = "<h1>Erreur : app non authentifiée</h1>";
        return;
    }

    // --- Exemple fetch pour récupérer crédits ---
    fetch(`/api/get-credits?shop=${shop}`, {
        headers: {
            "Authorization": `Bearer ${idToken}`
        }
    })
    .then(res => res.json())
    .then(data => {
        document.body.innerHTML = `
            <div style="padding:20px; max-width:600px; margin:auto;">
                <h1>Bienvenue dans VTON Magic</h1>
                <p>Crédits disponibles : <strong>${data.credits}</strong></p>
            </div>
        `;
    })
    .catch(err => {
        console.error(err);
        document.body.innerHTML = "<h1>Erreur de récupération des crédits</h1>";
    });
});
