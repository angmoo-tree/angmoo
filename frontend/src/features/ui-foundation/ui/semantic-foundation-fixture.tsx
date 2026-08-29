"use client";

import {
  ArrowLeft,
  Bell,
  Bird,
  Home,
  MessageCircle,
  Network,
  RefreshCw,
  Settings,
  Users,
} from "lucide-react";
import { useState } from "react";

import styles from "./semantic-foundation-fixture.module.css";
import {
  Avatar,
  Badge,
  BottomNavigation,
  Button,
  Card,
  DegradedPanel,
  Dialog,
  EmptyState,
  Field,
  IconButton,
  InlineError,
  Input,
  ListRow,
  PageHeader,
  Select,
  StatusChip,
  Tabs,
  Textarea,
  Toast,
} from "@/shared/ui/public";

const INLINE_ERROR_ID = "foundation-inline-error";

const TAB_ITEMS = [
  { id: "all", label: "전체", panelId: "foundation-tab-all" },
  { id: "running", label: "활동 중", panelId: "foundation-tab-running" },
  { id: "disabled", label: "비활성", panelId: "foundation-tab-disabled", disabled: true },
];

const NAV_ITEMS = [
  { id: "home", label: "홈", icon: <Home size={22} /> },
  { id: "feed", label: "피드", icon: <MessageCircle size={22} /> },
  { id: "alerts", label: "알림", icon: <Bell size={22} /> },
  { id: "characters", label: "캐릭터", icon: <Users size={22} /> },
  { id: "worlds", label: "World", icon: <Network size={22} /> },
  { id: "status", label: "상태", icon: <RefreshCw size={22} /> },
  { id: "settings", label: "설정", icon: <Settings size={22} /> },
];

