/* APP.JS - Cerveau du Frontend
    Gère l'interface, les uploads, et la communication avec Python/Render
*/

document.addEventListener("DOMContentLoaded", () => {
    // 1. Détection du mode (Client vs Admin)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('mode') === 'client') {
        document.body.classList.add('client-mode');
    }

    // 2. Initialisation des données (si on n'est pas en mode client strict)
    if (!document.body.classList.contains('client-mode')) {
        fetchStats();
        // Initialiser la prévisualisation du widget (couleurs, texte)
        updateWidgetPreview();
    }
});

/* =========================================
   LOGIQUE UTILISATEUR (TRY-ON)
   ========================================= */

// Fonction pour prévisualiser les images uploadées (Photo ou Vêtement)
function preview(inputId, imgId) {
    const input = document.getElementById(inputId);
    const img = document.getElementById(imgId);
    const label = input.parentElement; // Le cadre pointillé
    
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        
        reader.onload = function(e) {
            img.src = e.target.result;
            img.style.display = 'block';
            
            // Cacher l'icône et le texte "Empty state"
            const emptyState = label.querySelector('.empty-state');
            if (emptyState) emptyState.style.display = 'none';
        }
        
        reader.readAsDataURL(input.files[0]);
    }
}

// C'est la fonction principale qui lance l'IA
async function generate() {
    // Récupération des éléments du DOM
    const uInput = document.getElementById('uImg');
    const cInput = document.getElementById('cImg');
    const resultZone = document.getElementById('resZone');
    const loader = document.getElementById('loader');
    const loaderText = document.getElementById('loader-text');
    const resImg = document.getElementById('resImg');
    const btnGo = document.getElementById('btnGo');
    const postActions = document.getElementById('post-actions');

    // 1. Validation : Est-ce que les 2 images sont là ?
    if (!uInput.files[0] || !cInput.files[0]) {
        alert("Oups ! Merci d'ajouter votre photo ET la photo du vêtement.");
        return;
    }

    // 2. UI : Passage en mode "Chargement"
    btnGo.disabled = true;
    btnGo.style.opacity = "0.6";
    btnGo.innerHTML = '<span class="btn-content">Transformation en cours... <i class="fa-solid fa-spinner fa-spin"></i></span>';
    
    resultZone.style.display = "block";
    loader.style.display = "block";
    resImg.style.display = "none";
    postActions.style.display = "none";
    
    // Scroller doucement vers la zone de résultat
    resultZone.scrollIntoView({behavior: 'smooth', block: 'center'});

    // 3. Préparation de l'envoi vers Render
    const formData = new FormData();
    formData.append('human_img', uInput.files[0]);
    formData.append('cloth_img', cInput.files[0]);

    try {
        // Message d'attente pour faire patienter (l'IA prend ~15-30 sec)
        let dots = 0;
        const loadingInterval = setInterval(() => {
            dots = (dots + 1) % 4;
            const states = [
                "Analyse de la silhouette...",
                "Démarrage du GPU...",
                "Fusion du vêtement...",
                "Finalisation du rendu..."
            ];
            loaderText.innerText = states[dots];
        }, 4000);

        // --- APPEL AU SERVEUR PYTHON ---
        const response = await fetch('/generate', {
            method: 'POST',
            body: formData
        });

        clearInterval(loadingInterval);
        const data = await response.json();

        if (response.ok) {
            // --- SUCCÈS ---
            console.log("Image générée :", data.result_url);

            // Afficher l'image
            resImg.onload = () => {
                // On n'affiche le résultat que quand l'image est totalement chargée
                loader.style.display = "none";
                resImg.style.display = "block";
                resImg.classList.add('fade-in'); // Animation CSS si vous voulez
                postActions.style.display = "block";
                
                // Remettre le bouton normal
                resetButton(btnGo);
            };
            resImg.src = data.result_url;
            
            // Mettre à jour les crédits si on est admin
            if(document.getElementById('credits')) {
                document.getElementById('credits').innerText = data.credits_remaining;
            }
            
            // Incrémenter le compteur local "Total Try-Ons"
            incrementStat('stat-tryons');
            
        } else {
            // --- ERREUR DU SERVEUR ---
            throw new Error(data.error || "Erreur inconnue");
        }

    } catch (error) {
        console.error("Erreur:", error);
        loader.style.display = "none";
        alert("Erreur lors de la génération : " + error.message);
        resetButton(btnGo);
    }
}

