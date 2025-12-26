document.addEventListener("DOMContentLoaded", function() {

    // --- 1. CONFIGURATION ET DÉTECTION ---
    const params = new URLSearchParams(window.location.search);
    
    // Le mode 'client' est activé par le widget
    const mode = params.get('mode'); 
    
    // Le shop est TOUJOURS dans l'URL (envoyé par Shopify ou le widget)
    const shop = params.get('shop'); 
    const autoProductImage = params.get('product_image');

    // On affiche l'app (Transition fluide CSS)
    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    // --- 2. GESTION DES MODES (CLIENT vs ADMIN) ---
    if (mode === 'client') {
        // === MODE VISITEUR (WIDGET) ===
        console.log("👋 Mode Client (Widget) détecté pour :", shop);
        document.body.classList.add('client-mode');

        // CACHER L'ADMIN : On supprime physiquement la zone admin pour éviter les erreurs
        const adminZone = document.getElementById('admin-only-zone');
        if (adminZone) adminZone.style.display = 'none';

        // PRÉ-CHARGEMENT IMAGE : Si le widget envoie une image produit
        if (autoProductImage) {
            const img = document.getElementById('prevC');
            if (img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                // Cacher l'icône "vide"
                const emptyState = img.parentElement.querySelector('.empty-state');
                if (emptyState) emptyState.style.display = 'none';
            }
        }
    } else {
        // === MODE ADMIN (DASHBOARD) ===
        console.log("👑 Mode Admin détecté");
        if (shop) initAdminMode(shop);
        else console.warn("⚠️ Shop non détecté dans l'URL Admin");
    }

    // --- 3. FONCTIONS D'INTERFACE ---

    // Prévisualisation des images uploadées (Step 1 & 2)
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

    // --- 4. LA FONCTION CŒUR : GENERATE() ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        // Sécurités
        if (!shop) return alert("Erreur technique : Boutique inconnue. Rechargez la page.");
        if (!uFile) return alert("Veuillez ajouter votre photo (Étape 1).");
        if (!autoProductImage && !cFile) return alert("Veuillez ajouter un vêtement (Étape 2).");

        // UI Loading
        const oldText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = "Création du look... <i class='fa-solid fa-spinner fa-spin'></i>";
        
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        
        // Animation texte d'attente
        const textEl = document.getElementById('loader-text');
        const steps = ["Analyse de la silhouette...", "Ajustement du vêtement...", "Rendu haute qualité..."];
        let stepIdx = 0;
        if(textEl) {
            textEl.innerText = steps[0];
            var stepInterval = setInterval(() => {
                stepIdx = (stepIdx + 1) % steps.length;
                textEl.innerText = steps[stepIdx];
            }, 3000);
        }

        try {
            const formData = new FormData();
            formData.append("shop", shop);
            formData.append("person_image", uFile);
            
            // Logique : URL (Widget) ou Fichier (Admin/Upload)
            if (autoProductImage) {
                formData.append("clothing_url", autoProductImage);
            } else {
                formData.append("clothing_file", cFile);
            }

            let res;

            // === BIFURCATION CRITIQUE (CLIENT vs ADMIN) ===
            if (mode === 'client') {
                // CLIENT : Fetch standard (Pas de Token Session).
                // Le backend vérifiera le token dans la Base de Données PostgreSQL.
                // C'est ce qui permet de marcher sur tous les navigateurs.
                console.log("🚀 Envoi requête PUBLIQUE (Widget)");
                res = await fetch('/api/generate', {
                    method: 'POST',
                    body: formData
                });
            } else {
                // ADMIN : Fetch Authentifié (App Bridge).
                // Nécessaire pour garantir que c'est bien le propriétaire qui est là.
                console.log("🛡️ Envoi requête ADMIN (Secure)");
                res = await authenticatedFetch('/api/generate', {
                    method: 'POST',
                    body: formData
                });
            }

            if(stepInterval) clearInterval(stepInterval);

            // GESTION DES ERREURS SERVEUR
            if (!res.ok) {
                const errTxt = await res.text();
                let errMsg = "Erreur inconnue";
                try {
                    const errJson = JSON.parse(errTxt);
                    errMsg = errJson.error;
                } catch(e) { errMsg = errTxt; }

                if (res.status === 403) throw new Error("Accès refusé. L'application doit être ouverte une fois par l'admin.");
                if (res.status === 402) throw new Error("La boutique n'a plus de crédits.");
                if (res.status === 429) throw new Error("Limite journalière atteinte.");
                
                throw new Error("Erreur Serveur : " + errMsg);
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
                throw new Error("Aucune image reçue.");
            }

        } catch (e) {
            console.error(e);
            if(stepInterval) clearInterval(stepInterval);
            alert("Oups ! " + e.message);
            document.getElementById('loader').style.display = 'none';
        } finally {
            btn.disabled = false;
            btn.innerHTML = oldText;
        }
    };

    // --- 5. FONCTIONS ADMIN UNIQUEMENT (App Bridge) ---

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
            // Récupérer les stats et crédits depuis la DB
            const res = await authenticatedFetch(`/api/get-data?shop=${s}`);
            if (res.ok) {
                const data = await res.json();
                
                // Mettre à jour l'UI Dashboard
                if(document.getElementById('credits')) document.getElementById('credits').innerText = data.credits;
                if(document.getElementById('stat-tryons')) document.getElementById('stat-tryons').innerText = data.usage;
                
                // Gestion de la barre de stock (Visuel)
                const supplyCard = document.querySelector('.smart-supply-card');
                if (supplyCard && data.credits < 10) {
                    supplyCard.style.background = "#fff0f0"; // Rouge si bas
                }
            }
        } catch (e) { console.log("Init Admin Error", e); }
    }
    
    // Fonction d'achat (Settings & Billing)
    window.saveSettings = async function(btn) {
        // Logique de sauvegarde (Metafields)
        const oldText = btn.innerText;
        btn.innerText = "Saving..."; btn.disabled = true;
        const settings = {
            shop: shop,
            text: document.getElementById('ws-text').value,
            bg: document.getElementById('ws-color').value,
            color: document.getElementById('ws-text-color').value,
            max_tries: parseInt(document.getElementById('ws-limit').value) || 5
        };
        try {
            const res = await authenticatedFetch('/api/save-settings', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(settings)
            });
            if(res.ok) { btn.innerText = "Saved! ✅"; setTimeout(() => btn.innerText = oldText, 2000); } 
            else { alert("Erreur sauvegarde"); btn.innerText = oldText; }
        } catch(e) { btn.innerText = oldText; }
        finally { btn.disabled = false; }
    };

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
                // Redirection hors de l'iframe pour le paiement Shopify
                window.top.location.href = data.confirmation_url; 
            } else {
                alert("Erreur création paiement: " + (data.error || "Inconnue"));
            }
        } catch (e) { alert("Erreur réseau"); }
        finally { btn.disabled = false; btn.innerHTML = oldText; }
    };
    
    window.buyCustom = function(btn) {
        const val = document.getElementById('customAmount').value;
        window.buy('pack_custom', val, btn);
    };

});
