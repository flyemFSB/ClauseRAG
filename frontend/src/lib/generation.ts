/**
 * 异步轮次与代际栅栏（Generation Fence）
 *
 * 通过单调递增的版本号隔离并发异步回调，防止过时请求响应污染新上下文状态。
 */

export interface Generation {
  /** 开始新的一代并返回它的编号；此前各代就此失效。 */
  readonly begin: () => number;
  /** 让当前代失效（放弃在途工作），不取新号。 */
  readonly abandon: () => void;
  /** 这一代是否仍然是当前代 —— 一次异步回调写任何状态之前都要问它。 */
  readonly isCurrent: (generation: number) => boolean;
}

export function createGeneration(): Generation {
  let current = 0;
  return {
    begin: () => (current += 1),
    abandon: () => {
      current += 1;
    },
    isCurrent: (generation) => generation === current,
  };
}
