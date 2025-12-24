let app;
let getSessionToken;
let shop;

document.addEventListener("DOMContentLoaded", async () => {
    const params = new URLSearchParams(window.location.search);
    shop = params.get("shop");

    app = window["app-bridge"].createApp({
        apiKey: "TON_API_KEY_SHOPIFY",
        shopOrigin: shop,
        forceRedirect: true
    });

    getSessionToken = window["app-bridge-utils"].getSessionToken;

    fetchCredits();
});

async function getToken() {
    return await getSessionToken(app);
}

async function fetchCredits() {
    const token = await getToken();

    const res = await fetch(`/api/get-credits?shop=${shop}`, {
        headers: {
            Authorization: `Bearer ${token}`
        }
    });

    const data = await res.json();
    document.getElementById("credits").innerText = data.credits;
}

window.buy = async function (packId) {
    const token = await getToken();

    const res = await fetch("/api/buy-credits", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
            shop: shop,
            pack_id: packId
        })
    });

    const data = await res.json();

    if (data.confirmation_url) {
        window.top.location.href = data.confirmation_url;
    } else {
        alert("Payment error");
    }
};
