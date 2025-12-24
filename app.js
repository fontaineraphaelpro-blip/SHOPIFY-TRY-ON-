document.addEventListener("DOMContentLoaded", function() {
    const params = new URLSearchParams(window.location.search);
    const shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image'); 
    
    if(shop) {
        sessionStorage.setItem('shop', shop);
        fetchCredits(shop);
    }

    // Auto-fill product image from Shopify
    if (autoProductImage) {
        const imgC = document.getElementById('prevC');
        imgC.src = autoProductImage;
        imgC.style.display = 'block';
        imgC.parentElement.classList.add('has-image');
        const labels = imgC.parentElement.querySelectorAll('i, .upload-text, .upload-sub');
        labels.forEach(el => el.style.display = 'none');
    }

    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
                img.parentElement.classList.add('has-image');
                const labels = img.parentElement.querySelectorAll('i, .upload-text, .upload-sub');
                labels.forEach(el => el.style.display = 'none');
            };
            reader.readAsDataURL(file);
        }
    };

    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const btn = document.getElementById('btnGo');
        
        if (!uFile || !autoProductImage) return alert("Please upload your photo.");

        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> AI Processing...';
        
        document.getElementById('resZone').style.display = 'flex';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';

        // Utilisation de FormData pour envoyer vers le backend Metafield
        const formData = new FormData();
        formData.append("shop", shop);
        formData.append("person_image", uFile);
        formData.append("clothing_url", autoProductImage);

        try {
            const res = await fetch('/api/generate', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            if (data.result_image_url) {
                document.getElementById('resImg').src = data.result_image_url;
                document.getElementById('resImg').style.display = 'block';
                document.getElementById('loader').style.display = 'none';
                document.getElementById('credits').innerText = data.new_credits;
            } else {
                alert("Error: " + (data.error || "Unknown error"));
                btn.disabled = false;
            }
        } catch (e) {
            alert("Connection error");
            btn.disabled = false;
        } finally {
            btn.innerHTML = 'Test This Outfit Now <i class="fa-solid fa-wand-magic-sparkles"></i>';
            btn.disabled = false;
        }
    };

    async function fetchCredits(s) {
        try {
            const res = await fetch(`/api/get-credits?shop=${s}`);
            const data = await res.json();
            if(data.credits !== undefined) {
                document.getElementById('credits').innerText = data.credits;
            }
        } catch(e) { console.log("Credit fetch failed"); }
    }
});
