"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

type Language = "en" | "ko";

const STORAGE_KEY = "statiz-dashboard-language";

export function LanguageToggle() {
  const pathname = usePathname();
  const [language, setLanguage] = useState<Language>("en");

  useEffect(() => {
    const savedLanguage = readSavedLanguage();
    applyLanguage(savedLanguage);
    setLanguage(savedLanguage);
  }, []);

  useEffect(() => {
    applyLanguage(language);
  }, [language, pathname]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    let animationFrame = 0;
    const observer = new MutationObserver(() => {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(() => {
        observer.disconnect();
        applyLanguage(readSavedLanguage());
        observer.observe(document.body, { childList: true, subtree: true });
      });
    });

    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      window.cancelAnimationFrame(animationFrame);
      observer.disconnect();
    };
  }, []);

  function toggleLanguage(): void {
    const nextLanguage = language === "en" ? "ko" : "en";
    applyLanguage(nextLanguage);
    window.localStorage.setItem(STORAGE_KEY, nextLanguage);
    setLanguage(nextLanguage);
  }

  return (
    <button
      aria-label="Toggle language"
      className="language-toggle"
      onClick={toggleLanguage}
      type="button"
    >
      <span>{language === "en" ? "한국어" : "English"}</span>
    </button>
  );
}

function readSavedLanguage(): Language {
  if (typeof window === "undefined") {
    return "en";
  }
  return window.localStorage.getItem(STORAGE_KEY) === "ko" ? "ko" : "en";
}

function applyLanguage(language: Language): void {
  document.documentElement.lang = language;
  document.documentElement.dataset.language = language;

  const elements = document.querySelectorAll<HTMLElement>("[data-en][data-ko]");
  for (const element of elements) {
    const nextText = language === "en" ? element.dataset.en : element.dataset.ko;
    if (nextText) {
      element.textContent = nextText;
    }
  }
}
