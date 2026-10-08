import {
  Activity,
  ArrowRight,
  Ban,
  Bell,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleX,
  Copy,
  Database,
  Ellipsis,
  ExternalLink,
  FileSearch,
  FileText,
  Funnel,
  Gauge,
  GitCompare,
  Globe,
  Info,
  Layers,
  LayoutGrid,
  ListTree,
  LoaderCircle,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
  PanelLeft,
  PanelLeftClose,
  Paperclip,
  Pencil,
  Plus,
  RotateCw,
  Scale,
  Search,
  Settings,
  Shield,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Split,
  Sun,
  Trash2,
  TriangleAlert,
  Upload,
  Workflow,
  X,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

// 字形一律复用 `lucide-react`：本文件只声明本设计系统的默认尺寸与线宽，不再手工维护 path 数据。
// `DESIGN.md` 规定图标是中性灰阶的 1.5px 线性字形，因此默认值与 lucide 自带的 24px/2px 不同，
// 两者都在这里固定，调用点只表达语义与尺寸。

interface GlyphProps {
  readonly size?: number;
  readonly strokeWidth?: number;
  readonly className?: string;
}

/** 按本设计系统的默认尺寸与线宽渲染一个 lucide 字形。 */
function glyph(Icon: LucideIcon, size = 18, strokeWidth = 1.5) {
  return function Glyph({
    size: requested,
    strokeWidth: line,
    className,
  }: GlyphProps = {}): ReactNode {
    return (
      <Icon
        size={requested ?? size}
        strokeWidth={line ?? strokeWidth}
        className={className}
        aria-hidden="true"
      />
    );
  };
}

// 导航与页面架构图标

export const IconChat = glyph(MessageSquare);
export const IconGrid = glyph(LayoutGrid);
export const IconDatabase = glyph(Database);
export const IconDocument = glyph(FileText);
export const IconFileSearch = glyph(FileSearch);
export const IconSliders = glyph(SlidersHorizontal);
export const IconCog = glyph(Settings);
export const IconChevronDown = glyph(ChevronDown);

// 品牌与助手标识

/** 品牌标识：圆形底衬加一架天平，是本产品自己的标记，不属于通用字形集。 */
export function BrandMark({ size = 32 }: { readonly size?: number }): ReactNode {
  return (
    <span
      className="flex shrink-0 items-center justify-center rounded-full bg-ink text-canvas"
      style={{ width: size, height: size }}
    >
      <svg
        width={size * 0.56}
        height={size * 0.56}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
        <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
        <path d="M7 21h10" />
        <path d="M12 3v18" />
        <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" />
      </svg>
    </span>
  );
}

export const IconScale = glyph(Scale);

// 操作控件图标

export const IconSearch = glyph(Search);
export const IconFilter = glyph(Funnel);
export const IconPlus = glyph(Plus);
export const IconArrowRight = glyph(ArrowRight);
export const IconPaperclip = glyph(Paperclip);
export const IconEllipsis = glyph(Ellipsis);
export const IconCopy = glyph(Copy);
export const IconReplay = glyph(RotateCw);

// 状态反馈图标

export const IconCheck = glyph(Check, 16);
export const IconWarning = glyph(TriangleAlert, 16);
export const IconInfo = glyph(Info, 16);
export const IconError = glyph(CircleX, 16);

/** 加载中微动旋转指示器。 */
export function Spinner(): ReactNode {
  return <LoaderCircle className="animate-spin" size={16} strokeWidth={2} aria-hidden="true" />;
}

/** 环形进度条组件。 */
export function ProgressRing({
  size = 20,
  ratio,
  state = "running",
}: {
  readonly size?: number;
  readonly ratio: number;
  readonly state?: "running" | "done" | "failed" | "warning";
}): ReactNode {
  const radius = (size - 3) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(1, ratio));
  const tone =
    state === "done"
      ? "text-success"
      : state === "failed"
        ? "text-error"
        : state === "warning"
          ? "text-warning"
          : "text-accent";
  return (
    <svg
      className={tone}
      width={size}
      height={size}
      viewBox={`0 0 ${String(size)} ${String(size)}`}
      aria-hidden="true"
      style={{ transform: "rotate(-90deg)" }}
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.22"
        strokeWidth="2"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={circumference * (1 - clamped)}
      />
    </svg>
  );
}

// 头部与文件操作图标

export const IconBell = glyph(Bell);
export const IconSun = glyph(Sun);
export const IconMoon = glyph(Moon);
export const IconGlobe = glyph(Globe);
export const IconMenu = glyph(Menu);
export const IconSidebar = glyph(PanelLeft);
export const IconSidebarClose = glyph(PanelLeftClose);
export const IconChevronLeft = glyph(ChevronLeft);
export const IconChevronRight = glyph(ChevronRight);
export const IconUpload = glyph(Upload);
export const IconTrash = glyph(Trash2);
export const IconClose = glyph(X);

// 对话交互与引用图标

export const IconPencil = glyph(Pencil);
export const IconExternalLink = glyph(ExternalLink);

// 控制台与系统管理图标

export const IconGauge = glyph(Gauge);
export const IconLayers = glyph(Layers);
export const IconPipeline = glyph(Workflow);
export const IconSlash = glyph(Ban);
export const IconLogout = glyph(LogOut);

// 专业审计与管线流向图标
export const IconShield = glyph(Shield);
export const IconShieldAlert = glyph(ShieldAlert);
export const IconShieldCheck = glyph(ShieldCheck);
export const IconGitCompare = glyph(GitCompare);
export const IconListTree = glyph(ListTree);
export const IconSplit = glyph(Split);
export const IconActivity = glyph(Activity);
