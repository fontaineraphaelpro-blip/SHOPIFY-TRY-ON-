document.addEventListener("DOMContentLoaded", function() {

    document.body.classList.add('loaded');
    document.body.style.opacity = "1";

    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    let shop = params.get('shop') || sessionStorage.getItem('shop');
    const autoProductImage = params.get('product_image');

    // === CORRECTION CRITIQUE MODE CLIENT ===
    // En mode client, si shop n'est pas dans l'URL, on doit le récupérer depuis le parent (Shopify)
    if (mode === 'client' && !shop) {
        console.log("⚠️ Mode client détecté mais shop manquant, tentative de récupération...");
        
        // Essayer de récupérer depuis window.location (si passé en fragment)
        const hash = window.location.hash;
        if (hash.includes('shop=')) {
            const match = hash.match(/shop=([^&]+)/);
            if (match) shop = match[1];
        }
        
        // Si toujours pas trouvé, on doit le récupérer depuis Shopify
        if (!shop && window.Shopify && window.Shopify.shop) {
            shop = window.Shopify.shop;
            console.log("✅ Shop récupéré depuis Shopify.shop:", shop);
        }
        
        // Dernière tentative : parser depuis le domaine parent
        if (!shop) {
            try {
                const parentUrl = document.referrer || window.location.ancestorOrigins?.[0];
                if (parentUrl && parentUrl.includes('.myshopify.com')) {
                    const match = parentUrl.match(/https?:\/\/([^\/]+)/);
                    if (match) shop = match[1];
                    console.log("✅ Shop extrait du referrer:", shop);
                }
            } catch(e) {
                console.error("Impossible d'extraire le shop:", e);
            }
        }
    }

    // FIX SESSION
    try {
        if(!shop) shop = sessionStorage.getItem('shop');
        if(shop) sessionStorage.setItem('shop', shop);
    } catch(e) {}

    console.log("🏪 Shop actif:", shop, "| Mode:", mode);

    // Si shop manquant après tous les essais
    if (!shop) {
        console.error("❌ ERREUR CRITIQUE : Shop introuvable !");
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

            // Affichage Stats
            updateDashboardStats(data.credits || 0);
            updateVIPStatus(data.lifetime || 0);

            // Compteurs simples
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
        console.log("🌐 Initialisation mode CLIENT");
        document.body.classList.add('client-mode');
        const adminZone = document.getElementById('admin-only-zone');
        if(adminZone) adminZone.style.display = 'none';
        
        if (autoProductImage) {
            console.log("📸 Image produit auto-chargée:", autoProductImage);
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

    // --- GENERATE VIRTUAL TRY-ON ---
    window.generate = async function() {
        console.log("🚀 Début de la génération...");
        console.log("   - Shop:", shop);
        console.log("   - Mode:", mode);
        
        const uFile = document.getElementById('uImg').files[0];
        const cFile = document.getElementById('cImg').files[0];
        const btn = document.getElementById('btnGo');
        
        // VALIDATION CRITIQUE
        if (!shop) {
            console.error("❌ SHOP MANQUANT !");
            alert("Configuration error: Shop not found. Please contact support.");
            return;
        }
        
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
            formData.append("shop", shop); // LE SHOP DOIT ÊTRE LÀ !
            formData.append("person_image", uFile);
            
            if(cFile) {
                formData.append("clothing_file", cFile);
                console.log("👕 Fichier vêtement ajouté");
            } else {
                formData.append("clothing_url", autoProductImage);
                console.log("🔗 URL vêtement:", autoProductImage);
            }
            
            formData.append("category", "upper_body");

            let res;
            // Utiliser la route publique pour les clients
            if (mode === 'client') {
                console.log("🌐 Mode CLIENT : Appel /api/generate-public");
                console.log("   - Endpoint:", window.location.origin + '/api/generate-public');
                
                res = await fetch('/api/generate-public', { 
                    method: 'POST', 
                    body: formData 
                });
                
                console.log("📡 Réponse reçue, status:", res.status);
            } else {
                console.log("🔒 Mode ADMIN : Appel /api/generate");
                res = await authenticatedFetch('/api/generate', { 
                    method: 'POST', 
                    body: formData 
                });
            }

            clearInterval(interval);

            if (!res) {
                console.error("❌ Pas de réponse du serveur");
                document.getElementById('loader').style.display = 'none';
                alert("Network error: No response from server");
                return;
            }
            
            console.log("📊 Status HTTP:", res.status);
            
            if (res.status === 429) { 
                alert("Daily limit reached. Please try again tomorrow."); 
                document.getElementById('loader').style.display = 'none'; 
                return; 
            }
            
            if (res.status === 402) { 
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
                    throw new Error(`Server Error (${res.status}): ${errorText.substring(0, 100)}`);
                }
            }

            const data = await res.json();
            console.log("✅ Données reçues:", data);
            
            if(data.result_image_url){
                const ri = document.getElementById('resImg');
                ri.src = data.result_image_url;
                ri.onload = () => { 
                    ri.style.display = 'block'; 
                    document.getElementById('loader').style.display = 'none'; 
                    document.getElementById('post-actions').style.display = 'block';
                    console.log("✅ Image affichée avec succès");
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
            console.error("❌ Exception Generate:", e); 
            alert("Error: " + e.message); 
            document.getElementById('loader').style.display = 'none'; 
        } finally { 
            btn.disabled = false; 
            btn.innerHTML = oldText; 
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
