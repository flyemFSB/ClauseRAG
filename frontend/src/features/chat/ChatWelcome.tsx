import { type ReactNode } from "react";
import { IconFileSearch } from "../../components/icons";

export interface ChatWelcomeProps {
  readonly onAsk: (question: string) => void;
  readonly composer: ReactNode;
  readonly notice?: ReactNode;
}

/** 现代商事合同审查控制台主界面（无多余标签、无示例协议、输入框垂直居中）。 */
export function ChatWelcome({ composer, notice }: ChatWelcomeProps): ReactNode {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-canvas">
      <div className="mx-auto flex min-h-full w-full max-w-[920px] flex-col justify-center px-4 py-8 sm:px-6">
        {/* 顶部极简品牌与定位说明 */}
        <div className="flex flex-col items-center text-center pb-7">
          <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent-soft text-accent-strong shadow-xs">
            <IconFileSearch size={24} />
          </span>
          <h1 className="mt-4 text-title font-semibold tracking-tight text-ink">
            商事合同审查工作台
          </h1>
          <p className="mt-2 max-w-[56ch] text-body text-ink-secondary">
            面向复杂商务协议（MSA / NDA / SOW / SaaS License 等）的条款级证据驱动审查
          </p>
        </div>

        {/* 垂直居中的核心审查输入工作区 */}
        <div className="w-full">{composer}</div>

        {notice === undefined ? null : <div className="mt-4">{notice}</div>}
      </div>
    </div>
  );
}
