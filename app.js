document.addEventListener("DOMContentLoaded", function() {

    // --- 1. DÉTECTION INTELLIGENTE DU MODE ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode'); // 'client' (Widget) ou null (Admin)
    
    // En mode client, le shop est TOUJOURS dans l'URL (envoyé par le widget).
    // En admin, on le récupère via l'URL ou on le laisse gérer par Shopify App Bridge.
    const shop = params.get('shop'); 
    const autoProductImage = params.get('product_image');

    // On affiche l'interface proprement
    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    // --- 2. CONFIGURATION DE L'INTERFACE ---
    if (mode === 'client') {
        // === MODE CLIENT (VISITEUR) ===
        console.log("👋 Mode Client activé");
        document.body.classList.add('client-mode');

        // On CACHE toute la partie administration (Dashboard, Achat, Settings)
        const adminZone = document.getElementById('admin-only-zone');
        if (adminZone) adminZone.style.display = 'none';

        // Si une image produit est fournie, on la pré-charge
        if (autoProductImage) {
            const img = document.getElementById('prevC');
            if (img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                // Masquer l'icône vide
                const emptyState = img.parentElement.querySelector('.empty-state');
                if (emptyState) emptyState.style.display = 'none';
            }
        }
    } else {
        // === MODE ADMIN (PROPRIÉTAIRE) ===
        console.log("👑 Mode Admin activé");
        // On charge les stats du dashboard
        if (shop) initAdminMode(shop);
    }

    // --- 3. FONCTIONS UTILITAIRES ---

    // Prévisualisation image (Upload local)
    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                const emptyState = img.parentElement.querySelector('.empty-state');
                if (emptyState) emptyState.style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    };

    // --- 4. LA FONCTION GENERATE (CŒUR DU SYSTÈME) ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        // Sécurités basiques
        if (!shop) return alert("Erreur: Boutique non identifiée. Veuillez recharger la page.");
        if (!uFile) return alert("Veuillez ajouter votre photo (Étape 1).");
        if (!autoProductImage && !cFile) return alert("Veuillez ajouter un vêtement (Étape 2).");

        // UI Loading
        const oldText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = "Création du look... <i class='fa-solid fa-spinner fa-spin'></i>";
        
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        
        // Texte d'ambiance
        const textEl = document.getElementById('loader-text');
        if(textEl) textEl.innerText = "Analyse de la silhouette...";

        try {
            const formData = new FormData();
            formData.append("shop", shop);
            formData.append("person_image", uFile);
            
            // Gestion intelligente URL vs Fichier
            if (autoProductImage) {
                formData.append("clothing_url", autoProductImage);
            } else {
                formData.append("clothing_file", cFile);
            }

            let res;

            // === BIFURCATION CRITIQUE ===
            if (mode === 'client') {
                // CAS 1 : CLIENT (Widget)
                // On utilise un FETCH STANDARD. 
                // Le serveur utilisera le token stocké en base de données.
                // Cela contourne les problèmes de cookies tiers sur Firefox/Safari.
                console.log("🚀 Envoi requête mode PUBLIC");
                res = await fetch('/api/generate', {
                    method: 'POST',
                    body: formData
                });
            } else {
                // CAS 2 : ADMIN (Dashboard)
                // On utilise FETCH AUTHENTIFIÉ (App Bridge)
                // Pour garantir que c'est bien l'admin qui teste.
                console.log("🛡️ Envoi requête mode ADMIN");
                res = await authenticatedFetch('/api/generate', {
                    method: 'POST',
                    body: formData
                });
            }

            // Gestion des erreurs HTTP
            if (!res.ok) {
                const errTxt = await res.text();
                if (res.status === 403) throw new Error("L'application n'est pas installée correctement côté Admin.");
                if (res.status === 402) throw new Error("La boutique n'a plus de crédits.");
                if (res.status === 429) throw new Error("Limite journalière atteinte.");
                throw new Error("Erreur serveur : " + errTxt);
            }

            const data = await res.json();
            
            if (data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => {
                    document.getElementById('loader').style.display = 'none';
                    ri.style.display = 'block';
                    ri.scrollIntoView({behavior: "smooth", block: "center"});
                };
            } else {
                throw new Error("Aucune image reçue de l'IA.");
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

    // --- 5. FONCTIONS ADMIN UNIQUEMENT ---
    // Ces fonctions ne sont utilisées que si on est dans le Dashboard Shopify

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
        } catch (e) { throw e; }
    }

    async function initAdminMode(s) {
        try {
            // Récupère les crédits pour l'affichage admin
            const res = await authenticatedFetch(`/api/get-data?shop=${s}`);
            if (res.ok) {
                const data = await res.json();
                if(document.getElementById('credits')) document.getElementById('credits').innerText = data.credits;
                if(document.getElementById('stat-tryons')) document.getElementById('stat-tryons').innerText = data.usage;
            }
        } catch (e) { console.log("Init Admin Error", e); }
    }
    
    // Fonction d'achat de crédits
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
            else alert("Erreur lors de la création du paiement.");
        } catch (e) { alert("Erreur réseau ou paiement annulé."); }
        finally { btn.disabled = false; btn.innerHTML = oldText; }
    };
    
    window.buyCustom = function(btn) {
        const val = document.getElementById('customAmount').value;
        window.buy('pack_custom', val, btn);
    };

});