function resetButton(btn) {
    btn.disabled = false;
    btn.style.opacity = "1";
    btn.innerHTML = '<span class="btn-content">Try It On Now <i class="fa-solid fa-wand-magic-sparkles"></i></span><div class="btn-glow"></div>';
}

function trackATC() {
    // Simulation d'un ajout au panier
    const btn = document.getElementById('shopBtn');
    btn.innerHTML = 'Added <i class="fa-solid fa-check"></i>';
    btn.style.background = "#22c55e";
    
    incrementStat('stat-atc');
    
    setTimeout(() => {
        alert("Super ! Produit ajouté au panier (Simulation).");
        btn.innerHTML = 'Shop This Look <i class="fa-solid fa-bag-shopping"></i>';
        btn.style.background = "#000";
    }, 1000);
}


/* =========================================
   LOGIQUE DASHBOARD (ADMIN)
   ========================================= */

function fetchStats() {
    fetch('/api/stats')
        .then(res => res.json())
        .then(data => {
            if(document.getElementById('credits')) {
                document.getElementById('credits').innerText = data.credits;
            }
            // Charger les réglages existants
            if(data.settings) {
                if(document.getElementById('ws-text')) document.getElementById('ws-text').value = data.settings.button_text;
                if(document.getElementById('ws-color')) document.getElementById('ws-color').value = data.settings.button_color;
                if(document.getElementById('ws-text-color')) document.getElementById('ws-text-color').value = data.settings.text_color;
                if(document.getElementById('ws-limit')) document.getElementById('ws-limit').value = data.settings.limit;
                
                updateWidgetPreview();
            }
        })
        .catch(err => console.log("Pas de stats (mode offline ?)"));
}

// Met à jour le faux bouton "Try On" dans le Dashboard quand on change les inputs
function updateWidgetPreview() {
    const textInput = document.getElementById('ws-text');
    if(!textInput) return; // Sécurité si l'élément n'existe pas

    const text = textInput.value;
    const bg = document.getElementById('ws-color').value;
    const ink = document.getElementById('ws-text-color').value;
    
    const btn = document.getElementById('ws-preview-btn');
    if(btn) {
        // On cherche le span à l'intérieur pour garder l'icône
        const span = btn.querySelector('span');
        if(span) span.innerText = text;
        
        btn.style.backgroundColor = bg;
        btn.style.color = ink;
    }
}

function saveSettings(btn) {
    const oldText = btn.innerText;
    btn.innerText = "Saving...";
    btn.disabled = true;
    
    const settings = {
        button_text: document.getElementById('ws-text').value,
        button_color: document.getElementById('ws-color').value,
        text_color: document.getElementById('ws-text-color').value,
        limit: document.getElementById('ws-limit').value
    };

    fetch('/api/save-settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(settings)
    })
    .then(res => res.json())
    .then(data => {
        setTimeout(() => {
            btn.innerText = "Saved!";
            btn.style.background = "#22c55e";
            setTimeout(() => {
                btn.innerText = oldText;
                btn.style.background = ""; // Retour couleur CSS
                btn.disabled = false;
            }, 2000);
        }, 500);
    });
}

// Fonction d'achat de crédits (Simulation)
function buy(packId, customAmount = 0, cardElement) {
    let amount = 0;
    if(packId === 'pack_10') amount = 10;
    if(packId === 'pack_30') amount = 30;
    if(packId === 'pack_100') amount = 100;
    if(customAmount > 0) amount = parseInt(customAmount);

    if(amount <= 0) return;

    // Animation "Click"
    if(cardElement) {
        cardElement.style.transform = "scale(0.95)";
        setTimeout(() => cardElement.style.transform = "", 150);
    }

    fetch('/api/buy-credits', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ amount: amount })
    })
    .then(res => res.json())
    .then(data => {
        document.getElementById('credits').innerText = data.new_balance;
        alert(`Succès ! ${amount} crédits ajoutés à votre compte.`);
    });
}

function buyCustom(btn) {
    const val = document.getElementById('customAmount').value;
    buy('custom', val, btn);
}

// Petite utilitaire pour faire monter les chiffres
function incrementStat(id) {
    const el = document.getElementById(id);
    if(el) {
        let val = parseInt(el.innerText);
        el.innerText = val + 1;
        // Petit effet de couleur
        el.style.color = "#6366f1";
        setTimeout(() => el.style.color = "", 500);
    }
}
