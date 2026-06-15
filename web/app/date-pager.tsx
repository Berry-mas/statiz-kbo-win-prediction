"use client";

import { ReactNode, useMemo, useState } from "react";

export type DatePagerPage = {
  key: string;
  label: string;
  detail: string;
  itemCount: number;
  content: ReactNode;
};

type DatePagerProps = {
  ariaLabel: string;
  pages: DatePagerPage[];
};

export function DatePager({ ariaLabel, pages }: DatePagerProps) {
  const [pageIndex, setPageIndex] = useState(0);
  const activePageIndex = Math.min(pageIndex, Math.max(pages.length - 1, 0));
  const activePage = pages[activePageIndex];
  const pageSummary = useMemo(() => {
    if (!activePage) {
      return "";
    }
    return `${activePage.label} · ${activePage.detail}`;
  }, [activePage]);

  if (!activePage) {
    return null;
  }

  const hasMultiplePages = pages.length > 1;

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
