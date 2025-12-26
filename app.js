document.addEventListener("DOMContentLoaded", function() {

    // 1. Récupération des paramètres Iframe
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode'); 
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image');

    // Sauvegarde shop
    if (shop) sessionStorage.setItem('shop', shop);

    console.log("VTON Init - Shop:", shop, "| Mode:", mode);

    // 2. Initialisation selon le mode
    if (mode === 'client') {
        initClientMode();
    } else if (shop) {
        initAdminMode(shop);
    }

    // --- MODE CLIENT (WIDGET SITE) ---
    function initClientMode() {
        console.log("Activation Mode Client");
        document.body.classList.add('client-mode');
        
        // Cacher le dashboard admin
        const adminZone = document.getElementById('admin-only-zone');
        if(adminZone) adminZone.style.display = 'none';

        // GESTION IMAGE PRODUIT
        if (autoProductImage) {
            // Cible la boite pour le vêtement (normalement cImg)
            const garmentBox = document.querySelector('label[for="cImg"]');
            
            if (garmentBox) {
                // On l'affiche, mais on bloque le clic (lecture seule)
                garmentBox.style.display = 'flex'; 
                garmentBox.style.pointerEvents = 'none';
                
                const img = document.getElementById('prevC');
                const emptyState = garmentBox.querySelector('.empty-state');
                
                if (img) {
                    // Nettoyage URL si nécessaire
                    let secureUrl = autoProductImage;
                    if(secureUrl.startsWith('//')) secureUrl = 'https:' + secureUrl;
                    
                    img.src = secureUrl;
                    img.style.display = 'block';
                }
                // Masquer l'icône "upload"
                if (emptyState) emptyState.style.display = 'none';
            }
        }
        
        document.body.classList.add('loaded');
        document.body.style.opacity = "1";
    }

    // --- MODE ADMIN (DASHBOARD) ---
    async function initAdminMode(s) {
        // Authenticated fetch helper
        async function authFetch(url) {
             if (window.shopify && window.shopify.id) {
                 const token = await shopify.id.getToken();
                 return fetch(url, { headers: { 'Authorization': `Bearer ${token}` } });
             }
             return fetch(url);
        }

        const res = await authFetch(`/api/get-data?shop=${s}`);
        if (res && res.ok) {
            const data = await res.json();
            updateDashboardStats(data.credits || 0);
            
            if(data.widget) {
                document.getElementById('ws-text').value = data.widget.text || "Try It On Now ✨";
                document.getElementById('ws-color').value = data.widget.bg || "#000000";
                document.getElementById('ws-text-color').value = data.widget.color || "#ffffff";
            }
        }
        document.body.classList.add('loaded');
        document.body.style.opacity = "1";
    }

    function updateDashboardStats(credits) {
        const el = document.getElementById('credits');
        if(el) el.innerText = credits;
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

    window.updateWidgetPreview = function() {
        const text = document.getElementById('ws-text').value;
        const color = document.getElementById('ws-color').value;
        const textColor = document.getElementById('ws-text-color').value;
        const btn = document.getElementById('ws-preview-btn');
        if(btn) {
            btn.style.backgroundColor = color;
            btn.style.color = textColor;
            const span = btn.querySelector('span');
            if(span) span.innerText = text;
        }
    }
    
    // --- TRACKING ATC ---
    window.trackATC = async function() {
        if(shop) {
             fetch('/api/track-atc', { 
                 method: 'POST', 
                 headers: {'Content-Type': 'application/json'}, 
                 body: JSON.stringify({ shop: shop }) 
             });
             const btn = document.getElementById('shopBtn');
             btn.innerHTML = "Redirecting... <i class='fa-solid fa-check'></i>";
        }
    };

    // --- FONCTION GENERATE PRINCIPALE ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const btn = document.getElementById('btnGo');

        if (!shop) return alert("Erreur: Boutique non identifiée.");
        if (!uFile) return alert("Veuillez ajouter votre photo.");
        // Note: En mode client, pas de cFile, mais autoProductImage

        const oldText = btn.innerHTML;
        btn.disabled = true; 
        btn.innerHTML = "Generating...";

        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        document.getElementById('post-actions').style.display = 'none';

        // Animation texte
        const textEl = document.getElementById('loader-text');
        const texts = ["Analyzing silhouette...", "Matching fabrics...", "Simulating drape...", "Rendering lighting..."];
        let step = 0;
        const interval = setInterval(() => { if(step < texts.length) textEl.innerText = texts[step++]; }, 2500);

        try {
            const formData = new FormData();
            formData.append("shop", shop);
            formData.append("person_image", uFile);
            
            // GESTION VETEMENT : URL ou FICHIER
            if (autoProductImage) {
                // Mode Client : on envoie l'URL propre
                let cleanUrl = autoProductImage;
                if(cleanUrl.startsWith('//')) cleanUrl = 'https:' + cleanUrl;
                formData.append("clothing_url", cleanUrl);
            } else {
                // Mode Admin : on envoie le fichier
                const cFile = document.getElementById('cImg').files[0];
                if (cFile) formData.append("clothing_file", cFile);
                else return alert("Veuillez choisir un vêtement.");
            }
            
            formData.append("category", "upper_body");

            // Appel API
            const res = await fetch('/api/generate', { 
                method: 'POST', 
                body: formData 
            });

            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.error || "Server Error");
            }

            const data = await res.json();
            
            clearInterval(interval);
            
            if(data.result_image_url){
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => { 
                    ri.style.display = 'block'; 
                    document.getElementById('loader').style.display = 'none'; 
                    document.getElementById('post-actions').style.display = 'block'; 
                };
            } else {
                throw new Error("No image URL returned");
            }

        } catch(e) { 
            clearInterval(interval); 
            console.error(e); 
            alert("Erreur: " + e.message); 
            document.getElementById('loader').style.display = 'none'; 
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldText; 
        }
    };
    
    // Admin functions binding
    window.saveSettings = async function(btn) { /* ... garder logique existante ... */ };
});
