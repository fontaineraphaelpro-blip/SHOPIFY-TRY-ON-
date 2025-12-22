// Récupération des paramètres URL
const urlParams = new URLSearchParams(window.location.search);
const SHOP_URL = urlParams.get('shop');
const APP_MODE = urlParams.get('mode'); // "client" ou null (admin)

document.addEventListener("DOMContentLoaded", function() {
    
    // --- MODE CLIENT ---
    if (APP_MODE === 'client') {
        // On cache le panneau admin
        document.getElementById('adminPanel').style.display = 'none';
        // On s'assure que le header client est visible
        document.getElementById('clientHeader').style.display = 'flex';
        // On adapte le style pour l'intégration "App Block"
        document.body.style.background = 'transparent';
        document.body.style.padding = '0';
    } 
    // --- MODE ADMIN (Propriétaire) ---
    else {
        // On affiche le Dashboard Admin
        document.getElementById('adminPanel').style.display = 'block';
        // On cache le petit header client (inutile car on a le dashboard)
        document.getElementById('clientHeader').style.display = 'none';
        
        // On va chercher les crédits pour le dashboard
        fetchCredits();
    }
});

// --- FONCTIONS ---

async function fetchCredits() {
    if (!SHOP_URL) return;
    try {
        const res = await fetch(`/api/get-credits?shop=${SHOP_URL}`);
        const data = await res.json();
        
        // Mise à jour du GROS compteur Admin
        const adminCounter = document.getElementById('adminCredits');
        if (adminCounter) adminCounter.innerText = data.credits;

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

    document.getElementById('generateButton').disabled = true;
    document.getElementById('loadingMessage').style.display = 'block';
    document.getElementById('resultImage').style.display = 'none';
    document.getElementById('resultPlaceholder').style.display = 'block';

    try {
        const userBase64 = await toBase64(userFile);
        const clothBase64 = await toBase64(clothFile);

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
            const resultImg = document.getElementById('resultImage');
            resultImg.src = data.result_image_url;
            resultImg.style.display = 'block';
            document.getElementById('resultPlaceholder').style.display = 'none';
            
            const dlLink = document.getElementById('downloadLink');
            if(dlLink) {
                dlLink.href = data.result_image_url;
                dlLink.style.display = 'inline-block';
            }

            // Si on est Admin, on met à jour le compteur en temps réel
            if (APP_MODE !== 'client') {
                 fetchCredits(); 
            }
        } else {
            alert("Erreur : " + (data.detail || "Problème inconnu"));
        }

    } catch (error) {
        console.error(error);
        alert("Erreur technique.");
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

// Fonction de paiement directe (boutons du dashboard)
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
            alert("Erreur lors de la création du paiement.");
        }
    } catch (e) {
        alert("Erreur de connexion : " + e);
    }
}