export function SemanticFoundationFixture() {
  const [selectedTab, setSelectedTab] = useState("all");
  const [activeNavigation, setActiveNavigation] = useState("feed");
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <div
      className={styles.fixture}
      data-ui-foundation-fixture
      data-fixture-schema="ui-b-semantic-primitives-v1"
    >
      <PageHeader
        title="UI Foundation"
        subtitle="UI-B deterministic fixture"
        backAction={
          <IconButton
            label="이전 화면"
            variant="ghost"
            data-ui-test="minimum-target"
          >
            <ArrowLeft size={20} aria-hidden="true" />
          </IconButton>
        }
        actions={
          <IconButton
            label="상태 새로고침"
            variant="secondary"
            data-ui-test="focus-target"
          >
            <RefreshCw size={20} aria-hidden="true" />
          </IconButton>
        }
      />

      <main className={styles.main}>
        <section className={styles.intro}>
          <p className={styles.eyebrow}>Angmoo Local · UI-B</p>
          <h2 className={styles.introTitle}>Semantic token · primitive foundation</h2>
          <p className={styles.introCopy} data-ui-test="contrast-sample">
            원격 글꼴과 이미지 없이 Phone 환경의 버튼, 입력, 상태, 탐색, 피드백 계약을
            고정합니다.
          </p>
        </section>

        <section className={styles.section} aria-labelledby="foundation-actions">
          <div className={styles.sectionHeading}>
            <p className={styles.sectionEyebrow}>Actions</p>
            <h2 className={styles.sectionTitle} id="foundation-actions">
              의미와 상태가 분리된 버튼
            </h2>
          </div>
          <div className={styles.buttonGrid}>
            <Button variant="primary" data-ui-test="hover-target">
              저장하기
            </Button>
            <Button variant="strong" data-ui-test="active-target">
              실행 중지
            </Button>
            <Button variant="secondary">취소</Button>
            <Button variant="ghost">자세히</Button>
            <Button variant="danger">연결 제거</Button>
            <Button variant="secondary" disabled data-ui-test="disabled-button">
              사용할 수 없음
            </Button>
            <Button loading loadingLabel="저장 중" data-ui-test="loading-button">
              저장
            </Button>
          </div>
        </section>

        <section className={styles.section} aria-labelledby="foundation-fields">
          <div className={styles.sectionHeading}>
            <p className={styles.sectionEyebrow}>Fields</p>
            <h2 className={styles.sectionTitle} id="foundation-fields">
              label · hint · error 연결
            </h2>
          </div>
          <Card className={styles.formStack}>
            <Field
              id="foundation-character-name"
              label="표시 이름"
              required
              helperText="World 안에서 구분할 이름입니다."
            >
              {(fieldProps) => (
                <Input
                  {...fieldProps}
                  defaultValue="미도리야 이즈쿠"
                  data-ui-test="control-boundary"
                />
              )}
            </Field>
            <Field id="foundation-world-role" label="World 역할">
              {(fieldProps) => (
                <Select {...fieldProps} defaultValue="student">
                  <option value="student">학생</option>
                  <option value="teacher">교사</option>
                </Select>
              )}
            </Field>
            <Field id="foundation-long-copy" label="World 안의 배경">
              {(fieldProps) => (
                <Textarea
                  {...fieldProps}
                  defaultValue="긴 한국어 설명과 local-world://characters/very-long-character-identifier-that-must-wrap-without-breaking-the-phone-layout 를 함께 넣어도 넘치지 않습니다."
                />
              )}
            </Field>
            <Field
              id="foundation-invalid"
              label="활동 시간"
              error="활동 시간은 00:00부터 23:59 사이여야 합니다."
            >
              {(fieldProps) => (
                <Input
                  {...fieldProps}
                  defaultValue="25:90"
                  data-ui-test="error-control"
                />
              )}
            </Field>
            <InlineError id={INLINE_ERROR_ID} data-ui-test="inline-error">
              설정을 저장하지 못했습니다. 입력값을 다시 확인해 주세요.
            </InlineError>
          </Card>
        </section>

        <section className={styles.section} aria-labelledby="foundation-presentation">
          <div className={styles.sectionHeading}>
            <p className={styles.sectionEyebrow}>Presentation</p>
            <h2 className={styles.sectionTitle} id="foundation-presentation">
              flat row와 summary card
            </h2>
          </div>
          <Card>
            <div className={styles.avatarRow}>
              <Avatar
                src="/icon.svg"
                alt="Angmoo 로컬 아이콘"
                fallback="앵"
                className={styles.avatarDemo}
                fallbackClassName={styles.avatarFallbackA}
              />
              <Avatar
                fallback="미"
                alt="미도리야 이즈쿠"
                className={styles.avatarDemo}
                fallbackClassName={styles.avatarFallbackB}
              />
              <Badge>로컬 전용</Badge>
            </div>
          </Card>
          <div>
            <ListRow>
              <Avatar
                fallback="올"
                alt="올마이트"
                className={styles.avatarDemo}
                fallbackClassName={styles.avatarFallbackA}
              />
              <div className={styles.listCopy}>
                <p className={styles.listTitle}>올마이트</p>
                <p className={styles.listMeta}>
                  flat chronological row · divider · no floating shadow
                </p>
              </div>
            </ListRow>
            <ListRow>
              <Avatar
                fallback="미"
                alt="미도리야 이즈쿠"
                className={styles.avatarDemo}
                fallbackClassName={styles.avatarFallbackB}
              />
              <div className={styles.listCopy}>
                <p className={styles.listTitle}>미도리야 이즈쿠</p>
                <p className={styles.listMeta}>긴 ID와 한국어도 Phone 폭 안에서 안전하게 줄바꿈</p>
              </div>
            </ListRow>
          </div>
        </section>

        <section className={styles.section} aria-labelledby="foundation-status">
          <div className={styles.sectionHeading}>
            <p className={styles.sectionEyebrow}>Typed status</p>
            <h2 className={styles.sectionTitle} id="foundation-status">
              color · icon · text
            </h2>
          </div>
          <div className={styles.statusGrid}>
            <StatusChip label="정상" tone="healthy" />
            <StatusChip label="실행 중" tone="running" />
            <StatusChip label="대기 중" tone="waiting" />
            <StatusChip label="일부 기능 제한" tone="degraded" />
            <StatusChip label="실패" tone="danger" />
            <StatusChip label="비활성" tone="disabled" />
          </div>
        </section>

        <section className={styles.section} aria-labelledby="foundation-navigation">
          <div className={styles.sectionHeading}>
            <p className={styles.sectionEyebrow}>Navigation roles</p>
            <h2 className={styles.sectionTitle} id="foundation-navigation">
              tabs · bottom navigation
            </h2>
          </div>
          <div data-ui-test="tabs">
            <Tabs
              ariaLabel="캐릭터 상태"
              items={TAB_ITEMS}
              selectedId={selectedTab}
              onSelect={setSelectedTab}
            />
          </div>
          <div
            id={TAB_ITEMS.find((item) => item.id === selectedTab)?.panelId}
            role="tabpanel"
            aria-labelledby={`${TAB_ITEMS.find((item) => item.id === selectedTab)?.panelId}-tab`}
            className={styles.tabPanel}
          >
            선택한 상태: {selectedTab}. Arrow key roving focus와 선택 상태를 제공합니다.
          </div>
          <div className={styles.navPreview} data-ui-test="bottom-navigation">
            <BottomNavigation
              activeId={activeNavigation}
              items={NAV_ITEMS}
              onSelect={setActiveNavigation}
            />
          </div>
        </section>

        <section className={styles.section} aria-labelledby="foundation-feedback">
          <div className={styles.sectionHeading}>
            <p className={styles.sectionEyebrow}>Feedback</p>
            <h2 className={styles.sectionTitle} id="foundation-feedback">
              오류와 degraded를 숨기지 않기
            </h2>
          </div>
          <div className={styles.feedbackStack}>
            <Toast tone="success">설정이 현재 기기에 저장되었습니다.</Toast>
            <EmptyState
              icon={<Bird size={24} aria-hidden="true" />}
              title="아직 연결된 캐릭터가 없습니다"
              description="새 캐릭터를 만들거나 기존 캐릭터를 이 World에 연결할 수 있습니다."
              action={<Button variant="secondary">캐릭터 연결</Button>}
            />
            <DegradedPanel
              title="관계 그래프를 잠시 읽을 수 없습니다"
              description="피드와 캐릭터 데이터는 유지됩니다. 진단 상태를 확인한 뒤 다시 시도하세요."
              action={<Button variant="secondary">다시 확인</Button>}
            />
          </div>
        </section>

        <section className={styles.section} aria-labelledby="foundation-dialog">
          <div className={styles.sectionHeading}>
            <p className={styles.sectionEyebrow}>Dialog</p>
            <h2 className={styles.sectionTitle} id="foundation-dialog">
              focus trap · Escape · return focus
            </h2>
          </div>
          <Button
            variant="danger"
            data-ui-test="dialog-trigger"
            onClick={() => setDialogOpen(true)}
          >
            World 연결 제거 확인
          </Button>
        </section>
      </main>

      <Dialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title="이 World에서 올마이트 연결을 제거할까요?"
        description="캐릭터 자체는 삭제되지 않으며 현재 World 참여만 종료됩니다."
        dialogAttributes={{ "data-ui-test": "dialog" }}
        closeButtonAttributes={{ "data-ui-test": "dialog-close" }}
        actions={
          <div className={styles.dialogActions}>
            <Button variant="secondary" onClick={() => setDialogOpen(false)}>
              취소
            </Button>
            <Button variant="danger" onClick={() => setDialogOpen(false)}>
              연결 제거
            </Button>
          </div>
        }
      >
        <p className={styles.dialogCopy}>
          destructive action은 대상과 범위를 다시 보여주고, 닫힌 뒤 원래 trigger로 focus를
          돌려줍니다.
        </p>
        <a
          className={styles.dialogLink}
          href="#foundation-dialog-help"
          data-ui-test="dialog-link"
        >
          연결 제거 범위 도움말
        </a>
      </Dialog>
    </div>
  );
}
