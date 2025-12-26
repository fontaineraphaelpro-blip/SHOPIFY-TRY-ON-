document.addEventListener("DOMContentLoaded", function() {

    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image');

    // FIX SESSION
    try {
        if(!shop) shop = sessionStorage.getItem('shop');
        if(shop) sessionStorage.setItem('shop', shop);
    } catch(e) {}

    async function getSessionToken() {
        if (window.shopify && window.shopify.id) return await shopify.id.getToken();
        return null;
    }

    async function authenticatedFetch(url, options = {}) {
        try {
            const token = await getSessionToken();
            const headers = options.headers || {};
            if (token) headers['Authorization'] = `Bearer ${token}`;
            const res = await fetch(url, { ...options, headers });
            if (res.status === 401 && shop && mode !== 'client') { window.top.location.href = `/login?shop=${shop}`; return null; }
            return res;
        } catch (error) { throw error; }
    }

    if(shop) {
        if (mode === 'client') initClientMode();
        else initAdminMode(shop);
    }

    // --- DASHBOARD ---
    async function initAdminMode(s) {
        const res = await authenticatedFetch(`/api/get-data?shop=${s}`);
        if (res && res.ok) {
            const data = await res.json();

            // Affichage Stats
            updateDashboardStats(data.credits || 0);
            updateVIPStatus(data.lifetime || 0);

            // Compteurs simples
            const tryEl = document.getElementById('stat-tryons');
            const atcEl = document.getElementById('stat-atc');
            if(tryEl) tryEl.innerText = data.usage || 0;
            if(atcEl) atcEl.innerText = data.atc || 0;

            if(data.widget) {
                document.getElementById('ws-text').value = data.widget.text || "Try It On Now ✨";
                document.getElementById('ws-color').value = data.widget.bg || "#000000";
                document.getElementById('ws-text-color').value = data.widget.color || "#ffffff";
                if(data.security) document.getElementById('ws-limit').value = data.security.max_tries || 5;
                window.updateWidgetPreview();
            }
        }
    }

    function updateDashboardStats(credits) {
        const el = document.getElementById('credits');
        if(el) el.innerText = credits;
        const supplyCard = document.querySelector('.smart-supply-card');
        const alertBadge = document.querySelector('.alert-badge');
        const daysEl = document.querySelector('.rs-value');
        if (supplyCard && daysEl) {
            let daysLeft = Math.floor(credits / 8); 
            if(daysLeft < 1) daysLeft = "< 1";
            daysEl.innerText = daysLeft + (daysLeft === "< 1" ? " Day" : " Days");
            if (credits < 20) {
                supplyCard.style.background = "#fff0f0";
                alertBadge.innerText = "CRITICAL";
                alertBadge.style.background = "#dc2626";
            } else {
                supplyCard.style.background = "#f0fdf4";
                alertBadge.innerText = "HEALTHY";
                alertBadge.style.background = "#16a34a";
            }
        }
    }

    function updateVIPStatus(lifetime) {
        const fill = document.querySelector('.vip-fill');
        const marker = document.querySelector('.vip-marker');
        let percent = (lifetime / 500) * 100;
        if(percent > 100) percent = 100;
        if(fill) fill.style.width = percent + "%";
        if(marker) marker.style.left = percent + "%";
        if(lifetime >= 500) {
            const title = document.querySelector('.vip-title strong');
            if(title) title.innerText = "Gold Member";
        }
    }

    window.saveSettings = async function(btn) {
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
            else { alert("Save failed"); }
        } catch(e) { console.error(e); alert("Error saving"); }
        finally { btn.disabled = false; }
    };

    window.trackATC = async function() {
        if(shop) {
            try {
                await fetch('/api/track-atc', {
                    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ shop: shop })
                });
            } catch(e) { console.error("Tracking Error", e); }
        }
    };

    function initClientMode() {
        document.body.classList.add('client-mode');
        const adminZone = document.getElementById('admin-only-zone');
        if(adminZone) adminZone.style.display = 'none';
        if (autoProductImage) {
            const img = document.getElementById('prevC');
            if(img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                if(img.parentElement) img.parentElement.querySelector('.empty-state').style.display = 'none';
            }
        }
    }

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

    // 
