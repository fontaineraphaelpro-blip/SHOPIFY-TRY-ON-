// --- RECUPERATION ROBUSTE DES PARAMETRES ---
// Shopify App Bridge ajoute le shop dans l'URL, on le capture ici
const urlParams = new URLSearchParams(window.location.search);
// On nettoie l'URL pour être sûr (parfois c'est test.myshopify.com, parfois https://test...)
let SHOP_URL = urlParams.get('shop');

// On stocke le shop dans la session pour ne jamais le perdre
if (SHOP_URL) {
    sessionStorage.setItem('stylelab_shop', SHOP_URL);
} else {
    SHOP_URL = sessionStorage.getItem('stylelab_shop');
}

const APP_MODE = urlParams.get('mode'); 

console.log("App démarrée pour la boutique :", SHOP_URL);

document.addEventListener("DOMContentLoaded", function() {
    // Gestion Admin vs Client
    if (APP_MODE === 'client') {
        const adminPanel = document.getElementById('adminPanel');
        if(adminPanel) adminPanel.style.display = 'none';
        
        const clientHeader = document.getElementById('clientHeader');
        if(clientHeader) clientHeader.style.display = 'flex';
        
        document.body.style.background = 'transparent';
        document.body.style.padding = '0';
    } else {
        const adminPanel = document.getElementById('adminPanel');
        if(adminPanel) adminPanel.style.display = 'block';
        
        const clientHeader = document.getElementById('clientHeader');
        if(clientHeader) clientHeader.style.display = 'none';
        
        // C'est ici que ça plantait avant : on vérifie que SHOP_URL existe
        if (SHOP_URL) {
            fetchCredits();
        } else {
            console.error("Impossible de charger les crédits : Shop URL manquant");
        }
    }
});

// --- API ---

async function fetchCredits() {
    if (!SHOP_URL) return;
    try {
        // ON AJOUTE BIEN LE SHOP DANS L'APPEL
        const res = await fetch(`/api/get-credits?shop=${SHOP_URL}`);
        if (res.status === 401) {
             console.log("Session expirée, rechargement...");
             return;
        }
        const data = await res.json();
        const el = document.getElementById('adminCredits');
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
    
    if (!SHOP_URL) {
        alert("Erreur critique : Impossible d'identifier la boutique. Rafraichissez la page.");
        return;
    }

    document.getElementById('generateButton').disabled = true;
    document.getElementById('loadingMessage').style.display = 'block';
    document.getElementById('resultImage').style.display = 'none';
    document.getElementById('resultPlaceholder').style.display = 'block';

    try {
        const userBase64 = await toBase64(userFile);
        const clothBase64 = await toBase64(clothFile);

        // ENVOI SÉCURISÉ AVEC LE SHOP
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                shop: SHOP_URL, // <--- C'est ça qui manquait parfois
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

async function buyPack(packId) {
    if (!SHOP_URL) return alert("Erreur: Boutique non identifiée");
    
    try {
        const res = await fetch('/api/buy-credits', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ shop: SHOP_URL, pack_id: packId }) // <--- INDISPENSABLE
        });
        const data = await res.json();
        
        if (data.confirmation_url) {
            // Pour sortir de l'iframe Shopify et aller payer
            window.top.location.href = data.confirmation_url;
        } else {
            alert("Erreur : " + JSON.stringify(data));
        }
    } catch (e) {
        alert("Erreur connexion : " + e);
    }
}
