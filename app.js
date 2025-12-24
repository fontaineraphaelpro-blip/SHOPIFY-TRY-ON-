document.addEventListener("DOMContentLoaded", async function() {
    document.body.classList.add('loaded');
    
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image'); 
    
    if(shop) sessionStorage.setItem('shop', shop);

    // --- INITIALISATION ---
    if (mode === 'client') {
        document.body.classList.add('client-mode');
        document.getElementById('admin-dashboard').style.display = 'none';
        document.getElementById('studio-interface').style.display = 'block';
        document.getElementById('client-title').style.display = 'block';

        if (autoProductImage) {
            const img = document.getElementById('prevC');
            img.src = autoProductImage;
            img.style.display = 'block';
            img.parentElement.classList.add('has-image');
            const els = img.parentElement.querySelectorAll('i, .upload-text, .upload-icon, .upload-sub');
            els.forEach(el => el.style.display = 'none');
        }
    } else {
        if(shop) fetchCredits(shop);
    }

    // --- FONCTION RECUPERATION CREDITS ---
    async function fetchCredits(s) {
        try {
            const token = await window.shopify.idToken();
            const res = await fetch(`/api/get-credits?shop=${s}`, {
                headers: { "Authorization": `Bearer ${token}` }
            });

            if (res.status === 401) { 
                // Utilisation de la redirection App Bridge pour le login
                window.location.href = `/login?shop=${s}`; 
                return; 
            }
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) { console.error("Erreur Credits:", e); }
    }

    // --- FONCTION ACHAT (BOUTONS) ---
    window.buy = async function(packId) {
        console.log("Tentative d'achat pack:", packId);
        if(!shop) return alert("Shop ID missing");
        
        // Gestion visuelle du bouton
        let btn = event.currentTarget.tagName === 'BUTTON' ? event.currentTarget : event.target.closest('button');
        const oldText = btn.innerText;
        btn.innerText = "Redirecting...";
        btn.disabled = true;

        try {
            // 1. On récupère le Session Token
            const token = await window.shopify.idToken();
            
            // 2. Appel API
            const res = await fetch('/api/buy-credits', {
                method: 'POST', 
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ shop: shop, pack_id: packId })
            });

            if (res.status === 401) {
                window.location.href = `/login?shop=${shop}`;
                return;
            }

            const data = await res.json();
            
            if(data.confirmation_url) {
                console.log("URL de paiement reçue, redirection...");
                // IMPORTANT: App Bridge 3.0 utilise window.open pour sortir de l'iframe
                // vers une URL de confirmation de paiement Shopify
                window.open(data.confirmation_url, "_top");
            } else {
                alert("Erreur: " + (data.error || "Inconnue"));
                btn.innerText = oldText;
                btn.disabled = false;
            }
        } catch(e) {
            console.error("Erreur Achat:", e);
            alert("Erreur de connexion avec Shopify");
            btn.innerText = oldText;
            btn.disabled = false;
        }
    };

    // --- ACHAT PERSONNALISÉ ---
    window.buyCustom = async function() {
        const amount = document.getElementById('customAmount').value;
        if(amount < 200) return alert("Min 200 credits");
        
        try {
            const token = await window.shopify.idToken();
            const res = await fetch('/api/buy-credits', {
                 method: 'POST', 
                 headers: {
                     'Content-Type': 'application/json',
                     'Authorization': `Bearer ${token}`
                 },
                 body: JSON.stringify({ shop: shop, pack_id: 'pack_custom', custom_amount: parseInt(amount) })
            });
            
            const data = await res.json();
            if(data.confirmation_url) window.open(data.confirmation_url, "_top");
            else alert(data.error);
        } catch(e) { console.error(e); }
    };

    // --- IA GENERATION ---
    window.preview = function(inputId, imgId, txtId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                img.parentElement.classList.add('has-image');
                const els = img.parentElement.querySelectorAll('i, .upload-text, .upload-icon, .upload-sub');
                els.forEach(el => el.style.display = 'none');
            };
            reader.readAsDataURL(file);
        }
    };

    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        if (!u || (!cFile && !autoProductImage)) return alert("Please upload photos.");
        
        const btn = document.getElementById('btnGo');
        btn.disabled = true; btn.innerHTML = 'Processing...';
        document.getElementById('resZone').style.display = 'flex';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resZone').scrollIntoView({ behavior: 'smooth' });
        
        const to64 = f => new Promise(r => { const rd = new FileReader(); rd.readAsDataURL(f); rd.onload=()=>r(rd.result); });

        try {
            let garmentData = cFile ? await to64(cFile) : autoProductImage;
            const res = await fetch('/api/generate', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    shop: shop || "demo", 
                    person_image_url: await to64(u), 
                    clothing_image_url: garmentData, 
                    category: "upper_body" 
                })
            });
            const data = await res.json();
            if(data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.style.display = 'block';
                document.getElementById('loader').style.display = 'none';
                if(mode !== 'client') fetchCredits(shop);
            } else alert("AI Error: " + (data.error || "Unknown"));
        } catch(e) { alert("Error: " + e); }
        finally { btn.disabled = false; btn.innerHTML = 'Test This Outfit Now'; }
    };
});
