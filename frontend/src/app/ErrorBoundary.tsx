import { Component, type ErrorInfo, type ReactNode } from "react";
import { useLocale } from "@/i18n/context";

/**
 * A last line of defence against a white screen. An uncaught error during
 * render unmounts the whole tree to a blank page; this boundary catches it and
 * shows a localized, reloadable fallback instead.
 *
 * It is mounted inside <LocaleProvider> (see main.tsx → App), so the fallback
 * may read translations through useLocale. The fallback is a function component
 * because the boundary itself must be a class (getDerivedStateFromError /
 * componentDidCatch have no hook equivalent), and a class cannot call hooks.
 */
function ErrorFallback() {
  const { t } = useLocale();
  return (
    <div
      role="alert"
      data-testid="error-boundary"
      className="flex min-h-screen flex-col items-center justify-center bg-leovee-surface p-8"
    >
      <section className="w-full max-w-md rounded-lg border border-slate-800 bg-leovee-panel p-8 text-center">
        <h1 className="text-2xl font-semibold text-foreground">
          {t("common.errorBoundary.title")}
        </h1>
        <p className="mt-2 text-muted-foreground">
          {t("common.errorBoundary.description")}
        </p>
        <button
          type="button"
          data-testid="error-boundary-reload"
          onClick={() => window.location.reload()}
          className="mt-6 rounded-md bg-leovee-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:opacity-90"
        >
          {t("common.errorBoundary.retry")}
        </button>
      </section>
    </div>
  );
}

type ErrorBoundaryProps = { children: ReactNode };
type ErrorBoundaryState = { hasError: boolean };

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surfaced to the console rather than swallowed: the fallback tells the
    // user what to do, this tells whoever is debugging what actually broke.
    console.error("Uncaught render error:", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return <ErrorFallback />;
    }
    return this.props.children;
  }
}
