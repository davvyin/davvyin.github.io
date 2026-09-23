const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = function (app) {
  // Preserve the browser Host header so admin redirects stay on port 3000.
  app.use(
    ["/api", "/admin", "/healthz", "/static/admin", "/static/portfolio"],
    createProxyMiddleware({ target: "http://127.0.0.1:8000", changeOrigin: false })
  );
};
