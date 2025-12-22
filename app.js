document.addEventListener("DOMContentLoaded", function() {
    
    // 1. DETECTION : EST-CE LE CLIENT ?
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode'); // Récupère ?mode=client
    const shop = params.get('shop');

    // On affiche le corps de la page maintenant que le JS est chargé
    document.body.style.display = 'block';

    if (mode === 'client') {
        // C'est le client : on ajoute la classe qui déclenche le CSS "Cache-Cache"
        document.body.classList.add('client-mode');
        console.log("Mode Client Activé");
    } else {
        // C'est l'admin : on charge les crédits
        if(shop) fetchCredits(shop);
    }

    // 2. PREVISUALISATION IMAGES
    window.preview = function(input, imgId) {
        const file = input.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = e => {
                const img = document.getElementById(imgId);
                img.src = e.target.result;
                img.style.display = 'block';
            };
            reader.readAsDataURL(file);
        }
    };

    // 3. GENERATION IA
    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const c = document.getElementById('cImg').files[0];
        
        if (!u || !c) return alert("Ajoutez les 2 photos !");

        const btn = document.querySelector('button');
        btn.disabled = true;
        btn.innerText = "Génération...";

        // Helper pour convertir en base64
        const toBase64 = file => new Promise(r => {
            const reader = new FileReader();
            reader.readAsDataURL(file);
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
                const resImg = document.getElementById('resImg');
                resImg.src = data.result_image_url;
                resImg.style.display = 'block';
            } else {
                alert("Erreur: " + JSON.stringify(data));
            }
        } catch(e) {
            alert("Erreur technique");
        } finally {
            btn.disabled = false;
            btn.innerText = "Générer";
        }
    };

    async function fetchCredits(shop) {
        try {
            const res = await fetch(`/api/get-credits?shop=${shop}`);
            const data = await res.json();
            document.getElementById('credits').innerText = data.credits;
        } catch(e) { console.error(e); }
    }
    
    window.buy = function() {
        alert("Paiement désactivé pour ce test");
    }
});
