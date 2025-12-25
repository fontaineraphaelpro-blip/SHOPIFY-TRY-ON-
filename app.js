document.addEventListener("DOMContentLoaded", function() {
    
    // --- 1. APPARITION EN DOUCEUR ---
    document.body.classList.add('loaded');
    document.body.style.opacity = "1"; // Force l'opacité si la classe CSS manque
    console.log("🚀 App started & Visible");

    // --- 2. FONCTION TOKEN (App Bridge 3) ---
    async function getSessionToken() {
        if (window.shopify && window.shopify.id) {
            return await shopify.id.getToken();
        } else {
            console.warn("⚠️ App Bridge non détecté. Assurez-vous d'être dans Shopify Admin.");
            return null; 
        }
    }

    // --- 3. INITIALISATION ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode'); 
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image'); 
    
    if(shop) {
        sessionStorage.setItem('shop', shop);
        // On charge les crédits SEULEMENT si on n'est pas en mode client (widget)
        if (mode !== 'client') {
            fetchCredits(shop);
        } else {
            // En mode client, on cache la section facturation
            const billingSec = document.getElementById('billing-section');
            if(billingSec) billingSec.style.display = 'none';
        }
    }

    // --- 4. MODE WIDGET (CLIENT) ---
    if (mode === 'client') {
        document.body.classList.add('client-mode');
        
        const adminDash = document.getElementById('admin-dashboard');
        if(adminDash) adminDash.style.display = 'none';
        
        const title = document.getElementById('client-title');
        if(title) title.style.display = 'block';

        if (autoProductImage) {
            const img = document.getElementById('prevC');
            if(img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                if(img.parentElement) {
                    img.parentElement.classList.add('has-image');
                    const els = img.parentElement.querySelectorAll('i, .upload-text, .upload-content');
                    els.forEach(el => el.style.display = 'none');
                }
            }
        }
    }

    // --- 5. FETCH CRÉDITS ---
    async function fetchCredits(s) {
        try {
            const token = await getSessionToken();
            // Important : Toujours avoir des headers valides
            const headers = token ? {'Authorization': `Bearer ${token}`} : {};
            
            const res = await fetch(`/api/get-credits?shop=${s}`, { headers });
            
            if (res.status === 401) {
                console.warn("Session expirée (401).");
                return; 
            }
            
            const data = await res.json();
            const el = document.getElementById('credits'); 
            if(el) el.innerText = data.credits;
        } catch(e) { 
            console.error("Erreur API Crédits", e); 
        }
    }

    // --- 6. PREVIEW IMAGE ---
    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                // Cache les textes d'upload
                const contentDiv = img.parentElement.querySelector('.upload-content');
                if(contentDiv) contentDiv.style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    };

    // --- 7. GÉNÉRATION IA ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        if (!uFile) return alert("Veuillez ajouter votre photo.");
        if (!autoProductImage && !cFile) return alert("Veuillez ajouter un vêtement.");

        // UI Loading
        btn.disabled = true; 
        const oldBtnText = btn.innerHTML;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Traitement...';
        
        document.getElementById('resZone').style.display = 'block'; // Block au lieu de flex pour eviter layout bizarre
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';

        try {
            const token = await getSessionToken();
            const formData = new FormData();
            formData.append("shop", shop || "demo");
            formData.append("person_image", uFile);
            
            if (cFile) formData.append("clothing_file", cFile); 
            else formData.append("clothing_url", autoProductImage); 
            
            formData.append("category", "upper_body");

            const headers = {};
            if(token) headers['Authorization'] = `Bearer ${token}`;

            const res = await fetch('/api/generate', {
                method: 'POST',
                headers: headers,
                body: formData
            });

            if (res.status === 401) {
                alert("Session expirée. Veuillez rafraîchir la page.");
                return;
            }
            if (res.status === 402) {
                alert("Crédits insuffisants !");
                return;
            }

            const data = await res.json();
            
            if(data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                
                // On attend que l'image charge pour cacher le loader
                ri.onload = () => {
                    ri.style.display = 'block';
                    document.getElementById('loader').style.display = 'none';
                };
                
                if(data.new_credits !== undefined) {
                    const cel = document.getElementById('credits');
                    if(cel) cel.innerText = data.new_credits;
                }
            } else {
                alert("Erreur IA : " + (data.error || "Erreur inconnue"));
                document.getElementById('loader').style.display = 'none';
            }
        } catch(e) { 
            console.error(e);
            alert("Erreur de connexion : " + e); 
            document.getElementById('loader').style.display = 'none';
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldBtnText; 
        }
    };

    // --- 8. FONCTION ACHAT (Corrigée) ---
    // On ajoute un 3ème argument 'btnElement' pour éviter l'erreur 'event'
    window.buy = async function(packId, customAmount = 0, btnElement = null) {
        if(!shop) return alert("Shop ID introuvable. Rechargez la page.");
        
        const btn = btnElement;
        const oldText = btn ? btn.innerText : "...";
        
        if(btn) { 
            btn.innerText = "Patientez..."; 
            btn.disabled = true; 
        }

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
                // Redirection login
                window.top.location.href = `/login?shop=${shop}`;
                return;
            }

            const data = await res.json();
            
            if(data.confirmation_url) {
                // Redirection paiement Shopify (Sortir de l'iframe)
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Erreur : " + (data.error || "Inconnue"));
                if(btn) { btn.innerText = oldText; btn.disabled = false; }
            }
        } catch(e) {
            console.error(e);
            alert("Erreur Réseau");
            if(btn) { btn.innerText = oldText; btn.disabled = false; }
        }
    };

    // Wrapper pour le bouton custom qui passe 'this' correctement
    window.buyCustom = function(btnElement) {
        const amount = document.getElementById('customAmount').value;
        if(amount < 200) return alert("Minimum 200 crédits");
        window.buy('pack_custom', parseInt(amount), btnElement);
    }

});
