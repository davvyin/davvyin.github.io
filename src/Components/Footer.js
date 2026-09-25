import React from "react";
import { useContent } from "../ContentContext";

function Footer() {
  const { footerText, siteCopy } = useContent();
  const adminHref = process.env.NODE_ENV === "development"
    ? "/admin/"
    : "http://10.66.66.1:8080/admin/";
  return (
    <footer className="container mx-auto py-1 fixed bottom-0 md:left-20 bg-white dark:bg-dark-mode">
      <p className="text-xs text-center text-dark-content dark:text-light-content w-full">
        {footerText}
        <a
          className="ml-4 underline"
          href={adminHref}
          aria-label={`${siteCopy.footer_admin_label} (VPN required)`}
          title="Requires an active WireGuard VPN connection"
        >
          {siteCopy.footer_admin_label} <span aria-hidden="true">(VPN)</span>
        </a>
      </p>
    </footer>
  );
}
export default Footer;
