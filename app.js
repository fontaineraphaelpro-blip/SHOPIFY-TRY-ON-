document.addEventListener("DOMContentLoaded", function() {
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const shop = params.get('shop');
    const productImg = params.get('product_image');

    // 1. AUTO-DETECT MODE
    if (mode === 'client') {
        document.body.classList.add('client-mode');
        document.getElementById('admin-only-zone').style.display = 'none';
        if (productImg) {
            const img = document.getElementById('prevC');
            img.src = productImg;
            img.style.display = 'block';
            document.getElementById('urlInputState').style.display = 'none';
        }
    }

    // 2. PREVIEW LOCALE
    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                img.parentElement.querySelector('.empty-state').style.display = 'none';
            };
            reader.readAsDataURL(file);
        }
    };

    // 3. GÉNÉRATION IA
    window.generate = async function() {
        const uFile = document.getElementById('person_image').files[0];
        // En mode client on prend l'URL auto, en admin on prend l'input texte
        const cUrl = mode === 'client' ? productImg : document.getElementById('clothing_url').value;

        if (!uFile || !cUrl) return alert("Missing photo or garment!");

        const btn = document.getElementById('btnGo');
        btn.disabled = true;
        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'flex';
        document.getElementById('resImg').style.display = 'none';

        const fd = new FormData();
        fd.append("shop", shop);
        fd.append("person_image", uFile);
        fd.append("clothing_url", cUrl);

        try {
            const res = await fetch('/api/generate', { method: 'POST', body: fd });
            const data = await res.json();
            
            if (res.ok) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.style.display = 'block';
                document.getElementById('post-actions').style.display = 'flex';
            } else {
                alert(data.error || "IA Error");
            }
        } catch (e) {
            alert("Connection error");
        } finally {
            btn.disabled = false;
            document.getElementById('loader').style.display = 'none';
        }
    };
});
