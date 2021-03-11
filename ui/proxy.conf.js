module.exports = {
  "/api": {
      target: "http://localhost:8080",
      changeOrigin: true,
      logLevel: "debug",
      secure: false,
      /*
      onProxyReq: function (proxyReq, req, res) {
          console.log('req.headers=' + JSON.stringify(req.headers, true, 2));
          console.log('proxyReq.headers=' + JSON.stringify(proxyReq.headers, true, 2));
      },
      onProxyRes: function (proxyRes, req, res) {
          console.log('res.headers=' + JSON.stringify(res.headers, true, 2));
          console.log('proxyRes.headers=' + JSON.stringify(proxyRes.headers, true, 2));
      },
      onError: function (err, req, res) {
          console.log('Error=' + err + '; req.headers=' + JSON.stringify(req.headers, true, 2));
      }
      */
  }
}