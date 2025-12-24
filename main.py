<!DOCTYPE html>
<html>
<head>
  <script src="https://unpkg.com/@shopify/app-bridge@3"></script>
</head>
<body>
  <h1>APP OK</h1>

  <script>
    const params = new URLSearchParams(window.location.search);
    const shop = params.get("shop");

    if (!shop) {
      document.body.innerHTML = "NO SHOP PARAM";
      throw new Error("No shop");
    }

    const app = window['app-bridge'].default({
      apiKey: "TON_API_KEY",
      shopOrigin: shop,
      forceRedirect: true
    });

    console.log("App Bridge OK");
  </script>
</body>
</html>
