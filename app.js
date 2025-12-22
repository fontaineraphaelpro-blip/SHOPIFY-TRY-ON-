document.addEventListener("DOMContentLoaded", function() {
    
    // 1. DETECTER LE MODE CLIENT
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');

    if (mode === 'client') {
        // Active le mode client dans le CSS
        document.body.classList.add('client-mode');
        console.log("Mode Client Activé : Admin masqué");
    }

    // 2. LOGIQUE PREVIEW
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

    // 3. LOGIQUE GENERATION
    window.generate = async function() {
        const u = document.getElementById('uImg').files[0];
        const c = document.getElementById('cImg').files[0];
        
        if (!u || !c) return alert("Mettez les 2 photos !");

        const btn = document.querySelector('button');
        btn.disabled = true;
        btn.innerText = "Génération...";

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
                    shop: params.get('shop') || "demo",
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
});
