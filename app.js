document.addEventListener("DOMContentLoaded", function() {
    
    // UI Init
    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    // --- 1. TOKEN HELPER ---
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
        if (mode === 'client') {
            initClientMode();
        } else {
            // On charge les crédits, avec retry auto
            fetchCredits(shop); 
        }
    }

    // --- 3. FONCTION MAGIQUE : FETCH AVEC RETRY ---
    // Cette fonction remplace fetch() classique. 
    // Si elle voit une erreur 401, elle redirige vers login et attend.
    async function authenticatedFetch(url, options = {}) {
        try {
            const token = await getSessionToken();
            const headers = options.headers || {};
            if (token) headers['Authorization'] = `Bearer ${token}`;
            
            const res = await fetch(url, { ...options, headers });

            // Si session expirée (401)
            if (res.status === 401) {
                console.log("🔄 Session expirée (401). Tentative de réparation...");
                
                // On force le re-login via Shopify App Bridge
                // Rediriger le TOP frame vers /login va recharger l'app
                // C'est le seul moyen fiable à 100% sur Render gratuit
                if (shop) {
                     // Astuce : On redirige, l'utilisateur verra un chargement rapide
                     // C'est mieux que de devoir cliquer deux fois.
                     window.top.location.href = `/login?shop=${shop}`; 
                     return null; // On arrête tout ici car la page va changer
                }
            }
            return res;
        } catch (error) {
            console.error("Network error:", error);
            throw error;
        }
    }

    // --- 4. FETCH CREDITS ---
    async function fetchCredits(s) {
        const res = await authenticatedFetch(`/api/get-credits?shop=${s}`);
        if (res && res.ok) {
            const data = await res.json();
            const el = document.getElementById('credits');
            if(el) el.innerText = data.credits;
        }
    }

    // --- 5. INITIALISATION CLIENT ---
    function initClientMode() {
        document.body.classList.add('client-mode');
        const adminDash = document.getElementById('admin-dashboard');
        if(adminDash) adminDash.style.display = 'none';
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

    // --- 6. PREVIEW IMAGES ---
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

    // --- 7. GENERATE (IA) ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        if (!uFile) return alert("Photo manquante.");
        if (!autoProductImage && !cFile) return alert("Vêtement manquant.");

        const oldText = btn.innerHTML;
        btn.disabled = true; 
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Traitement...';
        
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';

        try {
            const formData = new FormData();
            formData.append("shop", shop || "demo");
            formData.append("person_image", uFile);
            if (cFile) formData.append("clothing_file", cFile); 
            else formData.append("clothing_url", autoProductImage); 
            formData.append("category", "upper_body");

            // Utilisation de notre fetch sécurisé
            const res = await authenticatedFetch('/api/generate', {
                method: 'POST',
                body: formData
            });

            if (!res) return; // Si null, c'est qu'on est en train de rediriger pour auth

            if (res.status === 402) {
                alert("Crédits insuffisants !");
                btn.disabled = false; btn.innerHTML = oldText;
                return;
            }

            if (!res.ok) throw new Error("Erreur serveur");

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
            alert("Une erreur est survenue (ou session expirée)."); 
            document.getElementById('loader').style.display = 'none';
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldText; 
        }
    };

    // --- 8. BUY (Achat Crédits) ---
    window.buy = async function(packId, customAmount = 0, btnElement = null) {
        if(!shop) return alert("Erreur Shop ID. Rechargez la page.");
        
        const btn = btnElement;
        const oldText = btn ? btn.innerText : "...";
        if(btn) { btn.innerText = "Wait..."; btn.disabled = true; }

        try {
            const body = { shop: shop, pack_id: packId, custom_amount: customAmount };

            // Utilisation de notre fetch sécurisé
            const res = await authenticatedFetch('/api/buy-credits', {
                method: 'POST', 
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            });

            if (!res) return; // Redirection auth en cours

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
