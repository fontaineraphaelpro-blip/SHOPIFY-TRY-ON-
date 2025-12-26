document.addEventListener("DOMContentLoaded", function() {

    // --- CONFIG ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode'); 
    const shop = params.get('shop'); 
    const autoProductImage = params.get('product_image');

    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    // --- INTERFACE MODE ---
    if (mode === 'client') {
        console.log("👋 Mode Client:", shop);
        document.body.classList.add('client-mode');
        if(document.getElementById('admin-only-zone')) 
            document.getElementById('admin-only-zone').style.display = 'none';

        if (autoProductImage && document.getElementById('prevC')) {
            document.getElementById('prevC').src = autoProductImage;
            document.getElementById('prevC').style.display = 'block';
            document.getElementById('prevC').parentElement.querySelector('.empty-state').style.display = 'none';
        }
    } else {
        console.log("👑 Mode Admin");
        if (shop) initAdminMode(shop);
    }

    // --- UPLOAD PREVIEW ---
    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                document.getElementById(imgId).src = e.target.result;
                document.getElementById(imgId).style.display = 'block';
                document.getElementById(imgId).parentElement.querySelector('.empty-state').style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    };

    // --- GENERATE ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        if (!shop) return alert("Erreur: Boutique non identifiée.");
        if (!uFile) return alert("Photo manquante (Étape 1).");
        if (!autoProductImage && !cFile) return alert("Vêtement manquant (Étape 2).");

        const oldText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = "Création... <i class='fa-solid fa-spinner fa-spin'></i>";
        
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        
        try {
            const formData = new FormData();
            formData.append("shop", shop);
            formData.append("person_image", uFile);
            
            if (autoProductImage) formData.append("clothing_url", autoProductImage);
            else formData.append("clothing_file", cFile);

            let res;
            if (mode === 'client') {
                res = await fetch('/api/generate', { method: 'POST', body: formData });
            } else {
                res = await authenticatedFetch('/api/generate', { method: 'POST', body: formData });
            }

            if (!res.ok) {
                const txt = await res.text();
                let msg = txt;
                try { msg = JSON.parse(txt).error; } catch(e){}
                throw new Error(msg);
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
            } else throw new Error("Pas d'image reçue.");

        } catch (e) {
            console.error(e);
            alert("Erreur: " + e.message);
            document.getElementById('loader').style.display = 'none';
        } finally {
            btn.disabled = false;
            btn.innerHTML = oldText;
        }
    };

    // --- ADMIN FUNCS ---
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
            const res = await authenticatedFetch(`/api/get-data?shop=${s}`);
            if (res.ok) {
                const data = await res.json();
                if(document.getElementById('credits')) document.getElementById('credits').innerText = data.credits;
            }
        } catch (e) {}
    }
    window.buy = async function(pid, amt, btn) {
        const oldText = btn.innerHTML;
        btn.disabled = true; btn.innerHTML = '...';
        try {
            const res = await authenticatedFetch('/api/buy-credits', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ shop: shop, pack_id: pid, custom_amount: parseInt(amt) })
            });
            const data = await res.json();
            if (data.confirmation_url) window.top.location.href = data.confirmation_url;
            else alert("Erreur paiement");
        } catch (e) { alert("Erreur réseau"); }
        finally { btn.disabled = false; btn.innerHTML = oldText; }
    };
    window.buyCustom = function(btn) {
        window.buy('pack_custom', document.getElementById('customAmount').value, btn);
    };
});
