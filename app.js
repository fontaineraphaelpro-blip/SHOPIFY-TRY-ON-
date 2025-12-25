document.addEventListener("DOMContentLoaded", function() {
    
    // --- 1. UI INIT ---
    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    // --- 2. TOKEN HELPER (Avec attente de App Bridge) ---
    async function getSessionToken() {
        // On attend jusqu'à 2 secondes que window.shopify soit prêt
        let retries = 10;
        while (retries > 0) {
            if (window.shopify && window.shopify.id) {
                return await shopify.id.getToken();
            }
            await new Promise(r => setTimeout(r, 200)); // Attendre 200ms
            retries--;
        }
        console.warn("⚠️ App Bridge non détecté après attente.");
        return null;
    }

    // --- 3. CONFIG & INITIALISATION ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image');

    // Sauvegarde du shop pour ne pas le perdre
    if(shop) sessionStorage.setItem('shop', shop);

    // Initialisation selon le mode
    if (mode === 'client') {
        initClientMode();
    } else {
        // Mode Admin : On charge les crédits
        if(shop) fetchCredits(shop);
    }

    // --- 4. FONCTIONS DE RÉPARATION DE SESSION ---
    function handleSessionExpired() {
        console.log("🔄 Session expirée (Server Reset). Reconnexion auto...");
        // On redirige immédiatement pour régénérer le token en RAM
        if (shop) {
            window.top.location.href = `/login?shop=${shop}`;
        } else {
            alert("Erreur de session. Veuillez recharger l'application depuis Shopify.");
        }
    }

    // --- 5. FETCH CREDITS (Modifié pour auto-réparation) ---
    async function fetchCredits(s) {
        try {
            const token = await getSessionToken();
            const headers = token ? {'Authorization': `Bearer ${token}`} : {};
            
            const res = await fetch(`/api/get-credits?shop=${s}`, { headers });
            
            // SI ERREUR 401 AU CHARGEMENT -> ON RÉPARE TOUT DE SUITE
            if (res.status === 401) {
                handleSessionExpired();
                return;
            }
            
            const data = await res.json();
            const el = document.getElementById('credits');
            if(el) el.innerText = data.credits;

        } catch(e) { 
            console.error("Err Credits", e); 
        }
    }

    // --- 6. MODE WIDGET (Client) ---
    function initClientMode() {
        document.body.classList.add('client-mode');
        const adminDash = document.getElementById('admin-dashboard');
        if(adminDash) adminDash.style.display = 'none';
        
        // Cache la section facturation en mode client
        const billing = document.getElementById('billing-section');
        if(billing) billing.style.display = 'none';

        const title = document.getElementById('client-title');
        if(title) title.style.display = 'block';

        if (autoProductImage) {
            const img = document.getElementById('prevC');
            if(img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                if(img.parentElement) img.parentElement.querySelector('.upload-content').style.display = 'none';
            }
        }
    }

    // --- 7. PREVIEW ---
    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                const content = img.parentElement.querySelector('.upload-content');
                if(content) content.style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    };

    // --- 8. GENERATE (IA) ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        if (!uFile) return alert("Photo manquante.");
        if (!autoProductImage && !cFile) return alert("Vêtement manquant.");

        btn.disabled = true; 
        const oldText = btn.innerHTML;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Traitement...';
        
        document.getElementById('resZone').style.display = 'block';
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
                handleSessionExpired();
                return;
            }
            if (res.status === 402) {
                alert("Crédits insuffisants !");
                btn.disabled = false; btn.innerHTML = oldText;
                return;
            }

            const data = await res.json();
            
            if(data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => {
                    ri.style.display = 'block';
                    document.getElementById('loader').style.display = 'none';
                };
                if(data.new_credits !== undefined) {
                    const cel = document.getElementById('credits');
                    if(cel) cel.innerText = data.new_credits;
                }
            } else {
                alert("Erreur IA: " + (data.error || "Inconnue"));
                document.getElementById('loader').style.display = 'none';
            }
        } catch(e) { 
            console.error(e);
            alert("Erreur réseau"); 
            document.getElementById('loader').style.display = 'none';
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldText; 
        }
    };

    // --- 9. BUY (Achat Crédits) ---
    window.buy = async function(packId, customAmount = 0, btnElement = null) {
        if(!shop) return alert("Erreur Shop ID. Rechargez la page.");
        
        const btn = btnElement;
        const oldText = btn ? btn.innerText : "...";
        if(btn) { btn.innerText = "Wait..."; btn.disabled = true; }

        try {
            const token = await getSessionToken();
            const headers = {'Content-Type': 'application/json'};
            if(token) headers['Authorization'] = `Bearer ${token}`;

            const body = { shop: shop, pack_id: packId, custom_amount: customAmount };

            const res = await fetch('/api/buy-credits', {
                method: 'POST', headers: headers, body: JSON.stringify(body)
            });

            if (res.status === 401) {
                handleSessionExpired();
                return;
            }

            const data = await res.json();
            if(data.confirmation_url) {
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Erreur: " + (data.error || "Inconnue"));
                if(btn) { btn.innerText = oldText; btn.disabled = false; }
            }
        } catch(e) {
            console.error(e);
            alert("Erreur réseau");
            if(btn) { btn.innerText = oldText; btn.disabled = false; }
        }
    };

    window.buyCustom = function(btnElement) {
        const amount = document.getElementById('customAmount').value;
        if(amount < 200) return alert("Min 200 credits");
        window.buy('pack_custom', parseInt(amount), btnElement);
    }
});
