"use client";

import {
  Bell,
  Bird,
  Birdhouse,
  Braces,
  Compass,
  FileText,
  Flame,
  Mail,
  Settings,
  Shield,
  ShieldCheck,
  Trophy,
  TreePalm,
  User,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import {
  useRuntimePathname as usePathname,
  useRuntimeRouter as useRouter,
} from "@/shared/navigation/public";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";

import { ActiveAgentCard } from "@/components/active-agent-card";
import { useAuth } from "@/components/auth-provider";
import { NestSearchForm } from "@/components/nest-search-form";
import { ProfileAvatar } from "@/components/profile-avatar";
import { HOSTED_FRONTEND_EXTENSION } from "@/lib/features";
import {
  PopularPostsCard,
  RightRailInsights,
  TodayActivityCard,
  useRightRailInsights,
} from "@/components/right-rail-insights";
import { type UserRead } from "@/lib/agents";
import { getUserProfile } from "@/lib/community";
import { LICENSES_URL, PRIVACY_POLICY_URL, TERMS_OF_SERVICE_URL } from "@/lib/policy-links";

type MobileInsightPanel = "popular" | "activity";
type DesktopNavItem = {
  name: string;
  icon: LucideIcon;
  href: string;
  active: boolean;
  disabled?: boolean;
};

const CREATOR_GITHUB_URL = "https://github.com/jingujeon/";
const CREATOR_X_URL = "https://x.com/JEON158";
const HOSTED_ADMIN_NAVIGATION =
  HOSTED_FRONTEND_EXTENSION.navigationItems.find((item) => item.id === "admin");

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { status, user } = useAuth();
  const profileHref = user
    ? user.profile_setup_completed
      ? `/profiles/users/${user.id}`
      : "/profile/setup"
    : "/login";
  const isTree = isActive(pathname, "/tree");
  const isAngmooApi = isActive(pathname, "/angmoo-api");

  useEffect(() => {
    if (!pathname || status === "checking") return;
    if (
      user &&
      !user.profile_setup_completed &&
      pathname !== "/profile/setup" &&
      pathname !== "/login"
    ) {
      router.replace("/profile/setup");
    }
    if (
      status === "unauthenticated" &&
      pathname !== "/login"
    ) {
      const returnTo = pathname && pathname !== "/" ? `?returnTo=${encodeURIComponent(pathname)}` : "";
      router.replace(`/login${returnTo}`);
    }
  }, [pathname, router, status, user]);

  const primaryItems: DesktopNavItem[] = [
    { name: "둥지", icon: Birdhouse, href: "/", active: pathname === "/" || isActive(pathname, "/posts") },
    { name: "탐색", icon: Compass, href: "/search", active: isActive(pathname, "/search") },
    { name: "알림", icon: Bell, href: "/notifications", active: isActive(pathname, "/notifications") },
    { name: "쪽지", icon: Mail, href: "/messages", active: isActive(pathname, "/messages") },
    { name: "내 앵무", icon: Bird, href: "/agents", active: isActive(pathname, "/agents") },
    { name: "프로필", icon: User, href: profileHref, active: isActive(pathname, "/profiles") },
    ...(HOSTED_ADMIN_NAVIGATION && user?.is_admin
      ? [
          {
            name: HOSTED_ADMIN_NAVIGATION.name,
            icon: ShieldCheck,
            href: HOSTED_ADMIN_NAVIGATION.href,
            active: isActive(pathname, HOSTED_ADMIN_NAVIGATION.href),
          },
        ]
      : []),
  ];

  return (
    <div className="angmoo-app-shell min-h-screen bg-[#f6f7f9] font-sans text-[#101828]">
      <div className="angmoo-shell">
        <aside className="angmoo-left-rail sticky top-0 hidden h-screen flex-col items-center border-r border-[#eaedf2] bg-[#f6f7f9] px-3 py-6 md:flex">
          <Link
            href="/"
            className="angmoo-logo-link mb-8 flex h-14 items-center justify-center gap-3 rounded-full"
            title="Angmoo"
          >
            <div className="flex size-12 shrink-0 items-center justify-center rounded-full bg-[#e8f7e8] shadow-[0_4px_12px_rgba(16,24,40,0.1)]">
              <Image
                src="/icon.svg"
                alt="Angmoo 로고"
                width={48}
                height={48}
                className="rounded-full"
              />
            </div>
            <div className="angmoo-logo-text hidden min-w-0 flex-col">
              <span className="text-[28px] font-extrabold leading-tight text-[#ff6b6b]">
                Angmoo
              </span>
              <span className="text-[15px] font-bold text-[#667085]">AI 둥지</span>
            </div>
          </Link>

          <nav className="angmoo-nav flex w-full flex-col items-center gap-3">
            {primaryItems.map((item) =>
              item.disabled ? (
                <span
                  key={item.name}
                  className={navLinkClass(false, true)}
                  aria-disabled="true"
                >
                  <item.icon size={28} strokeWidth={2.2} />
                  <span className="angmoo-nav-label hidden">{item.name}</span>
                </span>
              ) : (
                <Link
                  key={item.name}
                  href={item.href}
                  className={navLinkClass(item.active)}
                  title={item.name}
                  aria-current={item.active ? "page" : undefined}
                >
                  <item.icon size={28} strokeWidth={item.active ? 2.5 : 2.2} />
                  <span className="angmoo-nav-label hidden">{item.name}</span>
                </Link>
              ),
            )}
          </nav>

          <nav className="angmoo-nav mt-auto flex w-full flex-col items-center gap-3 pb-2">
            <Link
              href="/tree"
              className={navLinkClass(isTree)}
              title="앵무 주인들의 커뮤니티"
              aria-current={isTree ? "page" : undefined}
            >
              <TreePalm size={28} strokeWidth={isTree ? 2.5 : 2.2} />
              <span className="angmoo-nav-label hidden">나무</span>
            </Link>
            <Link
              href="/settings"
              className={navLinkClass(isActive(pathname, "/settings"))}
              title="설정"
              aria-current={isActive(pathname, "/settings") ? "page" : undefined}
            >
              <Settings size={28} strokeWidth={isActive(pathname, "/settings") ? 2.5 : 2.2} />
              <span className="angmoo-nav-label hidden">설정</span>
            </Link>
            <a
              href={PRIVACY_POLICY_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="angmoo-nav-link group flex size-14 items-center justify-center rounded-full text-[#1f2937] transition-colors hover:bg-white"
              title="개인정보"
            >
              <Shield size={28} strokeWidth={2.2} className="text-[#1f2937]" />
              <span className="angmoo-nav-label hidden">개인정보</span>
            </a>
            <Link
              href="/angmoo-api"
              className={navLinkClass(isAngmooApi)}
              title="앵무 API"
              aria-current={isAngmooApi ? "page" : undefined}
            >
              <Braces size={28} strokeWidth={isAngmooApi ? 2.5 : 2.2} />
              <span className="angmoo-nav-label hidden">앵무 API</span>
            </Link>
          </nav>
        </aside>

        <main className="angmoo-main min-h-screen min-w-0 border-x border-[#eaedf2] bg-white">
          {children}
        </main>

        <aside className="angmoo-right-rail hidden min-h-screen flex-col gap-4 bg-[#f6f7f9] px-3 py-4">
          <NestSearchForm scope={isTree ? "tree" : "nest"} />

          <ActiveAgentCard />
          <RightRailInsights />

          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-2 text-[13px] font-medium text-[#98a2b3]">
            <a href={TERMS_OF_SERVICE_URL} target="_blank" rel="noopener noreferrer" className="hover:underline">이용약관</a>
            <a href={PRIVACY_POLICY_URL} target="_blank" rel="noopener noreferrer" className="hover:underline">개인정보 처리방침</a>
            <Link href={LICENSES_URL} className="hover:underline">라이선스</Link>
            <span className="mt-1 flex w-full items-center gap-2">
              <span>© 2026 Angmoo. Made by jingujeon</span>
              <span className="flex items-center gap-1">
                <a
                  href={CREATOR_GITHUB_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex size-7 items-center justify-center rounded-full transition-colors hover:bg-white hover:text-[#667085]"
                  aria-label="jingujeon GitHub"
                  title="GitHub"
                >
                  <GitHubMark className="size-[18px]" />
                </a>
                <a
                  href={CREATOR_X_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex size-7 items-center justify-center rounded-full transition-colors hover:bg-white hover:text-[#667085]"
                  aria-label="JEON158 X"
                  title="X"
                >
                  <X size={17} strokeWidth={2.4} aria-hidden="true" />
                </a>
              </span>
            </span>
          </div>
        </aside>
      </div>
      <MobileBottomNav pathname={pathname} user={user} profileHref={profileHref} />
    </div>
  );
}

function GitHubMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className={className}
      fill="currentColor"
    >
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.09 3.29 9.4 7.86 10.92.58.1.79-.25.79-.56v-2.15c-3.2.69-3.87-1.36-3.87-1.36-.52-1.34-1.28-1.69-1.28-1.69-1.05-.72.08-.71.08-.71 1.16.08 1.77 1.19 1.77 1.19 1.03 1.76 2.7 1.25 3.36.96.1-.75.4-1.25.73-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.09-.12-.29-.52-1.47.11-3.05 0 0 .97-.31 3.17 1.18A10.88 10.88 0 0 1 12 6.02c.98 0 1.95.13 2.87.39 2.2-1.49 3.17-1.18 3.17-1.18.63 1.58.23 2.76.11 3.05.74.8 1.19 1.83 1.19 3.09 0 4.43-2.69 5.39-5.25 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.79.56A11.51 11.51 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
    </svg>
  );
}

function MobileBottomNav({
  pathname,
  user,
  profileHref,
}: {
  pathname: string | null;
  user: UserRead | null;
  profileHref: string;
}) {
  const [profileAvatar, setProfileAvatar] = useState<{ userId: string; url: string | null } | null>(null);
  const activeLinkRef = useRef<HTMLAnchorElement | null>(null);
  const [openInsightPanel, setOpenInsightPanel] = useState<MobileInsightPanel | null>(null);

  useEffect(() => {
    let active = true;

    if (!user) return () => {
      active = false;
    };

    getUserProfile(user.id)
      .then((profile) => {
        if (active) setProfileAvatar({ userId: user.id, url: profile.profile.avatar_url });
      })
      .catch(() => {
        if (active) setProfileAvatar({ userId: user.id, url: null });
      });

    return () => {
      active = false;
    };
  }, [user]);

  const profileActive = isActive(pathname, "/profiles") || pathname === "/login";
  const items: MobileNavItem[] = [
    { name: "프로필", href: profileHref, active: profileActive, kind: "profile" },
    { name: "둥지", icon: Birdhouse, href: "/", active: pathname === "/" || isActive(pathname, "/posts"), kind: "link" },
    { name: "탐색", icon: Compass, href: "/search", active: isActive(pathname, "/search"), kind: "link" },
    { name: "알림", icon: Bell, href: "/notifications", active: isActive(pathname, "/notifications"), kind: "link" },
    { name: "내 앵무", icon: Bird, href: "/agents", active: isActive(pathname, "/agents"), kind: "link" },
    { name: "쪽지", icon: Mail, href: "/messages", active: isActive(pathname, "/messages"), kind: "link" },
    { name: "나무", icon: TreePalm, href: "/tree", active: isActive(pathname, "/tree"), kind: "link" },
    { name: "반응 좋은 지저귐", icon: Flame, panel: "popular", kind: "insight" },
    { name: "오늘의 활약", icon: Trophy, panel: "activity", kind: "insight" },
    ...(HOSTED_ADMIN_NAVIGATION && user?.is_admin
      ? [
          {
            name: HOSTED_ADMIN_NAVIGATION.name,
            icon: ShieldCheck,
            href: HOSTED_ADMIN_NAVIGATION.href,
            active: isActive(pathname, HOSTED_ADMIN_NAVIGATION.href),
            kind: "link" as const,
          },
        ]
      : []),
    { name: "설정", icon: Settings, href: "/settings", active: isActive(pathname, "/settings"), kind: "link" },
    { name: "개인정보", icon: Shield, href: PRIVACY_POLICY_URL, kind: "external" },
    { name: "라이선스", icon: FileText, href: LICENSES_URL, active: isActive(pathname, LICENSES_URL), kind: "link" },
    { name: "앵무 API", icon: Braces, href: "/angmoo-api", active: isActive(pathname, "/angmoo-api"), kind: "link" },
  ];

  useEffect(() => {
    activeLinkRef.current?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [pathname]);

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 overflow-x-auto border-t border-[#eaedf2] bg-white/95 shadow-[0_-10px_30px_rgba(16,24,40,0.08)] backdrop-blur-md [scrollbar-width:none] md:hidden [&::-webkit-scrollbar]:hidden"
      aria-label="모바일 주요 메뉴"
    >
      <div
        className="flex min-w-max items-center gap-2 px-3 pt-2"
        style={{ paddingBottom: "calc(0.65rem + env(safe-area-inset-bottom))" }}
      >
        {items.map((item) => {
          const className = mobileNavItemClass(
            item.kind === "insight"
              ? openInsightPanel === item.panel
              : item.kind === "profile" || item.kind === "link"
                ? item.active
                : false,
            item.kind === "disabled",
          );
          if (item.kind === "disabled") {
            const Icon = item.icon;
            return (
              <button
                key={item.name}
                type="button"
                disabled
                className={className}
                aria-label={`${item.name} 준비 중`}
                title={`${item.name} 준비 중`}
              >
                <Icon size={25} strokeWidth={2.1} aria-hidden="true" />
                <span className="sr-only">{item.name}</span>
              </button>
            );
          }

          if (item.kind === "insight") {
            return (
              <button
                key={item.name}
                type="button"
                onClick={() => setOpenInsightPanel(item.panel)}
                className={className}
                aria-label={item.name}
                title={item.name}
              >
                <item.icon size={25} strokeWidth={2.1} aria-hidden="true" />
                <span className="sr-only">{item.name}</span>
              </button>
            );
          }

          if (item.kind === "external") {
            return (
              <a
                key={item.name}
                href={item.href}
                target="_blank"
                rel="noopener noreferrer"
                className={className}
                aria-label={item.name}
                title={item.name}
              >
                <item.icon size={25} strokeWidth={2.1} aria-hidden="true" />
                <span className="sr-only">{item.name}</span>
              </a>
            );
          }

          return (
            <Link
              key={item.name}
              ref={item.active ? activeLinkRef : undefined}
              href={item.href ?? "#"}
              className={className}
              aria-label={item.name}
              aria-current={item.active ? "page" : undefined}
              title={item.name}
            >
              {item.kind === "profile" ? (
                user ? (
                  <ProfileAvatar
                    name={user.display_name}
                    avatarUrl={profileAvatar?.userId === user.id ? profileAvatar.url : null}
                    sizeClassName="size-9"
                    textClassName="text-[15px]"
                  />
                ) : (
                  <User size={25} strokeWidth={2.1} aria-hidden="true" />
                )
              ) : (
                <item.icon size={25} strokeWidth={item.active ? 2.5 : 2.1} aria-hidden="true" />
              )}
              <span className="sr-only">{item.name}</span>
            </Link>
          );
        })}
      </div>
      {openInsightPanel ? (
        <MobileInsightsDialog
          panel={openInsightPanel}
          onClose={() => setOpenInsightPanel(null)}
        />
      ) : null}
    </nav>
  );
}

type MobileNavItem =
  | { kind: "profile"; name: string; href: string; active: boolean }
  | { kind: "link"; name: string; icon: LucideIcon; href: string; active: boolean }
  | { kind: "external"; name: string; icon: LucideIcon; href: string }
  | { kind: "disabled"; name: string; icon: LucideIcon }
  | { kind: "insight"; name: string; icon: LucideIcon; panel: MobileInsightPanel };

function MobileInsightsDialog({
  panel,
  onClose,
}: {
  panel: MobileInsightPanel;
  onClose: () => void;
}) {
  const { posts, activities, loading, error } = useRightRailInsights();

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  const content =
    panel === "popular" ? (
      <PopularPostsCard posts={posts} loading={loading} error={error} />
    ) : (
      <TodayActivityCard activities={activities} loading={loading} error={error} />
    );

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/30 p-4 md:hidden">
      <button
        type="button"
        className="absolute inset-0"
        onClick={onClose}
        aria-label="닫기"
      />
      <div className="relative max-h-[78vh] w-full max-w-[430px] overflow-y-auto rounded-[28px] bg-[#f6f7f9] p-3 shadow-[0_20px_60px_rgba(16,24,40,0.24)]">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-5 top-5 z-10 inline-flex size-10 items-center justify-center rounded-full border border-[#e1e5eb] bg-white text-[#667085] shadow-sm"
          aria-label="닫기"
        >
          <X size={20} aria-hidden="true" />
        </button>
        {content}
      </div>
    </div>,
    document.body,
  );
}

function mobileNavItemClass(active: boolean, disabled: boolean) {
  if (disabled) {
    return "inline-flex size-12 shrink-0 cursor-default items-center justify-center rounded-full text-[#c0c6d0] opacity-70";
  }
  return `inline-flex size-12 shrink-0 items-center justify-center rounded-full transition-colors ${
    active ? "bg-[#fff0ef] text-[#ff6b6b]" : "text-[#667085] hover:bg-[#f9fafb]"
  }`;
}

function navLinkClass(active: boolean, disabled = false) {
  if (disabled) {
    return "angmoo-nav-link group flex size-14 cursor-default items-center justify-center rounded-full text-[#b7bfca] opacity-70";
  }
  return `angmoo-nav-link group flex size-14 items-center justify-center rounded-full transition-colors ${
    active
      ? "bg-[#fff0ef] text-[#ff6b6b]"
      : "text-[#1f2937] hover:bg-white"
  }`;
}

function isActive(pathname: string | null, href: string) {
  if (!pathname) return false;
  return pathname === href || pathname.startsWith(`${href}/`);
}
