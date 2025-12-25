<script>
document.addEventListener('DOMContentLoaded', function() {
    const btn = document.getElementById('vton-trigger');
    const modal = document.getElementById('vton-modal');
    const closeBtn = document.getElementById('vton-close');
    const backdrop = document.querySelector('.vton-backdrop');
    const iframe = document.getElementById('vton-frame');
    const loader = document.getElementById('vton-loader');

    if(!btn || !modal) return;

    btn.addEventListener('click', function(e) {
        e.preventDefault();
        modal.style.display = 'block';
        setTimeout(() => { modal.classList.add('open'); }, 10);
        document.body.style.overflow = 'hidden'; 

        if (!iframe.src) {
            let url = iframe.getAttribute('data-src');
            url = encodeURI(url); // ✅ Encode URL correctement
            iframe.src = url;
            iframe.onload = () => { loader.style.display = 'none'; };
        }
    });

    function closeModal() {
        modal.classList.remove('open');
        setTimeout(() => {
            modal.style.display = 'none';
            document.body.style.overflow = '';
        }, 300);
    }

    closeBtn.addEventListener('click', closeModal);
    if(backdrop) backdrop.addEventListener('click', closeModal);

    // --- GENERATE ---
    window.generate = async function() {
        const uFile = document.getElementById('uImg')?.files[0];
        const cFile = document.getElementById('cImg')?.files[0];
        const btnGo = document.getElementById('btnGo');
        if(!uFile) return alert("Please upload your photo.");

        const autoProductImage = iframe.dataset.productImage; // récupérer URL Shopify
        if(!cFile && !autoProductImage) return alert("Please provide a garment.");

        btnGo.disabled = true;
        const oldText = btnGo.innerHTML;
        btnGo.innerHTML = "Generating...";

        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        document.getElementById('post-actions').style.display = 'none';

        const loaderText = document.getElementById('loader-text');
        const steps = ["Initializing...", "Analyzing silhouette...", "Matching fabrics...", "Rendering lighting..."];
        let step = 0;
        const interval = setInterval(() => {
            if(step < steps.length) loaderText.innerText = steps[step++];
        }, 2500);

        try {
            const formData = new FormData();
            formData.append("shop", iframe.dataset.shop);
            formData.append("person_image", uFile);

            if(cFile) formData.append("clothing_file", cFile);
            else if(autoProductImage) {
                formData.append("clothing_url", autoProductImage.startsWith("//") ? "https:" + autoProductImage : autoProductImage);
            }

            formData.append("category", "upper_body");

            console.log("FormData Entries:");
            for(const pair of formData.entries()) console.log(pair[0], pair[1]);

            const res = await fetch('/api/generate', { method: 'POST', body: formData });
            clearInterval(interval);

            if(!res.ok) {
                if(res.status === 402) alert("Not enough credits!");
                else if(res.status === 429) alert("Daily limit reached!");
                else alert("Server Error");
                btnGo.disabled = false; btnGo.innerHTML = oldText;
                document.getElementById('loader').style.display = 'none';
                return;
            }

            const data = await res.json();
            if(data.result_image_url) {
                const resImg = document.getElementById('resImg');
                resImg.src = data.result_image_url;
                resImg.onload = () => {
                    resImg.style.display = 'block';
                    document.getElementById('loader').style.display = 'none';
                    document.getElementById('post-actions').style.display = 'block';
                };
            } else {
                alert("Error: " + (data.error || "Unknown"));
                document.getElementById('loader').style.display = 'none';
            }

        } catch(e) {
            console.error(e);
            alert("Network Error");
            clearInterval(interval);
            document.getElementById('loader').style.display = 'none';
        } finally {
            btnGo.disabled = false;
            btnGo.innerHTML = oldText;
        }
    }
});
</script>
