document.addEventListener("DOMContentLoaded", async () => {
    document.body.classList.add("loaded");

    const params = new URLSearchParams(window.location.search);
    const shop = params.get("shop");
    const token = params.get("token");

    if(!shop || !token){
        document.body.innerHTML="<h1>Erreur : App non authentifiée ou Shop manquant</h1>";
        return;
    }

    async function fetchCredits(){
        const res = await fetch(`/api/get-credits?shop=${shop}&token=${token}`);
        const data = await res.json();
        document.getElementById("credits").innerText = data.credits || 0;
    }
    fetchCredits();

    window.buy = async function(event, packId){
        event.preventDefault();
        const btn = event.currentTarget;
        const oldText = btn.innerText;
        btn.innerText = "Redirecting...";
        btn.disabled = true;
        try{
            const res = await fetch("/api/buy-credits",{
                method:"POST",
                headers:{"Content-Type":"application/json"},
                body: JSON.stringify({shop, token, pack_id: packId})
            });
            const data = await res.json();
            if(data.confirmation_url) window.top.location.href = data.confirmation_url;
            else throw new Error(data.error || "Unknown error");
        }catch(e){
            console.error(e);
            btn.innerText = oldText;
            btn.disabled = false;
            alert("Erreur achat pack");
        }
    };

    window.buyCustom = async function(){
        const amount = parseInt(document.getElementById("customAmount").value);
        if(isNaN(amount) || amount < 200) return alert("Montant min 200");
        const res = await fetch("/api/buy-custom",{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body: JSON.stringify({shop, token, amount})
        });
        const data = await res.json();
        if(data.confirmation_url) window.top.location.href = data.confirmation_url;
        else alert("Erreur custom pack");
    };

    // Preview upload
    window.preview = function(inputId,imgId,txtId){
        const file = document.getElementById(inputId).files[0];
        if(!file) return;
        const reader = new FileReader();
        reader.onload = e => {
            const img = document.getElementById(imgId);
            const txt = document.getElementById(txtId);
            img.src = e.target.result;
            img.style.display = "block";
            txt.style.display = "none";
            document.getElementById(inputId).parentElement.classList.add("has-image");
        }
        reader.readAsDataURL(file);
    }

    // Virtual Try-On
    window.generate = async function(){
        const userFile = document.getElementById("uImg").files[0];
        const garmentFile = document.getElementById("cImg").files[0];
        if(!userFile || !garmentFile){alert("Upload both images"); return;}
        const btn = document.getElementById("btnGo");
        btn.disabled = true; btn.innerText="Processing...";
        const formData = new FormData();
        formData.append("user_image", userFile);
        formData.append("garment_image", garmentFile);
        try{
            const res = await fetch("/api/generate-tryon",{method:"POST", body: formData});
            if(!res.ok) throw new Error("AI generation failed");
            const data = await res.json();
            document.getElementById("resImg").src = data.generated_image_url;
            document.getElementById("resZone").style.display="block";
            document.getElementById("loader").style.display="none";
            btn.innerText="Test This Outfit Now ✨"; btn.disabled=false;
        }catch(err){console.error(err); alert("Error generating try-on"); btn.innerText="Test This Outfit Now ✨"; btn.disabled=false;}
    }
});
