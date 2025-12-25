document.addEventListener("DOMContentLoaded", function() {

    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    /* ======================================================
       🔥 SHOP INITIALISATION (FIX DÉFINITIF)
    ====================================================== */
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    const autoProductImage = params.get('product_image');

    let shop = params.get('shop');

    // fallback session
    try {
        if (!shop) shop = sessionStorage.getItem('shop');
        if (shop) sessionStorage.setItem('shop', shop);
    } catch(e) {}

    // validation stricte
    if (!shop) {
        alert("Shop missing. Please reload the page.");
        throw new Error("SHOP_NOT_FOUND");
    }

    if (!shop.endsWith(".myshopify.com")) {
        alert("Invalid shop domain");
        throw new Error("INVALID_SHOP");
    }

    console.log("✅ SHOP:", shop);

    /* ======================================================
       AUTH
    ====================================================== */
    async function getSessionToken() {
        if (window.shopify && window.shopify.id) {
            return await shopify.id.getToken();
        }
        return null;
    }

    async function authenticatedFetch(url, options = {}) {
        try {
            const token = await getSessionToken();
            const headers = options.headers || {};
            if (token) headers['Authorization'] = `Bearer ${token}`;
            const res = await fetch(url, { ...options, headers });
            if (res.status === 401 && shop && mode !== 'client') {
                window.top.location.href = `/login?shop=${shop}`;
                return null;
            }
            return res;
        } catch (error) {
            throw error;
        }
    }

    if (mode === 'client') initClientMode();
    else initAdminMode(shop);

    /* ======================================================
       ADMIN DASHBOARD
    ====================================================== */
    async function initAdminMode(s) {
        const res = await authenticatedFetch(`/api/get-data?shop=${s}`);
        if (res && res.ok) {
            const data = await res.json();

            updateDashboardStats(data.credits || 0);
            updateVIPStatus(data.lifetime || 0);

            const tryEl = document.getElementById('stat-tryons');
            const atcEl = document.getElementById('stat-atc');
            if (tryEl) tryEl.innerText = data.usage || 0;
            if (atcEl) atcEl.innerText = data.atc || 0;

            if (data.widget) {
                document.getElementById('ws-text').value = data.widget.text || "Try It On Now ✨";
                document.getElementById('ws-color').value = data.widget.bg || "#000000";
                document.getElementById('ws-text-color').value = data.widget.color || "#ffffff";
                if (data.security) document.getElementById('ws-limit').value = data.security.max_tries || 5;
                window.updateWidgetPreview();
            }
        }
    }

    function updateDashboardStats(credits) {
        const el = document.getElementById('credits');
        if (el) el.innerText = credits;
    }

    function updateVIPStatus(lifetime) {
        const fill = document.querySelector('.vip-fill');
        let percent = (lifetime / 500) * 100;
        if (percent > 100) percent = 100;
        if (fill) fill.style.width = percent + "%";
    }

    /* ======================================================
       CLIENT MODE
    ====================================================== */
    function initClientMode() {
        document.body.classList.add('client-mode');
        const adminZone = document.getElementById('admin-only-zone');
        if (adminZone) adminZone.style.display = 'none';

        if (autoProductImage) {
            const img = document.getElementById('prevC');
            if (img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                const es = img.parentElement?.querySelector('.empty-state');
                if (es) es.style.display = 'none';
            }
        }
    }

    /* ======================================================
       GENERATE (🔥 FIX PRINCIPAL)
    ====================================================== */
    window.generate = async function() {
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');

        if (!uFile) return alert("Please upload your photo.");
        if (!autoProductImage && !cFile) return alert("Please upload a garment.");

        btn.disabled = true;

        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        document.getElementById('post-actions').style.display = 'none';

        try {
            const formData = new FormData();

            // 🔥 PLUS DE "demo"
            formData.append("shop", shop);
            formData.append("person_image", uFile);

            if (cFile) formData.append("clothing_file", cFile);
            else formData.append("clothing_url", autoProductImage);

            formData.append("category", "upper_body");

            const res = mode === 'client'
                ? await fetch('/api/generate', { method: 'POST', body: formData })
                : await authenticatedFetch('/api/generate', { method: 'POST', body: formData });

            if (!res) return;

            if (!res.ok) {
                const err = await res.json();
                console.error("❌ API ERROR:", err);
                alert(err.error || "Server error");
                document.getElementById('loader').style.display = 'none';
                btn.disabled = false;
                return;
            }

            const data = await res.json();

            if (data.result_image_url) {
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => {
                    ri.style.display = 'block';
                    document.getElementById('loader').style.display = 'none';
                    document.getElementById('post-actions').style.display = 'block';
                };
            } else {
                alert("Generation failed");
                document.getElementById('loader').style.display = 'none';
            }

        } catch (e) {
            console.error(e);
            alert("Network error");
            document.getElementById('loader').style.display = 'none';
        } finally {
            btn.disabled = false;
        }
    };

});
