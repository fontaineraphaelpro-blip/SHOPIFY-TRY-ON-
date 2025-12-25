document.addEventListener("DOMContentLoaded", function() {
    
    // UI Init
    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    // --- 1. TOKEN HELPER (App Bridge 3) ---
    async function getSessionToken() {
        if (window.shopify && window.shopify.id) {
            return await shopify.id.getToken();
        }
        return null;
    }

    // --- 2. CONFIG ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image');

    if(shop) {
        sessionStorage.setItem('shop', shop);
        if (mode !== 'client') fetchCredits(shop);
        else document.getElementById('billing-section').style.display = 'none';
    }

    // --- 3. MODE WIDGET (Client) ---
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
                if(img.parentElement) img.parentElement.querySelector('.upload-content').style.display = 'none';
            }
        }
    }

    // --- 4. FETCH CREDITS ---
    async function fetchCredits(s) {
        try {
            const token = await getSessionToken();
            const headers = token ? {'Authorization': `Bearer ${token}`} : {};
            const res = await fetch(`/api/get-credits?shop=${s}`, { headers });
            
            if (res.status === 401) return console.warn("Session expirée (401)");
            
            const data = await res.json();
            const el = document.getElementById('credits');
            if(el) el.innerText = data.credits;
        } catch(e) { console.error("Err Credits", e); }
    }

    // --- 5. PREVIEW ---
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

    // --- 6. GENERATE (AI) ---
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

            if (res.status === 401) return alert("Session expirée. Veuillez recharger la page.");
            if (res.status === 402) return alert("Crédits insuffisants !");

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
            alert("Erreur Réseau"); 
            document.getElementById('loader').style.display = 'none';
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldText; 
        }
    };

    // --- 7. BUY (Achat Crédits) ---
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
                window.top.location.href = `/login?shop=${shop}`;
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
