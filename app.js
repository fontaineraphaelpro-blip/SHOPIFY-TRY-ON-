document.addEventListener("DOMContentLoaded", function() {

    // 1. DÉTECTION INTELLIGENTE (Mode Client ou Admin ?)
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode'); // sera 'client' depuis le widget
    
    // Astuce : En mode client, le shop est TOUJOURS dans l'URL.
    // En admin, il peut être dans le storage.
    const shop = params.get('shop') || (window.shopify ? null : sessionStorage.getItem('shop'));
    const autoProductImage = params.get('product_image');

    // On affiche l'app (évite le flash blanc)
    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    // 2. LOGIQUE D'INTERFACE UNIFIÉE
    if (mode === 'client') {
        // --- MODE VISITEUR (WIDGET) ---
        console.log("👋 Mode Client détecté");
        document.body.classList.add('client-mode');
        
        // ON CACHE TOUTE L'ADMINISTRATION (Dashboard, Paiement, Settings)
        const adminZone = document.getElementById('admin-only-zone');
        if(adminZone) adminZone.style.display = 'none';
        
        // On pré-remplit l'image du produit si elle existe
        if (autoProductImage) {
            const img = document.getElementById('prevC');
            if(img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                // Cache l'icône vide
                const emptyState = img.parentElement.querySelector('.empty-state');
                if(emptyState) emptyState.style.display = 'none';
            }
        }
    } else {
        // --- MODE ADMIN (PROPRIÉTAIRE) ---
        console.log("👑 Mode Admin détecté");
        if(shop) initAdminMode(shop);
    }

    // --- FONCTIONS ---

    // Prévisualisation simple des images
    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if(file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                const emptyState = img.parentElement.querySelector('.empty-state');
                if(emptyState) emptyState.style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    };

    // LA FONCTION GÉNÉRATION (Compatible Firefox/Chrome/Safari)
    window.generate = async function() {
        // On relit les paramètres au moment du clic pour être sûr
        const currentParams = new URLSearchParams(window.location.search);
        const currentShop = currentParams.get('shop') || shop;
        const currentMode = currentParams.get('mode');

        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');

        // Sécurités
        if (!currentShop) return alert("Erreur technique : Boutique non identifiée. Rechargez la page.");
        if (!uFile) return alert("Veuillez ajouter votre photo (Étape 1).");
        if (!autoProductImage && !cFile) return alert("Veuillez ajouter un vêtement (Étape 2).");

        // Animation de chargement
        const oldText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = "Création du look... <i class='fa-solid fa-spinner fa-spin'></i>";
        
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        
        // Petit texte d'attente sympa
        const textEl = document.getElementById('loader-text');
        if(textEl) textEl.innerText = "Analyse de la silhouette...";

        try {
            const formData = new FormData();
            formData.append("shop", currentShop);
            formData.append("person_image", uFile);
            formData.append("category", "upper_body");

            // Gestion intelligente URL vs Fichier
            if (autoProductImage) {
                formData.append("clothing_url", autoProductImage);
            } else {
                formData.append("clothing_file", cFile);
            }

            let res;
            
            // --- C'EST ICI QUE LA MAGIE OPÈRE ---
            if (currentMode === 'client') {
                // Pour le client (Firefox friendly) : Fetch standard
                // Pas de headers bizarres, pas de session storage -> Ça passe partout !
                res = await fetch('/api/generate', {
                    method: 'POST',
                    body: formData
                });
            } else {
                // Pour l'admin : Fetch authentifié Shopify
                res = await authenticatedFetch('/api/generate', { 
                    method: 'POST', 
                    body: formData 
                });
            }

            if (!res.ok) {
                const errTxt = await res.text();
                // Gestion des erreurs spécifiques
                if (res.status === 429) throw new Error("Limite journalière atteinte pour cette boutique.");
                if (res.status === 402) throw new Error("La boutique n'a plus de crédits.");
                throw new Error("Erreur serveur: " + errTxt);
            }

            const data = await res.json();
            
            if(data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => {
                    document.getElementById('loader').style.display = 'none';
                    ri.style.display = 'block';
                    // Scroll vers le résultat
                    ri.scrollIntoView({behavior: "smooth", block: "center"});
                };
            } else {
                throw new Error("L'IA n'a pas renvoyé d'image.");
            }

        } catch (e) {
            console.error(e);
            alert("Oups ! " + e.message);
            document.getElementById('loader').style.display = 'none';
        } finally {
            btn.disabled = false;
            btn.innerHTML = oldText;
        }
    };

    // --- FONCTIONS ADMIN (Ne s'exécutent pas chez le client) ---
    
    async function getSessionToken() {
        if (window.shopify && window.shopify.id) return await shopify.id.getToken();
        return null;
    }

    async function authenticatedFetch(url, options = {}) {
        try {
            const token = await getSessionToken();
            const headers = options.headers || {};
            if (token) headers['Authorization'] = `Bearer ${token}`;
            return fetch(url, { ...options, headers });
        } catch(e) { throw e; }
    }

    async function initAdminMode(s) {
        try {
            // Récupération des stats dashboard
            const res = await authenticatedFetch(`/api/get-data?shop=${s}`);
            if(res.ok) {
                const data = await res.json();
                if(document.getElementById('credits')) document.getElementById('credits').innerText = data.credits;
                if(document.getElementById('stat-tryons')) document.getElementById('stat-tryons').innerText = data.usage;
                // ... on pourrait ajouter ici le reste des stats ...
            }
        } catch(e) { console.log("Admin init skipped or failed"); }
    }
    
    // Fonction d'achat (Admin uniquement)
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
            if (data.confirmation_url) window.top.location.href = data.confirmation_url; 
            else alert("Erreur paiement");
        } catch (e) { alert("Erreur réseau"); }
        finally { btn.disabled = false; btn.innerHTML = oldText; }
    };
    
    window.buyCustom = function(btn) {
        const val = document.getElementById('customAmount').value;
        window.buy('pack_custom', val, btn);
    };
});
