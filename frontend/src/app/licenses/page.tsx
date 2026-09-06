import type {Metadata} from 'next';
import {AppShell} from '@/composition/shells/app-shell';
import {LicensesContent} from '@/features/support/components/licenses-content';
export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "라이선스 | Angmoo",
  description: "Angmoo application과 제3자 구성요소의 라이선스 고지",
  alternates: {
    canonical: "/licenses",
  },
};
export default function LicensesPage(){ return <AppShell><LicensesContent /></AppShell>; }
