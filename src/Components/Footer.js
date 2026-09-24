import React from "react";
import { useContent } from "../ContentContext";

function Footer() {
  const { footerText, siteCopy } = useContent();
  return (
    <footer className="container mx-auto py-1 fixed bottom-0 md:left-20 bg-white dark:bg-dark-mode">
      <p className="text-xs text-center text-dark-content dark:text-light-content w-full">
        {footerText}
        <a className="ml-4 underline" href="/admin/">{siteCopy.footer_admin_label}</a>
      </p>
    </footer>
  );
}
export default Footer;
