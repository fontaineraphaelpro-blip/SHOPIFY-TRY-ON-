document.addEventListener("DOMContentLoaded", function() {
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const shop = params.get('shop');
    const productImg = params.get('product_image');

    if(shop) sessionStorage.setItem('vton_shop', shop);
    const activeShop = shop || sessionStorage.getItem('vton_shop');

    // 1. GESTION DU MODE CLIENT (WIDGET)
    if (mode === 'client') {
        document.body.classList.add('client-mode');
        const adminZone = document.getElementById('admin-only-zone');
        if(adminZone) adminZone.style.display = 'none';
        
        if (productImg) {
            const img = document.getElementById('prevC');
            img.src = productImg;
            img.style.display = 'block';
            img.parentElement.querySelector('.empty-state').style.display = 'none';
        }
    }

    // 2. CHARGEMENT DES DATA (ADMIN DASHBOARD)
    if (mode !== 'client' && activeShop) {
        fetch(`/api/get-data?shop=${activeShop}`)
            .then(res => res.json())
            .then(data => {
                document.getElementById('credits').innerText = data.credits || 0;
                document.getElementById('stat-tryons').innerText = data.usage || 0;
                document.getElementById('stat-atc').innerText = data.atc || 0;
                
                if(data.widget) {
                    document.getElementById('ws-text').value = data.widget.text;
                    document.getElementById('ws-color').value = data.widget.bg;
                    document.getElementById('ws-text-color').value = data.widget.color;
                    document.getElementById('ws-limit').value = data.security.max_tries;
                    window.updateWidgetPreview();
                }
                const vipPercent = Math.min(((data.lifetime || 0) / 500) * 100, 100);
                document.querySelector('.vip-fill').style.width = vipPercent + "%";
                document.querySelector('.vip-marker').style.left = vipPercent + "%";
                
                const forecast = Math.floor((data.credits || 0) / 8);
                document.querySelector('.rs-value').innerText = forecast + (forecast > 1 ? " Days" : " Day");
            });
    }

    // 3. GÉNÉRATION IA
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        if (!uFile) return alert("Please upload your photo first!");

        const btn = document.getElementById('btnGo');
        btn.disabled = true;
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        document.getElementById('post-actions').style.display = 'none';

        const fd = new FormData();
        fd.append("shop", activeShop);
        fd.append("person_image", uFile);
        fd.append("clothing_url", productImg || "");

        try {
            const res = await fetch('/api/generate', { method: 'POST', body: fd });
            const data = await res.json();
            if (data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => {
                    ri.style.display = 'block';
                    document.getElementById('loader').style.display = 'none';
                    document.getElementById('post-actions').style.display = 'block';
                };
            } else { alert(data.error || "Generation Error"); document.getElementById('loader').style.display = 'none';}
        } catch (e) { alert("Server Error"); document.getElementById('loader').style.display = 'none';}
        finally { btn.disabled = false; }
    };

    // 4. RÉGLAGES & TRACKING
    window.saveSettings = function() {
        const settings = {
            shop: activeShop,
            text: document.getElementById('ws-text').value,
            bg: document.getElementById('ws-color').value,
            color: document.getElementById('ws-text-color').value,
            max_tries: parseInt(document.getElementById('ws-limit').value)
        };
        fetch('/api/save-settings', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(settings)
        }).then(() => alert("Settings Saved!"));
    };

    window.trackATC = function() {
        fetch('/api/track-atc', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ shop: activeShop })
        });
        alert("Added to cart! Statistics updated.");
    };

    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        const reader = new FileReader();
        reader.onload = e => {
            const img = document.getElementById(imgId);
            img.src = e.target.result;
            img.style.display = 'block';
            img.parentElement.querySelector('.empty-state').style.display = 'none';
        };
        reader.readAsDataURL(file);
    };

    window.updateWidgetPreview = function() {
        const btn = document.getElementById('ws-preview-btn');
        btn.style.backgroundColor = document.getElementById('ws-color').value;
        btn.style.color = document.getElementById('ws-text-color').value;
        btn.querySelector('span').innerText = document.getElementById('ws-text').value;
    };
});
