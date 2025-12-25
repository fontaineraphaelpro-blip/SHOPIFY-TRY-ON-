document.addEventListener("DOMContentLoaded", function() {
    
    // --- 1. CORRECTION PAGE BLANCHE (CRUCIAL) ---
    // On ajoute la classe qui passe l'opacité de 0 à 1
    document.body.classList.add('loaded');
    console.log("App started & Visible");

    // --- 2. FONCTION TOKEN ---
    // Récupère le jeton de session pour authentifier les requêtes vers Python
    async function getSessionToken() {
        if (window.shopify && window.shopify.id) {
            return await shopify.id.getToken();
        }
        return null; // Retourne null si on teste hors de l'iframe Shopify
    }

    // --- 3. INITIALISATION & PARAMÈTRES ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode'); // 'client' ou null
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image'); 
    
    // On sauvegarde le shop pour ne pas le perdre au rechargement
    if(shop) {
        sessionStorage.setItem('shop', shop);
        // Si on est en mode Admin (pas client), on charge les crédits
        if (mode !== 'client') {
            fetchCredits(shop);
        }
    }

    // --- 4. GESTION MODE WIDGET (CLIENT) ---
    if (mode === 'client') {
        document.body.classList.add('client-mode');
        
        // On cache le dashboard admin
        const adminDash = document.getElementById('admin-dashboard');
        if(adminDash) adminDash.style.display = 'none';
        
        // On affiche le titre client
        const title = document.getElementById('client-title');
        if(title) title.style.display = 'block';

        // Si une image produit est passée dans l'URL (depuis le bouton "Essayer"), on l'affiche
        if (autoProductImage) {
            const img = document.getElementById('prevC');
            if(img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                if(img.parentElement) {
                    img.parentElement.classList.add('has-image');
                    // On cache les textes d'upload
                    const els = img.parentElement.querySelectorAll('i, .upload-text, .upload-icon, .upload-sub');
                    els.forEach(el => el.style.display = 'none');
                }
            }
        }
    }

    // --- 5. RÉCUPÉRATION DES CRÉDITS ---
    async function fetchCredits(s) {
        try {
            const token = await getSessionToken();
            const headers = token ? {'Authorization': `Bearer ${token}`} : {};
            
            const res = await fetch(`/api/get-credits?shop=${s}`, { headers });
            
            if (res.status === 401) {
                console.warn("Session expirée (401) lors du chargement des crédits.");
                return; 
            }
            
            const data = await res.json();
            const el = document.getElementById('credits'); 
            if(el) el.innerText = data.credits;
        } catch(e) { 
            console.error("Erreur API Crédits", e); 
        }
    }

    // --- 6. FONCTION DE PRÉVISUALISATION DES IMAGES ---
    // Appelée par le onchange des input file dans le HTML
    window.preview = function(inputId, imgId, txtId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                // Style pour cacher l'icône de fond
                if(img.parentElement) {
                    img.parentElement.classList.add('has-image');
                    const els = img.parentElement.querySelectorAll('i, .upload-text, .upload-icon, .upload-sub');
                    els.forEach(el => el.style.display = 'none');
                }
            };
            reader.readAsDataURL(file);
        }
    };

    // --- 7. FONCTION PRINCIPALE : GÉNÉRER L'ESSAYAGE (IA) ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        // Vérifications
        if (!uFile) return alert("Please upload your photo.");
        if (!autoProductImage && !cFile) return alert("Please select a garment.");

        // UI : Mode Chargement
        btn.disabled = true; 
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
        document.getElementById('resZone').style.display = 'flex';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';

        try {
            const token = await getSessionToken();
            
            // On utilise FormData pour envoyer des fichiers
            const formData = new FormData();
            formData.append("shop", shop || "demo");
            formData.append("person_image", uFile);
            
            if (cFile) {
                formData.append("clothing_file", cFile); 
            } else {
                formData.append("clothing_url", autoProductImage); 
            }
            formData.append("category", "upper_body");

            const headers = {};
            if(token) headers['Authorization'] = `Bearer ${token}`;

            const res = await fetch('/api/generate', {
                method: 'POST',
                headers: headers,
                body: formData
            });

            // Gestion session expirée
            if (res.status === 401) {
                if(shop && mode !== 'client') window.top.location.href = `/login?shop=${shop}`;
                else alert("Session expired. Please refresh.");
                return;
            }

            const data = await res.json();
            
            if(data.result_image_url) {
                // Succès !
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.style.display = 'block';
                document.getElementById('loader').style.display = 'none';
                
                // Si on a reçu le nouveau solde de crédits, on met à jour
                if(data.new_credits !== undefined) {
                    const cel = document.getElementById('credits');
                    if(cel) cel.innerText = data.new_credits;
                }
            } else {
                // Erreur IA (crédits insuffisants ou autre)
                alert("AI Error: " + (data.error || "Unknown error"));
                document.getElementById('resZone').style.display = 'none';
            }
        } catch(e) { 
            console.error(e);
            alert("Connection Error: " + e); 
            document.getElementById('resZone').style.display = 'none';
        } finally { 
            // On remet le bouton normal quoi qu'il arrive
            btn.disabled = false; 
            btn.innerHTML = 'Test This Outfit Now <i class="fa-solid fa-wand-magic-sparkles"></i>'; 
        }
    };

    // --- 8. FONCTION ACHAT (BUY) ---
    window.buy = async function(packId, customAmount = 0) {
        if(!shop) return alert("Shop ID missing. Please reload.");
        
        // Gestion UI du bouton cliqué
        let btn;
        if(event && event.target) {
            btn = event.target.tagName === 'BUTTON' ? event.target : event.target.closest('button');
        }
        if (!btn && packId === 'pack_custom') btn = document.querySelector('.custom-input-group button');
        
        const oldText = btn ? btn.innerText : "...";
        if(btn) { btn.innerText = "Wait..."; btn.disabled = true; }

        try {
            const token = await getSessionToken();
            const headers = {'Content-Type': 'application/json'};
            if(token) headers['Authorization'] = `Bearer ${token}`;

            const body = { shop: shop, pack_id: packId };
            if(customAmount > 0) body.custom_amount = customAmount;

            const res = await fetch('/api/buy-credits', {
                method: 'POST', 
                headers: headers, 
                body: JSON.stringify(body)
            });

            if (res.status === 401) {
                console.log("Session perdue, redirection login...");
                window.top.location.href = `/login?shop=${shop}`;
                return;
            }

            const data = await res.json();
            
            if(data.confirmation_url) {
                // Redirection vers la page de paiement Shopify
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Error: " + (data.error || "Unknown"));
                if(btn) { btn.innerText = oldText; btn.disabled = false; }
            }
        } catch(e) {
            console.error(e);
            alert("Network Error");
            if(btn) { btn.innerText = oldText; btn.disabled = false; }
        }
    };

    // Fonction intermédiaire pour le champ input custom
    window.buyCustom = function() {
        const amount = document.getElementById('customAmount').value;
        if(amount < 200) return alert("Min 200 credits");
        window.buy('pack_custom', parseInt(amount));
    }

}); // Fin du DOMContentLoaded
