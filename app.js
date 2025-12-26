document.addEventListener("DOMContentLoaded", function() {

    // 1. Récupération Paramètres
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode'); 
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image');

    if (shop) sessionStorage.setItem('shop', shop);

    console.log("VTON Init - Shop:", shop, "| Mode:", mode);

    // 2. Aiguillage
    if (mode === 'client') {
        initClientMode();
    } else if (shop) {
        initAdminMode(shop);
    }

    // --- MODE CLIENT (WIDGET SUR SITE) ---
    function initClientMode() {
        console.log("Activation Mode Client");
        document.body.classList.add('client-mode');
        
        // Cacher le dashboard admin
        const adminZone = document.getElementById('admin-only-zone');
        if(adminZone) adminZone.style.display = 'none';

        // GESTION IMAGE PRODUIT (Logique "Simple" appliquée au HTML "Complexe")
        if (autoProductImage) {
            // On cible la boite "Vêtement" (id cImg input, label parent)
            const garmentInput = document.getElementById('cImg');
            const garmentBox = garmentInput ? garmentInput.closest('label') : null;
            
            if (garmentBox) {
                // On affiche la boite, mais on empêche le clic (Lecture seule)
                garmentBox.style.display = 'flex'; 
                garmentBox.style.pointerEvents = 'none'; // Verrouillé
                garmentBox.style.borderStyle = 'solid';  // Style "Locked"
                
                // On insère l'image
                const img = document.getElementById('prevC');
                const emptyState = garmentBox.querySelector('.empty-state');
                
                if (img) {
                    let secureUrl = autoProductImage;
                    if(secureUrl.startsWith('//')) secureUrl = 'https:' + secureUrl;
                    
                    img.src = secureUrl;
                    img.style.display = 'block';
                }
                // On cache l'icône d'upload
                if (emptyState) emptyState.style.display = 'none';
            }
        }
        
        document.body.classList.add('loaded');
        document.body.style.opacity = "1";
    }

    // --- MODE ADMIN (DASHBOARD) ---
    async function initAdminMode(s) {
        // Authenticated fetch helper pour Shopify App Bridge
        async function authFetch(url) {
             if (window.shopify && window.shopify.id) {
                 const token = await shopify.id.getToken();
                 return fetch(url, { headers: { 'Authorization': `Bearer ${token}` } });
             }
             return fetch(url);
        }

        try {
            const res = await authFetch(`/api/get-data?shop=${s}`);
            if (res && res.ok) {
                const data = await res.json();
                const el = document.getElementById('credits');
                if(el) el.innerText = data.credits || 0;
            }
        } catch(e) { console.error("Admin Load Error", e); }
        
        document.body.classList.add('loaded');
        document.body.style.opacity = "1";
    }

    // --- PREVIEW (Pour l'upload utilisateur) ---
    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if(file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                const content = img.parentElement.querySelector('.empty-state');
                if(content) content.style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    };

    // --- FONCTION GENERATE (Logique Robuste) ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0]; // Photo User
        const btn = document.getElementById('btnGo');

        if (!shop) return alert("Erreur: Boutique non identifiée.");
        if (!uFile) return alert("Veuillez ajouter votre photo.");

        const oldText = btn.innerHTML;
        btn.disabled = true; 
        btn.innerHTML = "Generating...";

        // UI Loading
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        document.getElementById('post-actions').style.display = 'none';

        try {
            const formData = new FormData();
            formData.append("shop", shop);
            formData.append("person_image", uFile);
            
            // LOGIQUE HYBRIDE :
            // Si on a une URL produit (Mode Client), on l'envoie.
            // Sinon (Mode Admin), on cherche un fichier uploadé.
            if (autoProductImage) {
                let cleanUrl = autoProductImage;
                if(cleanUrl.startsWith('//')) cleanUrl = 'https:' + cleanUrl;
                formData.append("clothing_url", cleanUrl);
            } else {
                const cFile = document.getElementById('cImg').files[0];
                if (cFile) {
                    // En mode admin, on envoie le fichier, le backend devra gérer ça
                    // ASTUCE : Pour garder le backend simple, en mode admin pur
                    // il faudrait idéalement uploader l'image d'abord.
                    // Pour l'instant, disons que ça marche surtout pour le Client.
                    return alert("En mode Admin, veuillez utiliser une URL pour l'instant.");
                } else {
                    return alert("Image vêtement manquante.");
                }
            }

            // Appel API
            const res = await fetch('/api/generate', { 
                method: 'POST', 
                body: formData 
            });

            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.error || "Erreur serveur");
            }

            const data = await res.json();
            
            if(data.result_image_url){
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => { 
                    ri.style.display = 'block'; 
                    document.getElementById('loader').style.display = 'none'; 
                    document.getElementById('post-actions').style.display = 'block'; 
                };
            } else {
                throw new Error("Pas d'URL reçue.");
            }

        } catch(e) { 
            console.error(e); 
            alert("Erreur: " + e.message); 
            document.getElementById('loader').style.display = 'none'; 
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldText; 
        }
    };
});
