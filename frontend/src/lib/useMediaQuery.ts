/**
 * 视口媒体查询监听 Hook
 *
 * 监听指定 CSS 媒体查询条件（如断点变化），即时响应屏幕尺寸切换（用于抽屉与并列面板切换）。
 */

import { useEffect, useState } from "react";

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = (): void => {
      setMatches(list.matches);
    };
    list.addEventListener("change", onChange);
    return () => {
      list.removeEventListener("change", onChange);
    };
  }, [query]);

  return matches;
}
