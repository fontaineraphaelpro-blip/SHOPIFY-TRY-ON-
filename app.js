// Exécution automatique au chargement de la page
document.addEventListener("DOMContentLoaded", function() {
    const params = new URLSearchParams(window.location.search);
    const shop = params.get("shop");

    if (shop) {
        console.log("Detecting shop:", shop);
        fetchCredits(shop);
    } else {
        console.error("No shop domain detected in URL parameters.");
    }
});

/**
 * Récupère le nombre de crédits via l'API FastAPI
 */
async function fetchCredits(shop) {
    try {
        const response = await fetch(`/api/get-credits?shop=${shop}`);
        if (!response.ok) throw new Error("API response error");
        
        const data = await response.json();
        const creditsElement = document.getElementById("credits-count");
        
        if (creditsElement) {
            // Remplace "undefined" par 0 ou la valeur réelle
            creditsElement.innerText = (data.credits !== undefined) ? data.credits : 0;
        }
    } catch (error) {
        console.error("Failed to fetch credits:", error);
        document.getElementById("credits-count").innerText = "0";
    }
}

/**
 * Redirige vers Shopify Billing pour l'achat d'un pack
 */
async function buyPack(packId) {
    const params = new URLSearchParams(window.location.search);
    const shop = params.get("shop");
    
    if (!shop) {
        alert("Error: Shop domain not found.");
        return;
    }

    try {
        const response = await fetch("/api/buy-credits", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                shop: shop, 
                pack_id: packId 
            })
        });
        
        const data = await response.json();
        
        if (data.confirmation_url) {
            // Redirection vers l'URL de confirmation de paiement Shopify
            window.top.location.href = data.confirmation_url;
        } else if (data.error) {
            alert("Billing Error: " + data.error);
        }
    } catch (error) {
        console.error("Purchase failed:", error);
    }
}

/**
 * Gère l'achat de packs personnalisés (Enterprise)
 */
async function buyCustom() {
    const amount = document.getElementById("custom-amt").value;
    const params = new URLSearchParams(window.location.search);
    const shop = params.get("shop");

    const response = await fetch("/api/buy-credits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
            shop: shop, 
            pack_id: 'pack_custom', 
            custom_amount: parseInt(amount) 
        })
    });
    
    const data = await response.json();
    if (data.confirmation_url) {
        window.top.location.href = data.confirmation_url;
    }
}