window.generate = async function() {
    const uFile = document.getElementById('uImg').files[0];
    const cFile = document.getElementById('cImg').files[0];
    const btn = document.getElementById('btnGo');
    
    if (!uFile) return alert("Please upload your photo.");
    // Si on n'a ni URL auto, ni fichier uploadé manuellement
    if (!autoProductImage && !cFile) return alert("Please upload a garment.");

    const oldText = btn.innerHTML;
    btn.disabled = true; 
    btn.innerHTML = "Generating...";

    document.getElementById('resZone').style.display = 'block';
    document.getElementById('loader').style.display = 'block';
    document.getElementById('resImg').style.display = 'none';
    document.getElementById('post-actions').style.display = 'none';

    const textEl = document.getElementById('loader-text');
    const texts = ["Analyzing silhouette...", "Matching fabrics...", "Simulating drape...", "Rendering lighting..."];
    let step = 0;
    const interval = setInterval(() => { if(step < texts.length) textEl.innerText = texts[step++]; }, 2500);

    try {
        const formData = new FormData();
        formData.append("shop", shop);
        formData.append("person_image", uFile); // La photo de l'utilisateur reste un fichier
        formData.append("category", "upper_body");

        // --- CORRECTION MAJEURE ICI ---
        // Si on a l'URL du produit (Mode Client/Widget), on envoie l'URL.
        // C'est beaucoup plus stable pour Replicate.
        if (autoProductImage) {
            console.log("Using Product URL:", autoProductImage);
            formData.append("clothing_url", autoProductImage); 
            // On n'envoie PAS clothing_file pour ne pas embrouiller le serveur
        } else {
            // Sinon (Mode Admin ou test manuel), on envoie le fichier
            formData.append("clothing_file", cFile);
        }

        let res;
        if (mode === 'client') res = await fetch('/api/generate', { method: 'POST', body: formData });
        else res = await authenticatedFetch('/api/generate', { method: 'POST', body: formData });

        clearInterval(interval);

        if (!res) return;
        if (res.status === 429) { alert("Daily limit reached."); document.getElementById('loader').style.display = 'none'; return; }
        if (res.status === 402) { alert("Not enough credits!"); btn.disabled = false; btn.innerHTML = oldText; return; }
        if (!res.ok) throw new Error("Server Error");

        const data = await res.json();
        if(data.result_image_url){
            const ri = document.getElementById('resImg');
            ri.src = data.result_image_url;
            ri.onload = () => { ri.style.display = 'block'; document.getElementById('loader').style.display = 'none'; document.getElementById('post-actions').style.display = 'block'; };
        } else { alert("Error: " + (data.error || "Unknown")); document.getElementById('loader').style.display = 'none'; }
    } catch(e) { clearInterval(interval); console.error(e); alert("Network Error"); document.getElementById('loader').style.display = 'none'; }
    finally { btn.disabled = false; btn.innerHTML = oldText; }
};

    // --- FONCTIONS DE PAIEMENT (MANQUANTES) ---

    window.buy = async function(packId, amount, btn) {
        const oldText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';

        try {
            // 1. On appelle ton backend pour créer le lien de paiement
            const res = await authenticatedFetch('/api/buy-credits', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    shop: shop,
                    pack_id: packId,
                    custom_amount: parseInt(amount)
                })
            });

            const data = await res.json();

            // 2. Si on reçoit l'URL de confirmation, on redirige la fenêtre PRINCIPALE (pas l'iframe)
            if (data.confirmation_url) {
                // Important: window.top pour sortir de l'iframe
                window.top.location.href = data.confirmation_url; 
            } else {
                alert("Payment Error: " + (data.error || "Unknown error"));
                btn.disabled = false;
                btn.innerHTML = oldText;
            }
        } catch (e) {
            console.error(e);
            alert("Network Error");
            btn.disabled = false;
            btn.innerHTML = oldText;
        }
    };

    // Pour le bouton "Custom Order"
    window.buyCustom = function(btn) {
        const amount = document.getElementById('customAmount').value;
        if(amount < 50) return alert("Minimum 50 credits for custom order.");
        // On appelle la fonction buy avec le pack 'pack_custom'
        buy('pack_custom', amount, btn);
    };
});
