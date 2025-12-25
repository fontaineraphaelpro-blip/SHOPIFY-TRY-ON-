document.addEventListener("DOMContentLoaded", function() {
    console.log("App started...");

    // --- 1. FONCTION TOKEN ---
    async function getSessionToken() {
        if (window.shopify && window.shopify.id) {
            return await shopify.id.getToken();
        }
        return null; // Si test hors iframe
    }

    // --- 2. INITIALISATION ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image'); 
    
    if(shop) {
        sessionStorage.setItem('shop', shop);
        // Si on est en admin (pas en mode client), on charge les crédits
        if (mode !== 'client') fetchCredits(shop);
    }

    // GESTION MODE CLIENT (Widget)
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
                    const els = img.parentElement.querySelectorAll('i, .upload-text, .upload-icon, .upload-sub');
                    els.forEach(el => el.style.display = 'none');
                }
            }
        }
    }

    // --- 3. FETCH CREDITS ---
    async function fetchCredits(s) {
        try {
            const token = await getSessionToken();
            const headers = token ? {'Authorization': `Bearer ${token}`} : {};
            
            const res = await fetch(`/api/get-credits?shop=${s}`, { headers });
            if (res.status === 401) {
                // Redirection login gérée par main.py ou App Bridge
                // window.top.location.href = `/login?shop=${s}`; 
                console.log("Session expirée pour les crédits");
                return; 
            }
            const data = await res.json();
            const el = document.getElementById('credits'); 
            if(el) el.innerText = data.credits;
        } catch(e) { console.error("API Error", e); }
    }

    // --- 4. PREVIEW IMAGE ---
    window.preview = function(inputId, imgId, txtId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                if(img.parentElement) {
                    img.parentElement.classList.add('has-image');
                    const els = img.parentElement.querySelectorAll('i, .upload-text, .upload-icon, .upload-sub');
                    els.forEach(el => el.style.display = 'none');
                }
            };
            reader.readAsDataURL(file);
        }
    };

    // --- 5. GENERATE (AVEC TOKEN + FICHIERS) ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        if (!uFile) return alert("Please upload your photo.");
        if (!autoProductImage && !cFile) return alert("Please select a garment.");

        btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
        document.getElementById('resZone').style.display = 'flex';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';

        try {
            const token = await getSessionToken();
            
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

            if (res.status === 401) {
                if(shop) window.top.location.href = `/login?shop=${shop}`;
                return;
            }

            const data = await res.json();
            if(data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.style.display = 'block';
                document.getElementById('loader').style.display = 'none';
                
                // Refresh credits si en mode admin
                if(data.new_credits !== undefined) {
                    const cel = document.getElementById('credits');
                    if(cel) cel.innerText = data.new_credits;
                }
            } else {
                alert("AI Error: " + (data.error || "Unknown"));
                document.getElementById('resZone').style.display = 'none';
            }
        } catch(e) { 
            console.error(e);
            alert("Error: " + e); 
            document.getElementById('resZone').style.display = 'none';
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = 'Test This Outfit Now <i class="fa-solid fa-wand-magic-sparkles"></i>'; 
        }
    };

    // --- 6. BUY ---
    window.buy = async function(packId, customAmount = 0) {
        if(!shop) return alert("Shop ID missing");
        
        // UI : Bouton en attente
        let btn;
        if(event && event.target) {
             btn = event.target.tagName === 'BUTTON' ? event.target : event.target.closest('button');
        }
        // Fallback si le clic vient d'ailleurs
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
                method: 'POST', headers: headers, body: JSON.stringify(body)
            });

            // CAS CRITIQUE : Session perdue (401)
            if (res.status === 401) {
                console.log("Session perdue, redirection vers le login...");
                window.top.location.href = `/login?shop=${shop}`;
                return;
            }

            const data = await res.json();
            
            if(data.confirmation_url) {
                // Redirection vers le paiement Shopify
                window.top.location.href = data.confirmation_url;
            } else {
                alert("Error: " + (data.error || "Unknown"));
                if(btn) { btn.innerText = oldText; btn.disabled = false; }
            }
        } catch(e) {
            console.error(e);
            alert("Erreur réseau ou configuration API.");
            if(btn) { btn.innerText = oldText; btn.disabled = false; }
        }
    };

    // --- 7. BUY CUSTOM (MANQUAIT DANS TON CODE) ---
    window.buyCustom = function() {
        const amount = document.getElementById('customAmount').value;
        if(amount < 200) return alert("Min 200 credits");
        window.buy('pack_custom', parseInt(amount));
    }

}); // <--- C'EST ICI QUE TU AVAIS OUBLIÉ DE FERMER LE FICHIER
