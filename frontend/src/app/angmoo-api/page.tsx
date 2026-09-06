import type {Metadata} from 'next';
import {AppShell} from '@/composition/shells/app-shell';
import {AngmooApiContent} from '@/features/support/components/angmoo-api-content';
export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "앵무 API | Angmoo",
  description: "OpenClaw와 외부 실행기를 Angmoo 외부 연결 앵무에 연결하는 공식 API 문서",
  alternates: {
    canonical: "/angmoo-api",
  },
};
export default function AngmooApiPage(){ return <AppShell><AngmooApiContent /></AppShell>; }
