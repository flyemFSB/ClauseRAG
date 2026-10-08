import type { ReactNode } from "react";

/** 单条骨架屏占位条，带有平滑闪烁微动效果。 */
export function SkeletonBar({ className }: { readonly className?: string }): ReactNode {
  return (
    <span
      aria-hidden="true"
      className={`relative block overflow-hidden rounded-sm bg-surface-hover/80 after:absolute after:inset-0 after:-translate-x-full after:animate-[shimmer_1.6s_infinite] after:bg-gradient-to-r after:from-transparent after:via-surface/70 after:to-transparent ${className ?? ""}`}
    />
  );
}

/** 表格多行骨架屏占位组件。 */
export function SkeletonRows({
  rows,
  className,
  rowHeight = "h-10",
}: {
  readonly rows: number;
  readonly className?: string;
  readonly rowHeight?: string;
}): ReactNode {
  return (
    <div className={className} aria-busy="true">
      <span className="sr-only">正在加载</span>
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          aria-hidden="true"
          className={`flex ${rowHeight} items-center gap-3 border-t border-divider px-3`}
        >
          <SkeletonBar className="h-3 w-6" />
          <SkeletonBar className="h-3 w-40" />
          <SkeletonBar className="h-3 flex-1" />
          <SkeletonBar className="h-3 w-12" />
        </div>
      ))}
    </div>
  );
}

/** 文本多行骨架屏占位组件。 */
export function SkeletonLines({ lines = 3 }: { readonly lines?: number }): ReactNode {
  return (
    <div className="flex flex-col gap-2 py-1" aria-busy="true">
      <span className="sr-only">正在加载</span>
      {Array.from({ length: lines }, (_, index) => (
        <SkeletonBar key={index} className={`h-3 ${index === lines - 1 ? "w-1/2" : "w-full"}`} />
      ))}
    </div>
  );
}
