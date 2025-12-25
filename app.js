document.addEventListener("DOMContentLoaded", function() {
    
    // UI Init
    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    // --- TOKEN HELPER ---
    async function getSessionToken() {
        if (window.shopify && window.shopify.id) {
            return await shopify.id.getToken();
        }
        return null;
    }

    // --- CONFIG ---
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image');

    if(shop) {
        sessionStorage.setItem('shop', shop);
        if (mode === 'client') {
            initClientMode();
        } else {
            fetchCredits(shop); 
        }
    }

    // --- AUTH FETCH ---
    async function authenticatedFetch(url, options = {}) {
        try {
            const token = await getSessionToken();
            const headers = options.headers || {};
            if (token) headers['Authorization'] = `Bearer ${token}`;
            
            const res = await fetch(url, { ...options, headers });
            if (res.status === 401) {
                if (shop) { window.top.location.href = `/login?shop=${shop}`; return null; }
            }
            return res;
        } catch (error) { throw error; }
    }

    async function fetchCredits(s) {
        const res = await authenticatedFetch(`/api/get-credits?shop=${s}`);
        if (res && res.ok) {
            const data = await res.json();
            const el = document.getElementById('credits');
            if(el) el.innerText = data.credits;
        }
    }

    function initClientMode() {
        document.body.classList.add('client-mode');
        // On s'assure que la zone admin est cachée
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
        if (file) {
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

    // --- GENERATE AVEC STORYTELLING ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        if (!uFile) return alert("Please upload your photo.");
        if (!autoProductImage && !cFile) return alert("Please upload a garment.");

        // Animation bouton
        const oldText = btn.innerHTML;
        btn.disabled = true; 
        
        // Affichage Loader
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        document.getElementById('post-actions').style.display = 'none';

        // Storytelling Loop
        const texts = ["Analyzing silhouette...", "Matching fabrics...", "Simulating drape...", "Rendering lighting..."];
        let step = 0;
        const textEl = document.getElementById('loader-text');
        const interval = setInterval(() => {
            if(step < texts.length) {
                textEl.innerText = texts[step];
                step++;
            }
        }, 2500);

        try {
            const formData = new FormData();
            formData.append("shop", shop || "demo");
            formData.append("person_image", uFile);
            if (cFile) formData.append("clothing_file", cFile); 
            else formData.append("clothing_url", autoProductImage); 
            formData.append("category", "upper_body");

            const res = await authenticatedFetch('/api/generate', { method: 'POST', body: formData });

            clearInterval(interval); // Stop le texte

            if (!res) return;
            if (res.status === 402) { alert("Not enough credits!"); btn.disabled = false; btn.innerHTML = oldText; return; }
            if (!res.ok) throw new Error("Server Error");

            const data = await res.json();
            
            if(data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => {
                    ri.style.display = 'block';
                    document.getElementById('loader').style.display = 'none';
                    // Afficher le bouton d'achat
                    document.getElementById('post-actions').style.display = 'block';
                };
                if(data.new_credits !== undefined) {
                    const cel = document.getElementById('credits');
                    if(cel) cel.innerText = data.new_credits;
                }
            } else {
                alert("Error: " + (data.error || "Unknown"));
                document.getElementById('loader').style.display = 'none';
            }
        } catch(e) { 
            clearInterval(interval);
            console.error(e);
            alert("Network Error"); 
            document.getElementById('loader').style.display = 'none';
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldText; 
        }
    };

    window.buy = async function(packId, customAmount = 0, btnElement = null) {
        if(!shop) return alert("Shop ID missing.");
        const btn = btnElement;
        const oldText = btn ? btn.innerText : "...";
        if(btn) { btn.innerText = "Processing..."; btn.disabled = true; }

        try {
            const body = { shop: shop, pack_id: packId, custom_amount: customAmount };
            const res = await authenticatedFetch('/api/buy-credits', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
            });
            if (!res) return;
            const data = await res.json();
            if(data.confirmation_url) window.top.location.href = data.confirmation_url;
            else { alert("Error: " + (data.error || "Unknown")); if(btn) { btn.innerText = oldText; btn.disabled = false; } }
        } catch(e) {
            console.error(e); alert("Network Error"); if(btn) { btn.innerText = oldText; btn.disabled = false; }
        }
    };

    window.buyCustom = function(btnElement) {
        const amount = document.getElementById('customAmount').value;
        if(amount < 200) return alert("Min 200 credits");
        window.buy('pack_custom', parseInt(amount), btnElement);
    }
});
