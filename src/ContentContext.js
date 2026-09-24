import React, { createContext, useContext, useEffect, useState } from "react";

const ContentContext = createContext(null);

function validContent(data) {
  return data && data.personalDetails && data.logos && data.contactDetails &&
    data.socialMediaUrl && typeof data.footerText === "string" &&
    data.siteCopy && typeof data.siteCopy === "object" &&
    ["workDetails", "eduDetails", "projectDetails", "technologies"].every(
      (key) => Array.isArray(data[key])
    );
}

export function ContentProvider({ children }) {
  const [content, setContent] = useState(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setError(false);
    const timeout = setTimeout(() => controller.abort(), 10000);
    async function load() {
      try {
        const response = await fetch("/api/content/", { signal: controller.signal });
        if (!response.ok) throw new Error("Content request failed");
        const data = await response.json();
        if (!validContent(data)) throw new Error("Invalid site content");
        if (active) setContent(data);
      } catch (err) {
        if (active) setError(true);
      } finally {
        clearTimeout(timeout);
      }
    }
    load();
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [attempt]);

  if (error) {
    return (
      <main className="container mx-auto max-width section text-content" role="alert">
        <p>The site could not load. Please try again.</p>
        <button className="underline mt-4" onClick={() => setAttempt((value) => value + 1)}>
          Try again
        </button>
      </main>
    );
  }
  if (!content) {
    return <main className="container mx-auto max-width section text-content" role="status">Loading…</main>;
  }
  return <ContentContext.Provider value={content}>{children}</ContentContext.Provider>;
}

export function useContent() {
  return useContext(ContentContext);
}
