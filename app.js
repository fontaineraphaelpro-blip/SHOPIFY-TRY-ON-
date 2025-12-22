// Récupération des paramètres URL
const urlParams = new URLSearchParams(window.location.search);
const SHOP_URL = urlParams.get('shop');
const APP_MODE = urlParams.get('mode'); // Récupère "client" ou null

// --- GESTION DE L'AFFICHAGE CLIENT VS ADMIN ---
document.addEventListener("DOMContentLoaded", function() {
    
    // Si on est en mode "Client" (sur la boutique)
    if (APP_MODE === 'client') {
        const headerActions = document.querySelector('.header-actions');
        if (headerActions) {
            headerActions.style.display = 'none'; // Cache le bouton payer et les crédits
        }
        // Change le titre pour faire plus "Service"
        const logo = document.querySelector('.logo');
        if (logo) logo.innerHTML = "✨ Cabine d'Essayage";
    } 
    // Sinon (Admin), on charge les crédits normalement
    else {
        fetchCredits();
    }
});

// --- FONCTIONS EXISTANTES ---

async function fetchCredits() {
    if (!SHOP_URL) return;
    try {
        const res = await fetch(`/api/get-credits?shop=${SHOP_URL}`);
        const data = await res.json();
        const el = document.getElementById('creditsLeft');
        if (el) el.innerText = data.credits;
    } catch (e) {
        console.error("Erreur crédits:", e);
    }
}

function previewImage(inputId, imgId, placeholderId) {
    const input = document.getElementById(inputId);
    const img = document.getElementById(imgId);
    const placeholder = document.getElementById(placeholderId);
    
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            img.src = e.target.result;
            img.style.display = 'block';
            placeholder.style.display = 'none';
        }
        reader.readAsDataURL(input.files[0]);
    }
}

async function startTryOn() {
    const userFile = document.getElementById('userImage').files[0];
    const clothFile = document.getElementById('clothingImage').files[0];
    const category = document.getElementById('categorySelect').value;
    
    if (!userFile || !clothFile) {
        alert("Veuillez ajouter une photo de vous et du vêtement !");
        return;
    }

    // Afficher le chargement
    document.getElementById('generateButton').disabled = true;
    document.getElementById('loadingMessage').style.display = 'block';
    document.getElementById('resultImage').style.display = 'none';
    document.getElementById('resultPlaceholder').style.display = 'block';

    try {
        // 1. Convertir les images en Base64 pour l'envoi
        const userBase64 = await toBase64(userFile);
        const clothBase64 = await toBase64(clothFile);

        // 2. Appel API
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                shop: SHOP_URL,
                person_image_url: userBase64,
                clothing_image_url: clothBase64,
                category: category
            })
        });

        const data = await response.json();

        if (response.ok) {
            // Affichage du résultat
            const resultImg = document.getElementById('resultImage');
            resultImg.src = data.result_image_url;
            resultImg.style.display = 'block';
            document.getElementById('resultPlaceholder').style.display = 'none';
            
            // Bouton de téléchargement
            const dlLink = document.getElementById('downloadLink');
            if(dlLink) {
                dlLink.href = data.result_image_url;
                dlLink.style.display = 'block';
            }

            // Mise à jour des crédits seulement si on est admin
            if (APP_MODE !== 'client') {
                 fetchCredits(); 
            }
        } else {
            alert("Erreur : " + (data.detail || "Problème inconnu"));
        }

    } catch (error) {
        console.error(error);
        alert("Erreur technique. Vérifiez la console.");
    } finally {
        document.getElementById('generateButton').disabled = false;
        document.getElementById('loadingMessage').style.display = 'none';
    }
}

function toBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve(reader.result);
        reader.onerror = error => reject(error);
    });
}

// --- GESTION PAIEMENT (Visible seulement pour Admin) ---
function openPricing() {
    document.getElementById('pricingModal').style.display = 'flex';
}
function closePricing() {
    document.getElementById('pricingModal').style.display = 'none';
}

async function buyPack(packId) {
    if (!SHOP_URL) return alert("Erreur de boutique");
    
    try {
        const res = await fetch('/api/buy-credits', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ shop: SHOP_URL, pack_id: packId })
        });
        const data = await res.json();
        if (data.confirmation_url) {
            window.top.location.href = data.confirmation_url;
        } else {
            alert("Erreur création paiement");
        }
    } catch (e) {
        alert("Erreur : " + e);
    }
}
