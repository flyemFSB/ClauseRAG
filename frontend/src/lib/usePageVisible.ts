/**
 * 页面可见性监听 Hook
 *
 * 监听 document.visibilitychange 事件，在页面处于后台切走时暂停轮询等无用请求以节省资源。
 */

import { useEffect, useState } from "react";

export function usePageVisible(): boolean {
  const [visible, setVisible] = useState(() => document.visibilityState === "visible");

  useEffect(() => {
    const update = (): void => {
      setVisible(document.visibilityState === "visible");
    };
    document.addEventListener("visibilitychange", update);
    return () => {
      document.removeEventListener("visibilitychange", update);
    };
  }, []);

  return visible;
}
