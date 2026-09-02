/**
 * Rendering helpers for the component tests.
 *
 * Every component in this app assumes two providers -- a locale and a router --
 * so the tests mount them the same way the application does rather than
 * stubbing `useI18n`. A test that stubs the provider stops testing the thing
 * `T-110` is about.
 *
 * The providers are passed as Testing Library's `wrapper` rather than wrapped
 * around the element, so `rerender` keeps them: a rerender of a bare element
 * would drop the context and fail for a reason that has nothing to do with
 * the component under test.
 */

import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import { I18nProvider, type Locale } from "../i18n";

export function renderApp(
  element: ReactElement,
  options: { locale?: Locale; route?: string } = {},
): RenderResult {
  const locale = options.locale ?? "en";
  const route = options.route ?? "/";
  function Providers({ children }: { children: ReactNode }) {
    return (
      <I18nProvider initialLocale={locale}>
        <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
      </I18nProvider>
    );
  }
  return render(element, { wrapper: Providers });
}

/** A `fetch` that answers a fixed JSON body, for a test that must not hit a server. */
export function jsonFetch(
  responder: (url: string) => { status?: number; body: unknown },
): typeof fetch {
  return (async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    const { status = 200, body } = responder(url);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
}
