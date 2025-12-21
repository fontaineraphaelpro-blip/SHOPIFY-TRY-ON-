// --- 1. CONFIGURATION ---
// Récupère l'URL du shop depuis l'URL (ex: ?shop=ma-boutique.myshopify.com)
const urlParams = new URLSearchParams(window.location.search);
const SHOP_URL = urlParams.get('shop');

// --- 2. CLOUDINARY (On garde ton code qui marche) ---
const CLOUDINARY_FETCH_URL = 'https://api.cloudinary.com/v1_1/dbhxjrj8c/image/upload';

async function uploadToCloudinary(file) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('upload_preset', 'tryon_upload'); 
    formData.append('cloud_name', 'dbhxjrj8c'); 
    
    const response = await fetch(CLOUDINARY_FETCH_URL, { method: 'POST', body: formData });
    const data = await response.json();
    return data.secure_url;
}

// --- 3. LOGIQUE SHOPIFY ---

// Chargement initial
window.onload = async function() {
    if(!SHOP_URL) {
        alert("Erreur: App lancée hors de Shopify.");
        return;
    }
    
    // Récupérer les crédits depuis NOTRE backend
    const res = await fetch(`/api/get-credits?shop=${SHOP_URL}`);
    const data = await res.json();
    document.getElementById('creditsLeft').innerText = data.credits;
    
    // Check message succès paiement
    if (urlParams.get('success') === 'true') {
        alert("🎉 Paiement réussi ! Crédits ajoutés.");
        // Nettoyer l'URL
        window.history.replaceState({}, document.title, `/?shop=${SHOP_URL}`);
    }
};

// Fonctions UI
function openPricing() { document.getElementById('pricingModal').style.display = 'flex'; }
function closePricing() { document.getElementById('pricingModal').style.display = 'none'; }
function previewImage(inputId, previewId, placeholderId) {
    const input = document.getElementById(inputId);
    const preview = document.getElementById(previewId);
    const placeholder = document.getElementById(placeholderId);
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            preview.src = e.target.result;
            preview.style.display = 'block';
            placeholder.style.display = 'none';
        };
        reader.readAsDataURL(input.files[0]);
    }
}

// PAIEMENT (Nouveau Flow Shopify)
async function buyPack(packId) {
    try {
        const response = await fetch('/api/buy-credits', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ shop: SHOP_URL, pack_id: packId }) 
        });
        const data = await response.json();
        
        if(data.confirmation_url) {
            // REDIRECTION SPÉCIALE SHOPIFY
            // On doit sortir de l'iframe pour aller payer
            window.top.location.href = data.confirmation_url;
        } else {
            alert("Erreur création paiement");
        }
    } catch (e) {
        console.error(e);
        alert("Erreur serveur.");
    }
}

// GENERATION (Nouvel appel sécurisé)
async function startTryOn() {
    const userFile = document.getElementById('userImage').files[0];
    const clothingFile = document.getElementById('clothingImage').files[0];
    
    if (!userFile || !clothingFile) { alert("Mettez les 2 photos !"); return; }
    
    // UI Loading
    document.getElementById('loadingMessage').style.display = 'block';
    document.getElementById('generateButton').disabled = true;

    try {
        // 1. Upload Cloudinary (Client side)
        const [userUrl, clothingUrl] = await Promise.all([
            uploadToCloudinary(userFile),
            uploadToCloudinary(clothingFile)
        ]);

        // 2. Appel Backend (Qui appellera Replicate)
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                shop: SHOP_URL,
                person_image_url: userUrl,
                clothing_image_url: clothingUrl,
                category: document.getElementById('categorySelect').value
            })
        });

        const data = await response.json();
        
        if (!response.ok) throw new Error(data.detail || "Erreur Backend");

        // Succès
        document.getElementById('resultImage').src = data.result_image_url;
        document.getElementById('resultImage').style.display = 'block';
        document.getElementById('resultPlaceholder').style.display = 'none';
        
        // Update crédits visuel
        document.getElementById('creditsLeft').innerText = data.credits_remaining;

    } catch (error) {
        alert("Erreur: " + error.message);
    } finally {
        document.getElementById('loadingMessage').style.display = 'none';
        document.getElementById('generateButton').disabled = false;
    }
}