document.addEventListener("DOMContentLoaded", function() {
    // 1. Initialisation des variables
    const params = new URLSearchParams(window.location.search);
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image'); 
    
    if(shop) {
        sessionStorage.setItem('shop', shop);
        fetchCredits(shop);
    }

    // 2. Auto-remplissage du vêtement (Si venant d'une fiche produit Shopify)
    if (autoProductImage) {
        const imgC = document.getElementById('prevC');
        const cardC = document.getElementById('card-garment');
        if (imgC) {
            imgC.src = autoProductImage;
            imgC.style.display = 'block';
            imgC.parentElement.classList.add('has-image');
            // Cache les textes d'upload par défaut
            const labels = imgC.parentElement.querySelectorAll('i, .upload-text, .upload-icon, .upload-sub');
            labels.forEach(el => el.style.display = 'none');
        }
    }

    // --- FONCTIONS ACCESSIBLES PAR LE HTML (window.) ---

    // Prévisualisation des images uploadées
    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                img.parentElement.classList.add('has-image');
                const labels = img.parentElement.querySelectorAll('i, .upload-text, .upload-icon, .upload-sub');
                labels.forEach(el => el.style.display = 'none');
            };
            reader.readAsDataURL(file);
        }
    };

    // Lancement de la génération IA
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const btn = document.getElementById('btnGo');
        const currentShop = sessionStorage.getItem('shop');
        
        // Sécurité : On vérifie les deux images
        if (!uFile) return alert("Please upload your photo first.");
        if (!autoProductImage && !document.getElementById('cImg').files[0]) {
            return alert("Please select a garment first.");
        }

        // UI : Mode chargement
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> AI Magic...';
        
        document.getElementById('resZone').style.display = 'flex';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';

        // Préparation des données (Multipart pour la rapidité)
        const formData = new FormData();
        formData.append("shop", currentShop);
        formData.append("person_image", uFile);
        
        // On envoie soit l'URL auto, soit le fichier si l'utilisateur en a mis un autre
        const cFile = document.getElementById('cImg').files[0];
        formData.append("clothing_url", cFile ? cFile : autoProductImage);

        try {
            const res = await fetch('/api/generate', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            if (data.result_image_url) {
                const resImg = document.getElementById('resImg');
                resImg.src = data.result_image_url;
                resImg.style.display = 'block';
                document.getElementById('loader').style.display = 'none';
                
                // Mise à jour des crédits affichés
                if(data.new_credits !== undefined) {
                    document.getElementById('credits').innerText = data.new_credits;
                }
            } else {
                alert("AI Error: " + (data.error || "Unknown error"));
                resetUI();
            }
        } catch (e) {
            alert("Connection error to server");
            resetUI();
        } finally {
            btn.innerHTML = 'Test This Outfit Now <i class="fa-solid fa-wand-magic-sparkles"></i>';
            btn.disabled = false;
        }
    };

    // Gestion des achats de crédits
    window.buy = async function(packId, customAmount = 0) {
        const currentShop = sessionStorage.getItem('shop');
        if(!currentShop) return alert("Shop session lost. Please reload the app.");

        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    shop: currentShop, 
                    pack_id: packId, 
                    custom_amount: parseInt(customAmount) 
                })
            });
            const data = await res.json();
            if(data.confirmation_url) {
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Shopify Error: " + data.error);
            }
        } catch(e) {
            alert("Payment connection error");
        }
    };

    window.buyCustom = function() {
        const amount = document.getElementById('customAmount').value;
        if(amount < 200) return alert("Minimum 200 credits for custom packs.");
        window.buy('pack_custom', amount);
    };

    // --- FONCTIONS INTERNES ---

    async function fetchCredits(s) {
        try {
            const res = await fetch(`/api/get-credits?shop=${s}`);
            const data = await res.json();
            const creditEl = document.getElementById('credits');
            if(data.credits !== undefined && creditEl) {
                creditEl.innerText = data.credits;
            }
        } catch(e) {
            console.error("Could not load credits from Shopify Metafields");
        }
    }

    function resetUI() {
        document.getElementById('resZone').style.display = 'none';
        document.getElementById('loader').style.display = 'none';
    }
});
