document.addEventListener("DOMContentLoaded", function() {

    // --- 1. RÉCUPÉRATION DES PARAMÈTRES ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode'); 
    const shop = params.get('shop'); 
    const autoProductImage = params.get('product_image');

    console.log("🚀 App démarrée. Mode:", mode, "| Shop:", shop);

    // --- 2. GESTION DE L'AFFICHAGE (Client vs Admin) ---
    if (mode === 'client') {
        // MODE WIDGET
        document.body.classList.add('client-mode');
        
        // On cache l'admin, on montre le client
        const adminZone = document.getElementById('admin-only-zone');
        const clientZone = document.getElementById('client-only-wrapper');
        
        if (adminZone) adminZone.style.display = 'none';
        if (clientZone) clientZone.style.display = 'block'; // Ou 'flex' selon ton CSS

        // Pré-remplissage de l'image vêtement (envoyée par le widget Shopify)
        if (autoProductImage) {
            const img = document.getElementById('prevC');
            if (img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                // Cacher l'état vide s'il existe
                const emptyState = img.parentElement.querySelector('.empty-state');
                if (emptyState) emptyState.style.display = 'none';
            }
        }
    } else {
        // MODE DASHBOARD (ADMIN)
        console.log("👑 Mode Admin activé");
        if (shop) initAdminMode(shop);
    }

    // --- 3. FONCTIONS GLOBALES (Pour les onclick="..." du HTML) ---

    // Prévisualisation des images uploadées
    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                const empty = img.parentElement.querySelector('.empty-state');
                if(empty) empty.style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    };

    // ACTION PRINCIPALE : GÉNÉRER L'IMAGE
    window.generate = async function() {
        console.log("⚡ Bouton cliqué !");

        // Récupération des éléments
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0]; // Peut être null si on a autoProductImage
        const btn = document.getElementById('btnGo');
        
        // Vérifications de base
        if (!shop) return alert("Erreur technique : Boutique non identifiée (paramètre 'shop' manquant).");
        if (!uFile) return alert("Veuillez ajouter votre photo (Case 1).");
        if (!autoProductImage && !cFile) return alert("Veuillez ajouter un vêtement (Case 2).");

        // UI : Chargement
        const oldText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = "Création en cours... <i class='fa-solid fa-spinner fa-spin'></i>";
        
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        
        try {
            // Préparation des données
            const formData = new FormData();
            formData.append("shop", shop);
            formData.append("person_image", uFile);
            
            if (autoProductImage) {
                formData.append("clothing_url", autoProductImage);
            } else if (cFile) {
                formData.append("clothing_file", cFile);
            }

            // Choix de la méthode d'envoi (Public vs Admin)
            let res;
            if (mode === 'client') {
                // Fetch standard pour le widget
                res = await fetch('/api/generate', { method: 'POST', body: formData });
            } else {
                // Fetch authentifié pour l'admin (si tu testes depuis le dashboard)
                res = await authenticatedFetch('/api/generate', { method: 'POST', body: formData });
            }

            // Gestion des erreurs HTTP
            if (!res.ok) {
                const errTxt = await res.text();
                let errMsg = "Erreur serveur";
                try { errMsg = JSON.parse(errTxt).error; } catch(e) { errMsg = errTxt; }
                throw new Error(errMsg);
            }

            // Traitement du résultat
            const data = await res.json();
            
            if (data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                
                ri.onload = () => {
                    document.getElementById('loader').style.display = 'none';
                    ri.style.display = 'block';
                    ri.scrollIntoView({behavior: "smooth", block: "center"});
                };
                ri.onerror = () => {
                    throw new Error("L'image générée est illisible.");
                };
            } else {
                throw new Error("L'IA n'a pas renvoyé d'image.");
            }

        } catch (e) {
            console.error("ERREUR:", e);
            alert("Oups ! " + e.message);
            document.getElementById('loader').style.display = 'none';
            document.getElementById('resZone').style.display = 'none';
        } finally {
            // Rétablir le bouton
            btn.disabled = false;
            btn.innerHTML = oldText;
        }
    };

    // --- 4. LOGIQUE ADMIN (Authentification & Crédits) ---

    // Récupérer le token de session Shopify (App Bridge)
    async function getSessionToken() {
        if (window.shopify && window.shopify.id) {
            return await shopify.id.getToken();
        }
        return null;
    }

    // Fetch avec Header d'autorisation
    async function authenticatedFetch(url, options = {}) {
        try {
            const token = await getSessionToken();
            const headers = options.headers || {};
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            return fetch(url, { ...options, headers });
        } catch (e) {
            console.error("Auth Fetch Error:", e);
            throw e;
        }
    }

    // Initialisation Dashboard Admin
    async function initAdminMode(s) {
        try {
            const res = await authenticatedFetch(`/api/get-data?shop=${s}`);
            
            // Auto-Redirect si session expirée (401)
            if (res.status === 401) {
                console.warn("Session expirée, redirection vers login...");
                if (window.top) window.top.location.href = `/login?shop=${s}`;
                else window.location.href = `/login?shop=${s}`;
                return;
            }

            if (res.ok) {
                const data = await res.json();
                if(document.getElementById('credits')) document.getElementById('credits').innerText = data.credits;
                if(document.getElementById('stat-tryons')) document.getElementById('stat-tryons').innerText = data.usage;
            }
        } catch (e) { console.log("Init Admin Failed", e); }
    }
    
    // Fonction d'achat (Appelée par onclick dans le HTML Admin)
    window.buy = async function(packId, amount, btn) {
        const oldText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = 'Patientez...';
        try {
            const res = await authenticatedFetch('/api/buy-credits', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ shop: shop, pack_id: packId, custom_amount: parseInt(amount) })
            });
            const data = await res.json();
            if (data.confirmation_url) {
                // Redirection parent pour sortir de l'iframe et payer
                window.top.location.href = data.confirmation_url; 
            } else {
                alert("Erreur lors de la création du paiement.");
            }
        } catch (e) { 
            alert("Erreur réseau : " + e.message); 
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldText; 
        }
    };
    
    // Achat personnalisé
    window.buyCustom = function(btn) {
        const val = document.getElementById('customAmount').value;
        if(val) window.buy('pack_custom', val, btn);
    };
});
