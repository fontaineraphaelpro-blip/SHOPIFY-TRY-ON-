document.addEventListener("DOMContentLoaded", function() {

    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image');

    // === RÉCUPÉRATION DU SHOP EN MODE CLIENT ===
    if (mode === 'client' && !shop) {
        console.log("⚠️ Mode client détecté, recherche du shop...");
        
        const hash = window.location.hash;
        if (hash.includes('shop=')) {
            const match = hash.match(/shop=([^&]+)/);
            if (match) shop = match[1];
        }
        
        if (!shop && window.Shopify && window.Shopify.shop) {
            shop = window.Shopify.shop;
            console.log("✅ Shop depuis Shopify.shop:", shop);
        }
        
        if (!shop) {
            try {
                const parentUrl = document.referrer || window.location.ancestorOrigins?.[0];
                if (parentUrl && parentUrl.includes('.myshopify.com')) {
                    const match = parentUrl.match(/https?:\/\/([^\/]+)/);
                    if (match) shop = match[1];
                    console.log("✅ Shop depuis referrer:", shop);
                }
            } catch(e) {
                console.error("Erreur extraction shop:", e);
            }
        }

        if (!shop) {
            try {
                if (window.parent !== window) {
                    const parentShop = window.parent.location.hostname;
                    if (parentShop.includes('.myshopify.com')) {
                        shop = parentShop;
                        console.log("✅ Shop depuis parent:", shop);
                    }
                }
            } catch(e) {
                console.log("Cannot access parent (CORS)");
            }
        }
    }

    // FIX SESSION
    try {
        if(!shop) shop = sessionStorage.getItem('shop');
        if(shop) sessionStorage.setItem('shop', shop);
    } catch(e) {}

    console.log("🪧 Shop actif:", shop, "| Mode:", mode);

    if (!shop) {
        console.error("❌ ERREUR: Shop introuvable!");
        if (mode !== 'client') {
            alert("Configuration error: Shop not found. Please reload the page.");
        }
    }

    async function getSessionToken() {
        if (window.shopify && window.shopify.id) return await shopify.id.getToken();
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

    if(shop) {
        if (mode === 'client') initClientMode();
        else initAdminMode(shop);
    }

    // --- DASHBOARD ---
    async function initAdminMode(s) {
        const res = await authenticatedFetch(`/api/get-data?shop=${s}`);
        if (res && res.ok) {
            const data = await res.json();

            updateDashboardStats(data.credits || 0);
            updateVIPStatus(data.lifetime || 0);

            const tryEl = document.getElementById('stat-tryons');
            const atcEl = document.getElementById('stat-atc');
            if(tryEl) tryEl.innerText = data.usage || 0;
            if(atcEl) atcEl.innerText = data.atc || 0;

            if(data.widget) {
                document.getElementById('ws-text').value = data.widget.text || "Try It On Now ✨";
                document.getElementById('ws-color').value = data.widget.bg || "#000000";
                document.getElementById('ws-text-color').value = data.widget.color || "#ffffff";
                if(data.security) document.getElementById('ws-limit').value = data.security.max_tries || 5;
                window.updateWidgetPreview();
            }
        }
    }

    function updateDashboardStats(credits) {
        const el = document.getElementById('credits');
        if(el) el.innerText = credits;
        const supplyCard = document.querySelector('.smart-supply-card');
        const alertBadge = document.querySelector('.alert-badge');
        const daysEl = document.querySelector('.rs-value');
        if (supplyCard && daysEl) {
            let daysLeft = Math.floor(credits / 8); 
            if(daysLeft < 1) daysLeft = "< 1";
            daysEl.innerText = daysLeft + (daysLeft === "< 1" ? " Day" : " Days");
            if (credits < 20) {
                supplyCard.style.background = "#fff0f0";
                alertBadge.innerText = "CRITICAL";
                alertBadge.style.background = "#dc2626";
            } else {
                supplyCard.style.background = "#f0fdf4";
                alertBadge.innerText = "HEALTHY";
                alertBadge.style.background = "#16a34a";
            }
        }
    }

    function updateVIPStatus(lifetime) {
        const fill = document.querySelector('.vip-fill');
        const marker = document.querySelector('.vip-marker');
        let percent = (lifetime / 500) * 100;
        if(percent > 100) percent = 100;
        if(fill) fill.style.width = percent + "%";
        if(marker) marker.style.left = percent + "%";
        if(lifetime >= 500) {
            const title = document.querySelector('.vip-title strong');
            if(title) title.innerText = "Gold Member";
        }
    }

    // --- SAVE SETTINGS ---
    window.saveSettings = async function(btn) {
        const oldText = btn.innerText;
        btn.innerText = "Saving..."; 
        btn.disabled = true;
        const settings = {
            shop: shop,
            text: document.getElementById('ws-text').value,
            bg: document.getElementById('ws-color').value,
            color: document.getElementById('ws-text-color').value,
            max_tries: parseInt(document.getElementById('ws-limit').value) || 5
        };
        try {
            const res = await authenticatedFetch('/api/save-settings', {
                method: 'POST', 
                headers: {'Content-Type': 'application/json'}, 
                body: JSON.stringify(settings)
            });
            if(res && res.ok) { 
                btn.innerText = "Saved! ✅"; 
                setTimeout(() => btn.innerText = oldText, 2000); 
            } else { 
                alert("Save failed"); 
            }
        } catch(e) { 
            console.error(e); 
            alert("Error saving"); 
        } finally { 
            btn.disabled = false; 
        }
    };

    // --- TRACK ADD TO CART ---
    window.trackATC = async function() {
        if(shop) {
            try {
                await fetch('/api/track-atc', {
                    method: 'POST', 
                    headers: {'Content-Type': 'application/json'}, 
                    body: JSON.stringify({ shop: shop })
                });
            } catch(e) { 
                console.error("Tracking Error", e); 
            }
        }
    };

    // --- INIT CLIENT MODE ---
    function initClientMode() {
        console.log("🌐 Mode CLIENT activé");
        document.body.classList.add('client-mode');
        const adminZone = document.getElementById('admin-only-zone');
        if(adminZone) adminZone.style.display = 'none';
        
        if (autoProductImage) {
            console.log("📸 Image produit auto:", autoProductImage);
            const img = document.getElementById('prevC');
            if(img) {
                img.src = autoProductImage;
                img.style.display = 'block';
                if(img.parentElement) {
                    const emptyState = img.parentElement.querySelector('.empty-state');
                    if(emptyState) emptyState.style.display = 'none';
                }
            }
        }
    }

    // --- IMAGE PREVIEW ---
    window.preview = function(inputId, imgId) {
        const file = document.getElementById(inputId).files[0];
        if(file) {
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

    // --- UPDATE WIDGET PREVIEW ---
    window.updateWidgetPreview = function() {
        const text = document.getElementById('ws-text').value;
        const color = document.getElementById('ws-color').value;
        const textColor = document.getElementById('ws-text-color').value;
        const btn = document.getElementById('ws-preview-btn');
        if(btn) {
            btn.style.backgroundColor = color;
            btn.style.color = textColor;
            const span = btn.querySelector('span');
            if(span) span.innerText = text;
        }
    }

    // --- GENERATE (VERSION CORRIGÉE) ---
    window.generate = async function() {
        console.log("🚀 ========== DÉBUT GÉNÉRATION ==========");
        console.log("   📍 Shop:", shop);
        console.log("   📍 Mode:", mode);
        
        // VALIDATION SHOP
        if (!shop) {
            console.error("❌ SHOP MANQUANT - ARRÊT");
            alert("Configuration error: Shop information missing. Please contact support.");
            return;
        }
        
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        console.log("📂 Fichiers détectés:");
        console.log("   - Photo utilisateur:", uFile ? uFile.name : "MANQUANT");
        console.log("   - Vêtement (fichier):", cFile ? cFile.name : "non fourni");
        console.log("   - Vêtement (URL):", autoProductImage || "non fourni");
        
        if (!uFile) {
            alert("Please upload your photo.");
            return;
        }
        
        if (!autoProductImage && !cFile) {
            alert("Please upload a garment.");
            return;
        }

        const oldText = btn.innerHTML;
        btn.disabled = true; 
        btn.innerHTML = "Generating...";

        document.getElementById('resZone').style.display = 'block';
        document.getElementById('loader').style.display = 'block';
        document.getElementById('resImg').style.display = 'none';
        document.getElementById('post-actions').style.display = 'none';

        const textEl = document.getElementById('loader-text');
        const texts = [
            "Analyzing silhouette...", 
            "Matching fabrics...", 
            "Simulating drape...", 
            "Rendering lighting..."
        ];
        let step = 0;
        const interval = setInterval(() => { 
            if(step < texts.length) textEl.innerText = texts[step++]; 
        }, 2500);

        try {
            const formData = new FormData();
            
            console.log("📦 Construction FormData...");
            formData.append("shop", shop);
            formData.append("person_image", uFile);
            formData.append("category", "upper_body");
            
            if(cFile) {
                formData.append("clothing_file", cFile);
                console.log("   ✅ Fichier vêtement ajouté");
            } else if (autoProductImage) {
                formData.append("clothing_url", autoProductImage);
                console.log("   ✅ URL vêtement ajoutée:", autoProductImage);
            }
            
            // DEBUG: Afficher le contenu du FormData
            console.log("📋 Contenu FormData:");
            for (let pair of formData.entries()) {
                if (pair[1] instanceof File) {
                    console.log(`   - ${pair[0]}: [File] ${pair[1].name} (${pair[1].size} bytes)`);
                } else {
                    console.log(`   - ${pair[0]}: ${pair[1]}`);
                }
            }

            // URL selon le mode
            const apiUrl = mode === 'client' 
                ? 'https://stylelab-vtonn.onrender.com/api/generate'
                : '/api/generate';
            
            console.log("🎯 URL cible:", apiUrl);
            console.log("📤 Envoi de la requête POST...");
            
            const fetchStartTime = Date.now();
            
            // FETCH STANDARD
            const res = await fetch(apiUrl, {
                method: 'POST',
                body: formData
                // Pas de headers, laisse le navigateur gérer Content-Type
            });
            
            const fetchDuration = Date.now() - fetchStartTime;
            console.log(`📡 Réponse reçue en ${fetchDuration}ms`);
            console.log("   - Status:", res.status);
            console.log("   - Status Text:", res.statusText);
            console.log("   - Headers:", Object.fromEntries(res.headers.entries()));

            clearInterval(interval);

            if (!res) {
                console.error("❌ Pas de réponse du serveur");
                document.getElementById('loader').style.display = 'none';
                alert("Network error: No response from server");
                return;
            }
            
            if (res.status === 429) { 
                console.warn("⚠️ Rate limit atteint");
                alert("Daily limit reached. Please try again tomorrow."); 
                document.getElementById('loader').style.display = 'none'; 
                return; 
            }
            
            if (res.status === 402) { 
                console.warn("⚠️ Crédits insuffisants");
                alert("This shop has run out of credits!"); 
                btn.disabled = false; 
                btn.innerHTML = oldText; 
                document.getElementById('loader').style.display = 'none';
                return; 
            }
            
            if (!res.ok) {
                const errorText = await res.text();
                console.error("❌ Erreur serveur:", errorText);
                
                try {
                    const errorData = JSON.parse(errorText);
                    throw new Error(errorData.error || "Server Error");
                } catch(e) {
                    throw new Error(`Server Error (${res.status}): ${errorText.substring(0, 200)}`);
                }
            }

            console.log("📥 Parsing de la réponse JSON...");
            const data = await res.json();
            console.log("✅ Données reçues:", data);
            
            if(data.result_image_url){
                console.log("🖼️ Chargement de l'image:", data.result_image_url);
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => { 
                    ri.style.display = 'block'; 
                    document.getElementById('loader').style.display = 'none'; 
                    document.getElementById('post-actions').style.display = 'block';
                    console.log("✅ ========== IMAGE AFFICHÉE ==========");
                };
                ri.onerror = () => {
                    console.error("❌ Erreur chargement image:", data.result_image_url);
                    alert("Error loading result image");
                    document.getElementById('loader').style.display = 'none';
                };
            } else { 
                console.error("❌ Pas d'URL d'image dans la réponse");
                alert("Error: " + (data.error || "No image URL received")); 
                document.getElementById('loader').style.display = 'none'; 
            }
        } catch(e) { 
            clearInterval(interval); 
            console.error("❌ ========== EXCEPTION ==========");
            console.error("Type:", e.name);
            console.error("Message:", e.message);
            console.error("Stack:", e.stack);
            alert("Error: " + e.message); 
            document.getElementById('loader').style.display = 'none'; 
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldText; 
            console.log("🏁 ========== FIN GÉNÉRATION ==========");
        }
    };

    // --- BUY CREDITS (PACKS) ---
    window.buy = async function(packId, customAmount, btnElement) {
        if(!shop) return alert("Shop not detected!");
        
        const originalContent = btnElement.innerHTML;
        btnElement.innerHTML = "Processing...";
        btnElement.disabled = true;

        try {
            const payload = {
                shop: shop,
                pack_id: packId,
                custom_amount: customAmount || 0
            };

            const res = await authenticatedFetch('/api/buy-credits', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });

            if(res && res.ok) {
                const data = await res.json();
                if(data.confirmation_url) {
                    window.top.location.href = data.confirmation_url;
                } else {
                    alert("Error: No confirmation URL received");
                }
            } else {
                const errorData = await res.json().catch(() => ({}));
                alert("Purchase failed: " + (errorData.error || "Unknown error"));
            }
        } catch(e) {
            console.error("Buy Error:", e);
            alert("Network error during purchase");
        } finally {
            btnElement.innerHTML = originalContent;
            btnElement.disabled = false;
        }
    };

    // --- BUY CUSTOM AMOUNT ---
    window.buyCustom = async function(btn) {
        const customAmountInput = document.getElementById('customAmount');
        const amount = parseInt(customAmountInput.value);

        if(!amount || amount < 10) {
            return alert("Please enter at least 10 credits");
        }

        if(amount > 10000) {
            return alert("Maximum 10,000 credits per order. Contact support for larger volumes.");
        }

        const originalText = btn.innerHTML;
        btn.innerHTML = "Processing...";
        btn.disabled = true;

        try {
            const payload = {
                shop: shop,
                pack_id: 'pack_custom',
                custom_amount: amount
            };

            const res = await authenticatedFetch('/api/buy-credits', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });

            if(res && res.ok) {
                const data = await res.json();
                if(data.confirmation_url) {
                    window.top.location.href = data.confirmation_url;
                } else {
                    alert("Error: No confirmation URL received");
                }
            } else {
                const errorData = await res.json().catch(() => ({}));
                alert("Purchase failed: " + (errorData.error || "Unknown error"));
            }
        } catch(e) {
            console.error("Custom Buy Error:", e);
            alert("Network error during purchase");
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    };

});
