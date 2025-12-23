document.addEventListener("DOMContentLoaded", function() {
    const params = new URLSearchParams(window.location.search);
    const shop = params.get("shop");
    if (shop && !window.location.search.includes('mode=client')) {
        fetchCredits(shop);
    }
});

async function fetchCredits(shop) {
    try {
        const response = await fetch(`/api/get-credits?shop=${shop}`);
        const data = await response.json();
        const el = document.getElementById("credits-count");
        if (el) el.innerText = data.credits !== undefined ? data.credits : 0;
    } catch (e) { console.error(e); }
}

function previewImg(input, targetId) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = (e) => {
            const img = document.getElementById(targetId);
            img.src = e.target.result;
            img.style.display = 'block';
            input.parentElement.classList.add('has-image');
        };
        reader.readAsDataURL(input.files[0]);
    }
}

async function startGeneration() {
    const userImg = document.getElementById('preview1').src;
    const prodImg = document.getElementById('product-preview').src;
    const shop = new URLSearchParams(window.location.search).get('shop');

    if (!userImg || userImg.includes('window.location')) return alert("Upload photo first!");

    document.getElementById('loading-spinner').classList.remove('hidden');
    try {
        const response = await fetch("/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ shop, person_image_url: userImg, clothing_image_url: prodImg, category: "tops" })
        });
        const data = await response.json();
        if (data.result_image_url) {
            const resImg = document.getElementById('result-img');
            resImg.src = data.result_image_url;
            resImg.style.display = 'block';
        }
    } catch (e) { alert("Error: " + e); }
    finally { document.getElementById('loading-spinner').classList.add('hidden'); }
}
