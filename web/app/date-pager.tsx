"use client";

import { ReactNode, useState } from "react";

export type DatePagerPage = {
  key: string;
  label: string;
  detail: string;
  content: ReactNode;
};

type DatePagerProps = {
  ariaLabel: string;
  pages: DatePagerPage[];
};

export function DatePager({ ariaLabel, pages }: DatePagerProps) {
  const [pageIndex, setPageIndex] = useState(Math.max(pages.length - 1, 0));
  const activePageIndex = Math.min(pageIndex, Math.max(pages.length - 1, 0));
  const activePage = pages[activePageIndex];

  if (!activePage) {
    return null;
  }

  const hasMultiplePages = pages.length > 1;
  const pageSummary = `${activePage.label} · ${activePage.detail}`;

  return (
    <div className="date-pager" aria-label={ariaLabel}>
      <div className="date-pager-bar">
        <div className="date-pager-current">
          <strong>{activePage.label}</strong>
          <span>{activePage.detail}</span>
        </div>
        {hasMultiplePages ? (
          <div className="date-pager-controls" aria-label={pageSummary}>
            <button
              aria-label="Previous date"
              disabled={activePageIndex === 0}
              onClick={() => setPageIndex((current) => Math.max(current - 1, 0))}
              type="button"
            >
              Prev
            </button>
            <span>
              {activePageIndex + 1}/{pages.length}
            </span>
            <button
              aria-label="Next date"
              disabled={activePageIndex === pages.length - 1}
              onClick={() => setPageIndex((current) => Math.min(current + 1, pages.length - 1))}
              type="button"
            >
              Next
            </button>
          </div>
        ) : null}
      </div>
      {activePage.content}
    </div>
  );
}
