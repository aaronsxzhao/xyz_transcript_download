import {
  Component,
  lazy,
  Suspense,
  useState,
  useEffect,
  type ComponentType,
  type ReactNode,
} from "react";
import { reloadFreshPage } from "../lib/chunkRecovery";

class OptionalBoundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

/** Optional formatting must never prevent the actual page/data from opening. */
export function deferView<P extends object>(
  load: () => Promise<{ default: ComponentType<P> }>,
) {
  const createView = () =>
    lazy(
      () =>
        new Promise<{ default: ComponentType<P> }>((resolve, reject) => {
          const timer = setTimeout(
            () => reject(new Error("Tool loading timed out")),
            15000,
          );
          Promise.resolve()
            .then(load)
            .then(resolve, reject)
            .finally(() => clearTimeout(timer));
        }),
    ) as unknown as ComponentType<P>;
  const InitialView = createView();
  return function DeferredView({
    fallback,
    errorFallback,
    ...props
  }: P & { fallback: ReactNode; errorFallback?: (retry: () => void) => ReactNode }) {
    const [{ View, attempt }, setView] = useState(() => ({
      View: InitialView,
      attempt: 0,
    }));
    return (
      <OptionalBoundary
        key={attempt}
        fallback={errorFallback ? errorFallback(() => setView({ View: createView(), attempt: attempt + 1 })) : (
          <>
            {fallback}
            <p role="status" className="text-sm text-gray-400 py-3">
              Formatting could not load.{" "}
              <button
                className="underline text-indigo-300"
                onClick={() =>
                  setView({ View: createView(), attempt: attempt + 1 })
                }
              >
                Retry loading
              </button>{" "}
              <button
                className="underline text-indigo-300"
                onClick={reloadFreshPage}
              >
                Reload formatting
              </button>
            </p>
          </>
        )}
      >
        <Suspense fallback={fallback}>
          <View {...(props as P)} />
        </Suspense>
      </OptionalBoundary>
    );
  };
}

/** Mounted only while Suspense is pending; a stalled chunk must be escapable. */
function ToolPending({children}: {children: ReactNode}) {
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setExpired(true), 15000);
    return () => clearTimeout(timer);
  }, []);
  if (expired) throw new Error("Tool loading timed out");
  return <>{children}</>;
}

/** Failure of a secondary tool must not replace the reading page. */
export function OptionalTool({
  children,
  fallback,
  errorFallback,
}: {
  children: ReactNode;
  fallback: ReactNode;
  errorFallback?: ReactNode;
}) {
  return (
    <OptionalBoundary
      fallback={
        errorFallback || (
          <p role="status">
            This tool could not load.{" "}
            <button className="underline" onClick={reloadFreshPage}>
              Reload tools
            </button>
          </p>
        )
      }
    >
      <Suspense fallback={<ToolPending>{fallback}</ToolPending>}>{children}</Suspense>
    </OptionalBoundary>
  );
}
