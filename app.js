/**
 * APP.JS - Logique Client pour StyleLab
 */

// --- 1. CONFIGURATION & RÉCUPÉRATION PARAMÈTRES ---

// Récupération des paramètres URL (Shopify App Bridge)
const urlParams = new URLSearchParams(window.location.search);

// On nettoie l'URL pour être sûr (parfois c'est test.myshopify.com, parfois https://test...)
let SHOP_URL = urlParams.get('shop');
const APP_MODE = urlParams.get('mode'); 

// Persistance de la session : On stocke le shop pour ne jamais le perdre au rechargement
if (SHOP_URL) {
    sessionStorage.setItem('stylelab_shop', SHOP_URL);
} else {
    // Si l'URL ne l'a pas, on le cherche dans la mémoire du navigateur
    SHOP_URL = sessionStorage.getItem('stylelab_shop');
}

console.log("🚀 App démarrée pour la boutique :", SHOP_URL);


// --- 2. INITIALISATION AU CHARGEMENT ---

document.addEventListener("DOMContentLoaded", function() {
    
    // Vérification de sécurité de base
    if (!SHOP_URL) {
        console.error("⚠️ Shop URL manquant. L'application ne peut pas fonctionner.");
        // Optionnel : Afficher un message d'erreur visuel
        return;
    }

    // Gestion de l'affichage : Admin (Tableau de bord) vs Client (Widget)
    if (APP_MODE === 'client') {
        // --- MODE CLIENT (Widget sur la boutique) ---
        const adminPanel = document.getElementById('adminPanel');
        if(adminPanel) adminPanel.style.display = 'none';
        
        const clientHeader = document.getElementById('clientHeader');
        if(clientHeader) clientHeader.style.display = 'flex';
        
        // Rendre le fond transparent pour l'iframe du widget
        document.body.style.background = 'transparent';
        document.body.style.padding = '0';

    } else {
        // --- MODE ADMIN (Dans Shopify Admin) ---
        const adminPanel = document.getElementById('adminPanel');
        if(adminPanel) adminPanel.style.display = 'block';
        
        const clientHeader = document.getElementById('clientHeader');
        if(clientHeader) clientHeader.style.display = 'none';
        
        // On charge les crédits immédiatement
        fetchCredits();
    }
});


// --- 3. FONCTIONS API (COMMUNICATION AVEC LE SERVEUR) ---

// A. Récupérer les crédits
async function fetchCredits() {
    if (!SHOP_URL) return;
    try {
        const res = await fetch(`/api/get-credits?shop=${SHOP_URL}`);
        
        if (res.status === 401) {
             console.log("Session expirée, rechargement nécessaire...");
             // Ici on pourrait rediriger vers /login si besoin
             return;
        }
        
        const data = await res.json();
        const el = document.getElementById('adminCredits');
        if (el) el.innerText = data.credits;
        
    } catch (e) {
        console.error("Erreur récupération crédits:", e);
    }
}

// B. Acheter un pack (Paiement)
async function buyPack(packId) {
    if (!SHOP_URL) return alert("Erreur: Boutique non identifiée");
    
    try {
        const res = await fetch('/api/buy-credits', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                shop: SHOP_URL, 
                pack_id: packId 
            }) 
        });
        
        const data = await res.json();
        
        if (data.confirmation_url) {
            // CRUCIAL : On utilise window.top pour sortir de l'iframe Shopify et aller payer
            window.top.location.href = data.confirmation_url;
        } else {
            alert("Erreur lors de la création du paiement : " + JSON.stringify(data));
        }
    } catch (e) {
        alert("Erreur connexion serveur : " + e);
    }
}

// C. Générer l'essayage (IA)
async function startTryOn() {
    const userFile = document.getElementById('userImage').files[0];
    const clothFile = document.getElementById('clothingImage').files[0];
    const category = document.getElementById('categorySelect').value;
    
    // Validation
    if (!userFile || !clothFile) {
        alert("Veuillez ajouter une photo de vous ET du vêtement !");
        return;
    }
    
    if (!SHOP_URL) {
        alert("Erreur critique : Impossible d'identifier la boutique. Rafraichissez la page.");
        return;
    }

    // UI : État de chargement
    const btn = document.getElementById('generateButton');
    const loading = document.getElementById('loadingMessage');
    const resultImg = document.getElementById('resultImage');
    const resultPlaceholder = document.getElementById('resultPlaceholder');

    btn.disabled = true;
    loading.style.display = 'block';
    resultImg.style.display = 'none';
    if(resultPlaceholder) resultPlaceholder.style.display = 'block';

    try {
        // Conversion images en Base64
        const userBase64 = await toBase64(userFile);
        const clothBase64 = await toBase64(clothFile);

        // Appel API
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                shop: SHOP_URL, // Indispensable pour savoir qui débiter
                person_image_url: userBase64,
                clothing_image_url: clothBase64,
                category: category
            })
        });

        const data = await response.json();

        if (response.ok) {
            // Succès
            resultImg.src = data.result_image_url;
            resultImg.style.display = 'block';
            if(resultPlaceholder) resultPlaceholder.style.display = 'none';
            
            // Lien téléchargement
            const dlLink = document.getElementById('downloadLink');
            if(dlLink) {
                dlLink.href = data.result_image_url;
                dlLink.style.display = 'inline-block';
            }

            // Mise à jour des crédits (si on est en mode Admin)
            if (APP_MODE !== 'client') {
                 fetchCredits(); 
            }
        } else {
            // Erreur API (ex: plus de crédits)
            alert("Erreur : " + (data.detail || "Problème inconnu"));
        }

    } catch (error) {
        console.error(error);
        alert("Erreur technique. Vérifiez la console.");
    } finally {
        // Reset UI
        btn.disabled = false;
        loading.style.display = 'none';
    }
}


// --- 4. UTILITAIRES ---

// Prévisualisation d'image locale avant envoi
function previewImage(inputId, imgId, placeholderId) {
    const input = document.getElementById(inputId);
    const img = document.getElementById(imgId);
    const placeholder = document.getElementById(placeholderId);
    
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            img.src = e.target.result;
            img.style.display = 'block';
            if(placeholder) placeholder.style.display = 'none';
        }
        reader.readAsDataURL(input.files[0]);
    }
}

// Conversion Fichier -> Base64
function toBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve(reader.result);
        reader.onerror = error => reject(error);
    });
}
