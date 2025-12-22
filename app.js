document.addEventListener("DOMContentLoaded", function() {
    
    // 1. DÉTECTION DU MODE
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode'); 
    const shop = params.get('shop') || sessionStorage.getItem('shop');

    if(shop) sessionStorage.setItem('shop', shop);

    // On rend le body visible maintenant que le JS commence
    document.body.classList.add('loaded');

    if (mode === 'client') {
        // C'EST LE CLIENT : On active le mode "Clean"
        document.body.classList.add('client-mode');
        document.getElementById('client-title').style.display = 'block';
    } else {
        // C'EST L'ADMIN : On charge les crédits
        if(shop) fetchCredits(shop);
    }

    // 2. PRÉVISUALISATION
    window.preview = function(inputId, imgId, phId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                document.getElementById(imgId).src = e.target.result;
                document.getElementById(imgId).style.display = 'block';
                document.getElementById(phId).style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    }

    // 3. GÉNÉRATION
    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const c = document.getElementById('cImg').files[0];
        
        if (!u || !c) return alert("Veuillez ajouter les 2 photos !");

        const btn = document.getElementById('btnGo');
        const load = document.getElementById('loading');
        const ph = document.getElementById('phRes');
        const resImg = document.getElementById('resImg');

        btn.disabled = true;
        load.style.display = 'block';
        ph.style.display = 'none';
        resImg.style.display = 'none';

        const toBase64 = f => new Promise(r => {
            const reader = new FileReader();
            reader.readAsDataURL(f);
            reader.onload = () => r(reader.result);
        });

        try {
            const res = await fetch('/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    shop: shop || "demo",
                    person_image_url: await toBase64(u),
                    clothing_image_url: await toBase64(c),
                    category: "upper_body"
                })
            });
            const data = await res.json();
            
            if(data.result_image_url) {
                resImg.src = data.result_image_url;
                resImg.style.display = 'block';
                load.style.display = 'none';
                if(mode !== 'client') fetchCredits(shop); // Admin only
            } else {
                alert("Erreur: " + JSON.stringify(data));
                btn.disabled = false;
                load.style.display = 'none';
            }
        } catch(e) {
            alert("Erreur technique");
            btn.disabled = false;
            load.style.display = 'none';
        } finally {
            btn.disabled = false;
        }
    };

    async function fetchCredits(s) {
        try {
            const res = await fetch(`/api/get-credits?shop=${s}`);
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) { console.error(e); }
    }

    window.buy = async function(packId) {
        try {
            const res = await fetch('/api/buy-credits', {
                method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({shop: shop, pack_id: packId})
            });
            const data = await res.json();
            if(data.confirmation_url) window.top.location.href = data.confirmation_url;
        } catch(e) { alert("Erreur paiement"); }
    }
});
