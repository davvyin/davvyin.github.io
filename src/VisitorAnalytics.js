import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

const publicPaths = new Set(["/", "/about", "/projects", "/technologies", "/contact"]);

function eventId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  // This is a deduplication ID, not a credential or persistent visitor identity.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (letter) => {
    const random = Math.floor(Math.random() * 16);
    return (letter === "x" ? random : (random & 3) | 8).toString(16);
  });
}

export default function VisitorAnalytics() {
  const { pathname } = useLocation();
  const lastPath = useRef(null);
  useEffect(() => {
    const path = pathname.replace(/\/+$/, "") || "/";
    if (!publicPaths.has(path) || lastPath.current === path) return;
    const initial = lastPath.current === null;
    lastPath.current = path; // Also prevents React StrictMode's repeated effect.
    if (process.env.REACT_APP_ANALYTICS_ENABLED === "false" ||
        navigator.doNotTrack === "1" || window.doNotTrack === "1" ||
        navigator.globalPrivacyControl === true) return;
    let referrer = "";
    if (initial && document.referrer) {
      try { referrer = new URL(document.referrer).origin; } catch (_) { /* No referrer. */ }
    }
    // No analytics cookies, local storage, query strings, or cross-site service.
    // Existing same-origin sessions let Django exclude signed-in staff.
    try {
      fetch("/api/analytics/pageview/", {
        method: "POST", credentials: "same-origin", keepalive: true,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_id: eventId(), path, referrer }),
      }).catch(() => {}); // An analytics outage must not interrupt navigation.
    } catch (_) { /* Ignore unavailable fetch in restricted browsers. */ }
  }, [pathname]);
  return null;
}
