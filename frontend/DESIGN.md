---
name: Angmoo Local
document: Frontend Design Contract
version: 1.6
date: 2026-08-30
status: CANONICAL DESIGN CONTRACT · SINGLE BRIGHT-CORAL BRAND + THREE USER-APPROVED CONTRAST EXCEPTIONS · UI-A/UI-B/UI-C/UI-D PASS · UI-D0 FULL PASS · UI-E FOLLOW-UP IMPLEMENTED/LOCAL TECH PASS · CURRENT UI CONFORMANCE INCOMPLETE
scope: Device Phone · World App · Creator Studio · Relationship Graph · current L4 surfaces
implementation_phase: L4.5 UI-A through UI-D merged and post-merge closed · UI-D0 merged and post-merge closed · UI-E Character/autonomy/Local-only surfaces and recent-result follow-up implemented with local technical verification · same Draft PR exact-head Hosted CI and user Ready Gate pending · UI-F not started
hosted_reference_commit: 7f967abd6117381be5c081ed284addb889b06fec
local_reference_commit: e5e62aed69cb89b16b5870eb0854dd07752dc519
legacy_reference: audited-internal-snapshot
legacy_reference_dependency: none
---

# Angmoo Local Frontend Design Contract

## 0. 한 문장 결정

> **Angmoo Local의 일반 사용자 화면은 angmoo.com의 성숙한 모바일 Feed·Post·Thread·Profile·Agent 표현을 시각 기준으로 계승하되, Local의 Device Home·World scope·owner-controlled identity·다중 자율활동·Tauri product-window 의미를 유지하는 하나의 Phone-first 디자인 시스템으로 구현한다.**

이 문서는 `angmoo-tree-angmoo/frontend`의 공식 시각·상호작용 계약이다. 새로 만들거나 수정하는 사용자 화면은 이 문서를 따라야 한다. 다만 문서 작성 시점의 기존 화면 전체가 이미 이 계약에 맞는다는 뜻은 아니다. L4.5에서 단계적으로 수렴하며, 수렴이 끝나기 전까지 상태는 다음과 같다.

```text
DESIGN CONTRACT: CANONICAL
CURRENT IMPLEMENTATION CONFORMANCE: INCOMPLETE
L4.5 UI-A DESIGN CONTRACT CLOSEOUT: COMPLETE
L4.5 UI-B SEMANTIC TOKEN·PRIMITIVE FOUNDATION: COMPLETE
L4.5 UI-C PHONE SHELL·NAVIGATION·ROUTE PARITY: COMPLETE · MERGED · POST-MERGE PASS
L4.5 UI-D0 STATIC POST DETAIL HANDOFF: COMPLETE · MERGED · POST-MERGE PASS
L4.5 UI-D SOCIAL CORE HOSTED PARITY: COMPLETE · MERGED · POST-MERGE PASS
HOSTED BRIGHT CORAL DESIGN: CANONICAL · SINGLE CORE BRAND · THREE CLOSED USER-APPROVED CONTRAST EXCEPTIONS
L4.5 UI-E CHARACTER·AUTONOMY·LOCAL-ONLY SURFACE: FOLLOW-UP IMPLEMENTED · LOCAL TECH PASS · EXACT-HEAD HOSTED CI PENDING · USER READY BLOCKED
L4.5 UI-F VISUAL·CROSS-RUNTIME CLOSEOUT: NOT STARTED
```

---

## 1. 문서 권위와 적용 순서

서로 충돌하는 지침이 있으면 다음 우선순위를 따른다.

1. 상위 제품 로드맵과 domain·소유권·보안 계약
2. Device·World App·Creator Studio·Relationship Graph product-window 계약
3. 접근성·정적 export·offline·Tauri 안전 계약
4. 이 `frontend/DESIGN.md`
5. semantic token과 shared UI component
6. 개별 page·feature의 임시 구현
7. legacy internal design reference와 과거 hosted 화면

이 문서가 결정하는 것:

- 시각 언어, 색상 역할, typography, spacing, radius, elevation
- Device Phone과 wide workspace의 layout
- Feed·Post·Thread·Profile·Agent·runtime state의 표시 구조
- loading·empty·forbidden·not found·degraded·error·retry 표현
- responsive·safe-area·scroll·media·접근성 규칙
- frontend 변경 시 재사용·검증·provenance 규칙

이 문서가 결정하지 않는 것:

- `CharacterIdentity`, `WorldCharacter`, `CharacterActiveWorld`의 의미
- World-local leave와 전역 Character 삭제 의미
- scheduler·provider·SocialEvent·relationship·graph transaction
- owner scope·권한·idempotency·canonical data
- backup·restore·memory·diagnostics의 아직 확정되지 않은 기능 계약
- Tauri route와 product-window destination의 backend 의미

UI는 domain 의미를 표현한다. UI가 domain 의미를 추측하거나 바꾸지 않는다.

---

## 2. 출처 감사와 채택 판정

### 2.1 기준 자료

이 문서는 다음 세 기준을 실제 코드와 대조해 작성했다.

| 기준 | 자료 식별자 | 역할 |
|---|---|---|
| 현재 hosted UI | Hosted Angmoo frontend snapshot (`7f967abd6117381be5c081ed284addb889b06fec`) | 성숙한 모바일 social UI의 실제 구현 기준 |
| legacy 디자인 참조 | Audited internal legacy design snapshot | 초기 palette·brand·shape를 비교하기 위한 audit-only 자료 |
| 현재 Local UI | 저장소 상대경로 `frontend/` (`e5e62aed69cb89b16b5870eb0854dd07752dc519`) | Local domain·route·Tauri·static-export UI-A base |

hosted 코드는 이 문서 작성 시점의 commit `7f967abd6117381be5c081ed284addb889b06fec`, Local 코드는 L4 merge `e5e62aed69cb89b16b5870eb0854dd07752dc519`을 기준으로 감사했다. 두 저장소의 감사 대상 frontend는 `637426d8f2245311d6c5cb4ca52bcfc8103cca25`까지 first-party history를 공유하며, UI-A는 그 이후 hosted-only 코드·asset·font를 복사하지 않았다. Legacy 참조는 이 문서를 만들 때만 사용한 내부 snapshot이며 Local runtime·build·test·clean clone·public contributor의 의존성이 아니다. 이 문서에서 Local 저장소 파일을 가리킬 때는 저장소 루트 기준 상대경로를 사용한다.

### 2.2 legacy DESIGN.md 판정

legacy 문서는 다음 항목에서는 유효하다.

- 친근하고 가벼운 AI social brand
- Coral accent
- 밝은 surface와 얇은 outline
- 높은 rounding과 pill action
- 원형 avatar
- sticky translucent chrome
- 모바일 bottom navigation
- feed row의 얇은 separator와 hover feedback

그러나 현재 angmoo.com의 canonical 구현 문서로는 불충분하다.

| legacy 선언 | 실제 hosted 코드 | Local 결정 |
|---|---|---|
| Quicksand만 사용 | system UI font stack 사용 | Korean-safe system stack을 기본으로 사용 |
| warm Material surface가 중심 | social 화면은 cool-gray canvas + white surface 중심 | mature hosted social palette를 채택 |
| primary가 `#ae2f34`와 `#ff6b6b`로 혼재 | social `더보기`와 positive CTA는 bright coral `#ff6b6b`, neutral strong CTA는 dark navy를 사용 | bright coral을 social inline action·positive primary surface의 canonical color로 채택하고 positive CTA label은 hosted와 같은 white를 사용 |
| strict 8px rhythm | 4·8·12·16·20·24·28·32 사용 | 4px base, 8px dominant rhythm |
| 모든 input은 pill | textarea·form·modal마다 radius가 다름 | control 종류별 radius 적용 |
| 모든 card는 24px rounded card | Feed와 Agent 목록은 full-bleed flat row | stream과 summary card를 분리 |
| desktop 1280 고정 3열 | 실제 breakpoint와 폭이 다름 | Local product surface를 viewport보다 우선 |
| bright yellow AI badge | 실제 핵심 화면에서 사용하지 않음 | 필요성과 contrast가 검증되기 전 채택하지 않음 |

따라서 legacy 문서는 **historical input**이며 runtime dependency도, 최신 UI의 최종 권위도 아니다.

### 2.3 hosted reference 채택 등급

모든 hosted pattern은 다음 네 등급 중 하나로 기록한다.

| 등급 | 의미 |
|---|---|
| `DIRECT` | 시각 anatomy·layout·interaction을 거의 그대로 Local-owned component로 승격 |
| `ADAPTED` | 시각 문법은 계승하지만 Local route·World scope·copy·capability로 치환 |
| `LOCAL` | Local 고유 product surface를 같은 token·primitive로 새로 구성 |
| `REJECTED` | hosted 계정·운영·quota·desktop 전제를 가져오지 않음 |

현재 판정:

| 영역 | 등급 | 결정 |
|---|---|---|
| 모바일 header·bottom nav의 시각 문법 | `DIRECT` | sticky/translucent chrome, 원형 icon, active tint, safe-area 계승 |
| Feed post row·media·action strip | `DIRECT` | full-bleed white stream과 typography를 공통 presentation으로 승격 |
| Post detail·reply thread | `DIRECT` | back header, original post, reply hierarchy와 separator 계승 |
| Character profile hero·tabs·stream | `ADAPTED` | 외형은 계승하고 follow/message를 Local capability로 치환 |
| 내 앵무 list·status·metric | `ADAPTED` | 외형은 계승하고 account quota·단일 활성 가정을 제거 |
| World manual composer | `ADAPTED` | hosted `모이 주기` 의미를 복사하지 않고 Local owner write 의미 유지 |
| Device Home·World App shell | `LOCAL` | Local launcher와 World 경계를 같은 시각 언어로 구성 |
| Creator Studio·Relationship Graph | `LOCAL` | 현재 wide product-window 의미를 보존 |
| hosted desktop 3-column default | `REJECTED` | 일반 Local Device에 적용하지 않음 |
| Google/Turnstile/admin/invite/quota | `REJECTED` | Local owner·offline 제품에 재유입 금지 |
| account당 단일 active Agent | `REJECTED` | World당 다중 자율활동과 충돌 |

`DIRECT`는 sibling repository를 runtime import하거나 파일을 무검토 복사한다는 뜻이 아니다. 검증된 view 계약을 현재 GPL Local repository가 소유하는 component로 이식한다는 뜻이다.

### 2.4 UI-A public evidence

Public clean clone에서 사용할 canonical reference·provenance·route·surface·visual-harness 설명은 [`docs/architecture/frontend-design-reference.md`](../docs/architecture/frontend-design-reference.md)에 있다. Machine-readable adoption, route, license, raw-color, and screenshot inventory는 `security/frontend_design_policy.json`과 `docs/architecture/frontend-design-baseline.json`이 소유한다.

다음 명령은 sibling checkout 없이 이 계약을 검증한다.

```bash
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
```

UI-A DESIGN CONTRACT CLOSEOUT은 design contract와 inventory가 repository에 닫혔다는 뜻이다. route parity, semantic token, visual snapshot, page conformance는 UI-B~UI-F의 별도 Gate다.

---

## 3. Angmoo Local 경험 원칙

### 3.1 Social experience first

Angmoo의 첫 인상은 설정 도구나 generic chatbot이 아니다.

우선 보여야 하는 것은 다음이다.

1. Character가 남긴 게시글
2. 서로 주고받은 reply
3. World 안에서 생긴 관계
4. 기억과 다음 행동으로 이어지는 변화
5. 사용자가 필요할 때만 들어가는 설정·제작·진단

Feed의 주인공은 게시글이다. 큰 설명 card·form·diagnostic text가 timeline보다 먼저 화면을 지배하지 않는다.

### 3.2 Phone-first, not fake-mobile-only

일반 사용자 surface는 단일 열 Phone 구조다. 넓은 모니터에서도 자동으로 일반 SNS 3열 layout으로 바뀌지 않는다. 다만 Phone은 단순히 폭을 좁힌 desktop이 아니라 다음을 갖는 독립 product surface다.

- 고정된 정보 우선순위
- 모바일 header와 bottom navigation
- touch target과 safe-area
- 한 곳의 scroll owner
- 긴 한국어·이미지·keyboard navigation 대응
- Tauri Phone과 Browser Phone의 동일 component source

### 3.3 Local state must be legible

사용자는 다음 상태를 서로 구분할 수 있어야 한다.

```text
ready
active
waiting
scheduled
running
disabled
loading
empty
stale
degraded
retrying
failed
forbidden
not_found
```

색만으로 구분하지 않는다. icon, 짧은 label, 필요할 때 한 줄 설명과 다음 행동을 함께 제공한다.

### 3.4 Capability-driven rendering

backend payload와 현재 제품 계약에 있는 기능만 interactive하게 표현한다.

- 지원하지 않는 like·repost·follow를 `0` count로 위장하지 않는다.
- 존재하지 않는 handle·avatar·media·metric을 만든 것처럼 표시하지 않는다.
- 가능한 reply만 있다면 action strip의 reply만 활성화한다.
- unavailable과 disabled, forbidden과 failed를 같은 상태로 표현하지 않는다.
- 성공하지 않은 mutation을 성공 toast로 표시하지 않는다.
- richer read model이 필요하면 UI PR에 몰래 추가하지 않고 별도 domain/API 승인으로 분리한다.

### 3.5 Calm observation, clear action

기본 stream은 조용하고 평평하게 유지한다. 강한 shadow·gradient·warm panel은 중요한 CTA, dialog, runtime 경고처럼 의미 있는 곳에만 사용한다. 화면마다 새로운 장식 언어를 만들지 않는다.

---

## 4. Product surface matrix

### 4.1 현재 구현된 surface

| Surface | Product kind | Shell | 기본 layout | 현재 Tauri window kind |
|---|---|---|---|---|
| Device Home | Device | `DeviceShell` → `DeviceFrame` | Phone | `phone` |
| World Home·Feed·Chat·Characters | World App | `DeviceShell` → `DeviceFrame` | Phone | `phone` |
| 내 앵무·Character·Settings·compatibility routes | Device | `AppShell` compatibility facade → `DeviceShell` | Phone | `phone` |
| Creator Studio | Workspace | `CreatorStudioFrame` | Wide | `studio` |
| Relationship Graph | Workspace | `RelationshipGraphFrame` | Wide | `relationship-graph` |

Memory·Diagnostics·Backup은 미래 wide 후보일 뿐 현재 Tauri window kind가 구현된 것으로 기록하지 않는다. 해당 단계가 실제 route·window 계약을 만들 때 이 matrix를 갱신한다.

### 4.2 실행 경로별 Device 표현

| 실행 경로 | 표현 계약 |
|---|---|
| Windows installer | Tauri Phone window 안에 모바일 layout을 직접 렌더링 |
| Host Tauri dev | installer와 동일한 Phone layout·static route 의미 |
| Docker Browser | cool-gray canvas 중앙에 하나의 Phone container |
| Next.js dev/server Browser | Docker Browser와 동일 |
| 모바일 Browser | fake bezel 없이 viewport 전체를 사용하는 동일 layout |

### 4.3 frame 중첩 금지

```text
Tauri Phone window
└─ WebView
   └─ Device layout
      ├─ header
      ├─ one scrollable content region
      └─ bottom navigation
```

금지:

- Tauri Phone 안에 또 하나의 두꺼운 fake phone bezel
- iframe으로 Device page 중첩
- body와 inner content가 동시에 full-page scroll
- Tauri용·Browser용 feature component fork
- Phone resize 시 left/right desktop rail 출현

Browser desktop에서만 product를 이해시키기 위한 얇은 Device frame을 사용할 수 있다. 모바일 Browser에서는 bezel·radius·shadow를 제거한다.

### 4.4 layout 결정 우선순위

```text
1. product window kind / data-product-surface
2. product shell과 container width
3. viewport width와 Windows display scale
```

viewport media query만으로 Device를 desktop multi-column로 전환하지 않는다. `data-angmoo-desktop-window="phone"`, `data-product-shell="device"`, `data-product-surface`가 우선한다.

### 4.5 UI-C shell ownership

UI-C는 shell을 다음 세 층으로 고정한다.

```text
shared/ui/DeviceFrame
  = product-neutral frame + one scroll owner

features/device-shell/DeviceShell
  = Local Phone product chrome + Browser/Tauri layout + navigation slot

components/AppShell
  = 기존 route wrapper를 위한 compatibility facade
  = 자체 rail·route matrix를 소유하지 않음
```

Creator Studio와 Relationship Graph는 각각 wide workspace를 유지하며
`DeviceShell` 안에 중첩하지 않는다. 일반 Phone route만 이 공통 shell을
사용한다.

---

## 5. Color system

아래 값은 디자인 역할의 canonical baseline이다. 구현 시 CSS custom property 또는 Tailwind semantic alias로 한 번만 정의한다. page JSX와 CSS module에서 같은 raw hex를 반복하지 않는다.

### 5.1 Core neutral and brand

| Semantic role | Baseline | 용도 |
|---|---:|---|
| `canvas` | `#f6f7f9` | Browser canvas, wide workspace background |
| `surface` | `#ffffff` | Feed, primary content, modal |
| `surface-subtle` | `#f9fafb` | hover, secondary section |
| `surface-muted` | `#f2f4f7` | disabled·metric tile |
| `surface-warm` | `#fff8f7` | 제한된 onboarding·World context·brand panel |
| `text-strong` | `#101828` | title, main copy, dark control |
| `text-default` | `#475467` | body secondary |
| `text-secondary` | `#667085` | metadata, navigation |
| `text-muted` | `#98a2b3` | placeholder, nonessential metadata |
| `border-default` | `#eaedf2` | stream divider |
| `border-control` | `#e1e5eb` | input, icon button |
| `border-subtle` | `#eef1f5` | soft card, internal separator |
| `brand-accent` | `#ff6b6b` | `더보기`, World Feed kicker, mention, active underline·icon 같은 밝은 social inline action |
| `brand-accent-hover` | `#ff5252` | 밝은 social inline action hover·pressed |
| `brand-soft` | `#fff0ef` | selected nav, status chip background |
| `brand-soft-border` | `#ffb5b5` | selected filter border |
| `action-primary` | `#ff6b6b` | 만들기·켜기·게시하기처럼 긍정적인 primary CTA surface |
| `action-primary-hover` | `#ff5252` | positive primary CTA hover·pressed |
| `on-action-primary` | `#ffffff` | bright coral CTA 위 hosted-style label·icon · user-approved contrast exception `2.78:1` |
| `action-dark` | `#101828` | 끄기·중지·neutral confirm 같은 neutral strong action |
| `on-action-dark` | `#ffffff` | dark strong action 위 label·icon |

`#ff6b6b`은 Angmoo Local을 대표하는 유일한 공식 핵심 브랜드색이다. `#ff5252`·`#fff0ef`·`#ffb5b5`는 별도 브랜드색이 아니라 각각 hover/pressed, soft surface, soft border를 위한 파생 interaction/support token이다. 일반 text·metadata·score·avatar·graph·status·danger는 이 브랜드 예외를 상속하지 않고 각 semantic 역할을 사용한다.

### 5.1.1 Bright coral interaction hierarchy

2026-08-30 사용자 visual review에서 hosted angmoo.com의 밝은 `더보기`와 `만들기·켜기` button surface를 Local의 canonical interaction color로 채택했다. 역할은 다음처럼 고정한다.

| 사용자-visible 역할 | Semantic role | 결정 |
|---|---|---|
| `더보기`, mention, World Feed eyebrow·kicker, active inline link | `brand-accent` | `#ff6b6b` foreground |
| 만들기·켜기·게시하기·저장·계속 | `action-primary` + `on-action-primary` | `#ff6b6b` surface + white label/icon |
| 끄기·중지·neutral strong confirm | `action-dark` + `on-action-dark` | `#101828` surface + white label/icon |
| 삭제·영구 제거 | danger state token | coral primary로 위장하지 않음 |
| selected navigation·filter | `brand-soft` + `brand-accent` | soft surface와 bright coral foreground |

hosted의 bright coral 조합은 일반 글자 WCAG AA `4.5:1`을 충족하지 않는다. 흰 surface 위 `#ff6b6b` 및 `#ff6b6b` surface 위 white는 약 `2.78:1`, `#fff0ef` 위 `#ff6b6b`은 약 `2.51:1`, hover `#ff5252` 위 white는 약 `3.19:1`이다. 사용자는 이 사실을 인지한 상태에서 hosted와 같은 시각 표현을 우선해 다음 세 닫힌 목록을 명시적으로 선택했다.

| 예외 | 허용 범위 | 조합 |
|---|---|---|
| `EXCEPTION-A` | `더보기`, mention, World Feed kicker, 승인된 social inline action, `WORLD CHARACTER SETUP`과 동등한 autonomy section kicker, 양수 aggregate heart·count | white surface 위 `#ff6b6b` foreground |
| `EXCEPTION-B` | 만들기·켜기·게시하기·저장·계속 같은 positive primary CTA의 label·icon | `#ff6b6b` surface 위 white |
| `EXCEPTION-C` | selected Bottom Navigation, selected filter·indicator, 승인된 keyword chip | `#fff0ef` surface 위 `#ff6b6b` foreground |

세 조합은 `USER-APPROVED CONTRAST EXCEPTION`이며 **WCAG AA PASS가 아니다**. 예외는 일반 본문·metadata·score·avatar initial·Relationship Graph label/node·status·warning/error·danger·disabled·generic link·focus-visible로 확대하지 않는다. focus-visible, keyboard, disabled 구분, accessible name, 44px touch target, 상태의 색 외 단서는 계속 필수다. `#ffb5b5`는 selected border나 focus 보조 halo로만 쓰며 유일한 focus-visible 신호가 될 수 없다. PR·release 문서에서 세 예외를 WCAG AA contrast PASS라고 기록해서는 안 된다.

`#ae2f34`는 더 이상 social inline action이나 positive primary CTA의 canonical 값이 아니다. 기존 occurrence는 한 번에 raw replace하지 않고 dedicated token·consumer migration에서 제거한다. 이 문서 변경만으로 현재 화면이 바뀐 것으로 간주하지 않으며, 후속 구현은 최소 다음을 함께 닫는다.

1. `shared/ui/semantic-tokens.css`의 primary·on-primary 역할 분리
2. shared `Button` primary background·foreground·hover 갱신
3. Social `더보기`·World Feed kicker·inline action을 `brand-accent`로 전환
4. dark stop/off action과 danger action의 의미 분리 유지
5. Next/static/Tauri visual·contrast·focus·disabled 회귀 검증

### 5.2 Semantic states

| State | Foreground | Surface | Border |
|---|---:|---:|---:|
| success/healthy | `#147a45` | `#f0fbf5` | `#d9f2e5` |
| running/info | `#175cd3` | `#eff8ff` | `#b2ddff` |
| warning/waiting | `#b54708` | `#fffaeb` | `#fedf89` |
| degraded | `#6941c6` | `#f4f3ff` | `#d9d6fe` |
| danger/error | `#c24141` | `#fff5f5` | `#ffd7d7` |
| disabled | `#98a2b3` | `#f2f4f7` | `#e1e5eb` |

상태 이름과 backend typed value를 1:1로 문서화한다. UI가 color만 보고 상태를 역추론하지 않는다.

### 5.3 raw color 규칙

- 새 raw color 증가: `0`
- 수정한 component의 반복 raw color는 semantic token으로 이동
- 기존 raw color는 PR별 baseline을 기록하고 감소
- media-derived gradient, chart data color, third-party provenance처럼 필요한 예외만 allowlist
- allowlist에는 파일, 값, 이유, owner, 제거 또는 review 조건을 기록

첫 L4.5 PR에서 기존 raw color 전체를 한 번에 `0`으로 만들 필요는 없다. 기능과 무관한 대량 치환보다 review 가능한 감소를 우선한다.

---

## 6. Typography

### 6.1 Font policy

기본 stack은 offline에서 동작하는 Korean-safe system UI다.

```css
ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
"Segoe UI", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif
```

- remote font URL을 build/runtime 필수 dependency로 두지 않는다.
- Quicksand는 전체 한국어 UI 기본 font가 아니다.
- 영문 wordmark에 Quicksand를 쓰려면 font를 self-host하고 license·attribution·fallback을 확인한 별도 승인이 필요하다.
- emoji·CJK fallback으로 layout이 무너지지 않아야 한다.

### 6.2 Type roles

| Role | Phone baseline | Weight | Line height | 용도 |
|---|---:|---:|---:|---|
| `display` | 36px | 800 | 44px | 제한된 profile hero·empty hero |
| `page-title` | 28px | 800 | 36px | Feed·내 앵무·설정 화면 제목 |
| `section-title` | 24px | 800 | 32px | reply count·major section |
| `card-title` | 20px | 800 | 28px | summary card·dialog |
| `feed-author` | 18px | 800 | 24px | author name |
| `feed-body` | 18px | 500~700 | 28px | post body |
| `body` | 16px | 400~600 | 24px | 일반 설명·form |
| `body-small` | 15px | 500~700 | 24px | compact panel |
| `meta` | 14px | 600~800 | 20px | handle·time·counter |
| `label` | 13px | 700~800 | 18px | chip·field label |
| `caption` | 12px | 600~800 | 16px | 보조 상태·eyebrow |

긴 한국어 본문은 `word-break: keep-all`만 강제해 overflow를 만들지 않는다. 일반 문장은 적절한 `overflow-wrap`, ID·URL은 `break-all` 또는 전용 code style을 사용한다.

---

## 7. Spacing, shape, elevation, motion

### 7.1 Spacing

4px base grid, 8px dominant rhythm을 사용한다.

```text
4  micro gap
8  icon/label, compact stack
12 control group
16 Phone horizontal gutter
20 dense section padding
24 standard card/section padding
28 spacious stream padding
32 major section gap
48 hero separation
```

Phone 기본 horizontal gutter는 16px이며, post stream은 full-bleed divider를 위해 row 내부 padding으로 적용한다.

### 7.2 Radius

Tailwind 이름보다 component 역할로 정의한다.

| Role | Radius |
|---|---:|
| compact menu/control | 8px |
| field/textarea | 18px |
| reference card | 20px |
| card/panel | 24px |
| dialog | 28px |
| feature/empty card | 32px |
| pill/avatar/icon circle | 9999px |

모든 input을 pill로 만들지 않는다. 단일 행 search·filter·compact action은 pill을 사용할 수 있고, form input·textarea는 읽기와 편집 면적에 맞는 radius를 사용한다.

### 7.3 Elevation

| Layer | 표현 |
|---|---|
| primary stream | shadow 없음, divider 사용 |
| sticky header/bottom nav | white 95% + backdrop blur + 얇은 border |
| summary card | subtle border, 필요한 경우 아주 약한 neutral shadow |
| dialog | dim overlay + 명확한 neutral shadow |
| primary CTA | 제한된 brand-tinted shadow 허용 |
| Device frame on desktop Browser | 한 번만 neutral shadow |

Glass effect를 모든 card에 적용하지 않는다.

### 7.4 Motion

- 기본 transition: color·opacity·transform 120~180ms
- active press: 최대 `scale(.97)`
- layout을 크게 흔드는 spring·parallax는 사용하지 않음
- `prefers-reduced-motion: reduce`에서 불필요한 animation 제거
- loading은 motion 없이도 상태를 이해할 수 있어야 함

---

## 8. Shared component contracts

공통 component는 최소 다음 상태를 소유한다.

```text
default
hover
active/pressed
focus-visible
disabled
loading
error where applicable
Phone behavior
```

### 8.1 PageHeader

- Phone 높이 약 72px, wide workspace는 정보량에 따라 확장 가능
- left: back 또는 title context
- center logo는 진입 화면에서만 선택적으로 사용
- right: refresh 또는 하나의 primary action
- sticky + translucent surface
- icon-only control은 accessible name 필수

### 8.2 BottomNavigation

- Phone Device에서 고정
- safe-area bottom 포함
- item당 최소 44×44px touch target
- active item은 `brand-soft` surface와 `brand-accent` icon
- 항목이 많으면 가로 overflow를 허용하되 현재 route를 보이게 함
- route 목록은 hosted를 복사하지 않고 Local product navigation에서 결정
- static router가 처리하지 않는 link를 조용히 노출하지 않음

UI-C 현재 제품 destination은 `홈 /`, `피드 /posts`, `내 앵무 /agents`,
`설정 /settings` 네 개다. 이 목록은
`features/device-shell/model/device-navigation.ts`가 소유하며 현재 route에
정확히 하나의 `aria-current`를 제공한다.

### 8.3 Button and IconButton

- Positive primary text button: hosted bright coral `action-primary` + white `on-action-primary` · user-approved contrast exception
- Neutral strong action: dark navy `action-dark` + white `on-action-dark`
- Secondary: white + control border + strong text
- Ghost: transparent, hover surface
- Danger: danger foreground/background을 exact-scope copy와 함께 사용
- disabled는 opacity만 낮추지 말고 cursor·label·aria state를 제공

### 8.4 Form controls

- label은 field 밖에서 항상 식별 가능
- placeholder는 label 대체 금지
- 최소 control 높이 44px, 주요 action 48px
- focus-visible ring은 border와 별도로 인지 가능
- validation error와 runtime error를 구분
- time range는 locale label과 실제 timezone을 함께 설명

### 8.5 Stream row and Card

두 패턴을 혼동하지 않는다.

```text
chronological social stream
→ full-bleed white row + bottom divider + hover/focus background

summary, diagnostics, setup group
→ bordered rounded card or tonal panel
```

Feed post마다 독립된 큰 floating card를 쌓지 않는다.

### 8.6 Avatar, Badge, Status

- Avatar는 원형, image가 없으면 deterministic initial과 색 사용
- image alt는 문맥에 따라 이름 또는 decorative empty alt
- status chip은 짧은 명사/동작형 label 사용
- runtime 상태는 color + icon + text
- hosted의 `서버 LLM` badge를 Local에 그대로 복사하지 않음

### 8.7 Dialog, Toast, StatePanel

- Dialog는 focus trap·Escape·backdrop close 정책을 명시
- destructive dialog는 대상과 scope를 다시 표시
- toast는 보조 피드백이며 유일한 오류 전달 수단이 아님
- degraded/retry panel은 원인 추측보다 typed state와 가능한 다음 행동을 표시

---

## 9. Social core visual contract

### 9.1 World Feed

World Feed는 hosted Feed의 성숙한 anatomy를 Local World scope에 맞게 사용한다.

구조:

```text
sticky World Feed header
optional capability-backed filter/tabs
compact owner composer
timeline
  post row
  post row
  ...
bottom World navigation
```

현재처럼 큰 설명·composer card가 첫 viewport 대부분을 점유하지 않는다. World 이름과 scope는 header 또는 compact context row에서 분명히 보인다.

각 post row:

```text
avatar
author name · optional handle · local time
body/title
optional media
capability-backed action strip
divider
```

- avatar 48px baseline
- author 18px extra-bold
- body 18px/28px
- 긴 본문은 정해진 line clamp 뒤 bright `brand-accent`의 `더보기`
- image는 원본 비율을 보존하되 single hero media의 기본 frame은 4:3 후보
- mention은 brand accent와 accessible link style
- keyboard focus에서 전체 row navigation이 보임
- 내부 link/button/text selection과 row navigation이 충돌하지 않음

### 9.2 Manual composer

Global Feed의 상단 composer는 캐릭터의 다음 자율활동 주제를 주는 **Feed Cue**이고, World Feed composer는 owner-controlled 앵무가 현재 `worldId`에 즉시 저장하는 **direct post**다. 두 작성부는 avatar·author·white flat row·thin divider·compact control이라는 시각 anatomy만 공유하며 API·payload·행동 의미를 공유하지 않는다.

- hosted의 `모이 주기` 의미나 Global Feed Cue endpoint를 World Feed로 복사하지 않는다.
- provider 즉시 호출이나 autonomy ON을 암시하지 않는다. World direct write의 provider call은 `0`이다.
- owner actor가 있고 `postId`가 없는 World Feed 목록에서는 작성부를 게시글보다 위에 항상 표시한다.
- World post detail에는 root composer를 표시하지 않고 기존 reply composer만 유지한다.
- 현재 Local write 계약이 요구하는 제목·본문을 분리해 보존한다.
- 화면의 `제목`·`내용` 문구는 숨기되 실제 `label`과 input `id`로 accessible name을 유지한다.
- 제목 placeholder는 `오늘 이 World에 남길 이야기의 제목을 적어주세요`, 본문 placeholder는 `내가 조종하는 앵무의 말로 이야기를 적어보세요`로 고정한다.
- 기존 owner profile의 avatar와 display name만 표시하며 존재하지 않는 handle은 만들지 않는다.
- 제출 중 중복 submit 방지와 idempotency 상태를 유지한다.
- 성공 후 title/body를 비우고 timeline을 갱신하되 작성부는 계속 mount한다. 실패하면 입력값과 같은 idempotency key를 보존한다.
- 진입 시 input을 자동 focus하지 않는다. keyboard 순서는 title → body → `게시하기`이며 독립적인 focus-visible을 유지한다.
- empty Feed에 중복 `첫 글 쓰기` action을 만들지 않는다.

### 9.3 Action strip

시각 slot은 reply, repost, like, share 계열의 hosted rhythm을 계승할 수 있으나 link·button·read-only metric의 의미를 명시적으로 분리한다. payload에 없는 수치를 임의의 `0`으로 만들지 않으며, required aggregate가 누락되거나 음수·비정수이면 fail-closed한다.

L4.5 UI-D 기준:

- reply: 실제 detail route가 있는 link로 표시하고 payload의 authoritative `reply_count`를 `0`까지 항상 보인다. accessible name은 `대꾸 N`이다.
- like: payload의 authoritative `like_count`를 표시하는 focus되지 않는 read-only metric이다. `0`이면 neutral outline heart와 `0`, 양수이면 coral filled heart와 실제 수치를 보인다. accessible name은 `좋아요 N`이다.
- like metric에는 `button`, `href`, `onClick`, `aria-pressed`, pointer mutation cue, optimistic increment를 만들지 않는다. 이는 viewer-liked 상태가 아니다.
- icon은 `aria-hidden`이고 count와 의미는 container의 accessible name이 소유한다.
- repost/follow/share: 실제 capability와 cross-runtime route가 없다면 숨긴다.
- 최신 count snapshot은 initial GET, refresh, detail navigation, owner reply 성공 뒤 재조회로 갱신한다. WebSocket·polling은 이번 계약이 아니다.

### 9.4 Post detail and reply thread

- sticky back/title/refresh header
- original post는 full-bleed hero row
- `대꾸 N` section heading
- top-level reply는 divider로 구분
- nested reply는 indentation과 vertical guide로 parent 관계 표시
- reply author·time·body hierarchy는 Feed와 동일
- thread depth가 깊을 때 Phone 폭을 소모하지 않도록 flatten/summary 정책을 명시
- delete/report는 Local capability와 owner scope에 따라 노출

### 9.5 Feed states

별도 표현:

- loading: skeleton 또는 compact loading row
- empty: “이 World에 아직 게시글이 없음” + 가능한 다음 행동
- forbidden: owner/World permission 설명
- not found: World/post가 없거나 제거됨
- offline: runtime 연결 실패와 retry
- degraded: 읽기는 가능하나 graph/projector 등 일부 기능이 제한됨

---

## 10. Character and autonomy contract

### 10.1 Character profile

hosted profile의 다음 hierarchy를 계승한다.

1. banner
2. 겹치는 원형 avatar
3. context-aware action cluster
4. name·handle·mode/status·한 줄 소개
5. 실제로 존재하는 social/World metric
6. content tabs
7. 동일 PostRow 기반 stream

Local action은 follow/message를 무조건 복사하지 않는다. owner 여부와 World capability에 따라 `채팅`, `World 보기`, `활동 설정`, `관계망`, `관리` 등 실제 동작만 표시한다.

### 10.2 내 앵무

hosted Agent dashboard의 visual hierarchy를 계승하되 Local 의미로 바꾼다.

- sticky title + refresh + create
- flat separated Character rows
- avatar·name·handle·status
- autonomy ON/OFF
- active hours·next activity·last result·runtime state metric
- 여러 Character가 동시에 active일 수 있음
- World 참여와 전역 Character identity를 구분

`최근 결과` compact dashboard 표현은 다음 계약을 따른다.

- `features/characters`가 소유하는 pure presenter가 action type을 짧은 사용자용 label·headline으로 바꾼다.
- `최근 결과`는 `활동 시간`·`다음 활동` 아래에서 전체 metric 폭을 쓰며, headline은 compact한 두 줄 범위로 제한한다.
- 시각은 저장 instant를 그대로 출력하지 않고 payload의 World timezone으로 변환한 `<time>`으로 표시한다.
- 실제 결과 link는 API가 명시한 authoritative `target_post_id`가 있을 때만 canonical `/posts/{id}`로 만든다.
- raw `result` JSON·영문 message·internal ID·`created_post_id`·`topic_signature`·novelty·lore·retrieval metadata를 compact dashboard의 text, accessible name, tooltip 또는 route source로 사용하지 않는다.
- unknown·malformed action type은 raw fallback 없이 `활동 기록이 업데이트됐어요.` 같은 generic fail-closed summary로 축소한다. `result`가 malformed JSON이거나 장문이어도 presenter는 이를 parse하지 않으며, known action이면 안전한 action별 요약을 그대로 사용한다.
- recent activity가 없으면 `last_activity_at`이 있는 historical fallback과 완전히 비어 있는 상태를 구분한다.

금지:

- hosted의 계정당 `3 + 3` quota 재도입
- 한 Character를 켤 때 다른 Character를 끄는 UI state update
- `서버 LLM`/`외부 실행기`를 Local runtime 분류처럼 복사
- World당 50개 capacity와 account 전체 저장 Character 수를 혼동

### 10.3 Autonomy state

다음 항목은 한 화면에서 의미가 섞이지 않아야 한다.

```text
사용자 설정: ON/OFF, active hours, interval, daily limits
scheduler state: scheduled, due, running, retrying, failed
provider state: ready, missing credential, rejected, rate-limited
last activity: success/failure/time/result link
next activity: World timezone을 반영한 local display
```

시간은 저장 instant와 표시 timezone을 구분한다. `다음 활동`은 UTC 문자열을 그대로 노출하지 않는다.
`last activity`의 성공/failure 의미는 action·scheduler state가 소유하며 raw `result` 문자열을 해석해 추측하지 않는다. runtime `last_error`는 최근 결과와 별도의 danger panel로 유지한다.

---

## 11. Local-only surface contract

### 11.1 Device Home

- 앱 launcher 역할을 유지
- Settings·Creator Studio·World 앱을 icon grid 또는 명확한 list로 표시
- World launchability와 runtime state를 별도 badge로 표시
- unavailable app을 clickable한 것처럼 꾸미지 않음
- future feature를 기본 navigation에 과도하게 쌓지 않음
- Browser에서는 한 번의 Device frame, Tauri에서는 frame 중첩 없음

### 11.2 World App

- World identity와 Device Home 복귀가 header에 항상 보임
- `Home / Feed / Chat / Characters / Relationships`의 Local IA 유지
- hosted global nav label을 복사하지 않음
- current World scope를 route와 UI에서 fail-closed로 유지
- Chat·Characters가 아직 미구현이면 명시적 unavailable state, 가짜 화면 금지

### 11.3 Creator Studio

- 현재 구현된 wide workspace 예외
- Device와 같은 token·button·form·state vocabulary 사용
- 정보 밀도를 위해 wide layout을 쓰되 Device responsive 규칙을 변경하지 않음
- Character create/link/World-local leave는 exact scope를 명시
- package import/export는 source와 runtime data 경계를 설명

### 11.4 Relationship Graph

- 현재 구현된 wide workspace 예외
- direction, World scope, evidence를 색만이 아니라 label·arrow·text로 표현
- ready와 empty, degraded, rebuilding, unavailable을 분리
- fallback data를 정상 graph처럼 표시하지 않음
- Device에는 요약과 진입점만 두고 graph 전체를 좁은 Phone에 억지로 넣지 않음

### 11.5 Future Local surfaces

Memory, Diagnostics, Backup·Restore는 이 token과 state vocabulary를 재사용한다. 그러나 해당 단계 전에 route·window kind·data contract를 미리 구현된 것으로 간주하지 않는다.

---

## 12. Navigation, route, and static-export contract

### 12.1 One component source

동일 feature component가 다음에서 사용돼야 한다.

```text
Next.js App Router page wrapper
Tauri static manual route wrapper
Docker/Next Browser
Host Tauri dev
Windows installer
```

Browser용 `WorldSocialFeed`와 Tauri용 `WorldSocialFeed`를 따로 만들지 않는다.

### 12.2 Static-safe UI

Tauri static UI는 route별 물리 HTML이 아니라 하나의 static shell과 client router를 사용한다. 공통 UI는 다음을 전제로 하면 안 된다.

- runtime SSR 필수
- Next image optimizer 필수
- remote build font·asset
- browser-only navigation API 직접 호출
- dynamic route의 물리 HTML 존재
- sibling hosted/private repository runtime access

navigation은 Local의 runtime navigation adapter를 사용한다.

### 12.3 Route capability matrix

새 bottom navigation 또는 link를 추가하기 전에 각 route를 다음 중 하나로 판정한다.

```text
A. Next + Tauri static 모두 구현
B. Phone navigation에서 숨김
C. 명시적 disabled/unavailable entry
D. 안전한 외부 Browser destination
```

static router가 처리하지 않는 route를 visual parity 때문에 그대로 노출하지 않는다. broken route가 있으면 shell Gate는 FAIL이다.

UI-C의 현재 판정:

- bottom navigation 네 route는 Next와 static에서 모두 지원한다.
- World App과 World Post detail은 Phone direct route다.
- Creator Studio와 Relationship Graph는 각각 `studio`와
  `relationship-graph` wide window다.
- search·notifications·messages·profiles·tree·licenses·API guide는
  Next-only이므로 Local Phone navigation에서 숨긴다.
- `/worlds/new`와 `/worlds/{worldId}/creator`는 canonical Studio route로
  먼저 정규화하며, `new`를 동적 World ID로 해석하지 않는다.

### 12.4 Cross-window navigation

- Phone→Studio: `studio` window
- Phone→Relationship Graph: `relationship-graph` window
- wide→Phone 복귀: 원래 Phone route를 안전하게 복원하거나 명시적 복귀 action 제공
- route mismatch는 Device Home으로 조용히 fallback하지 않고 error boundary로 표시
- query와 return route는 allowlist·same-origin·window-kind 검증을 통과해야 함

---

## 13. Media and avatar

- runtime media URL은 Local sidecar/Tauri adapter를 거쳐 해석
- hosted `/media/` resolver를 무검토 복사하지 않음
- remote build-time asset dependency 금지
- image load failure는 layout collapse 없이 fallback
- avatar는 1:1 crop, banner는 목적에 맞는 aspect ratio
- post single media는 큰 rounded frame, multiple media는 일관된 grid
- user content는 intrinsic size와 lazy loading을 고려
- alt text는 정보성/장식성을 구분
- EXIF·privacy·local path 노출은 media domain 계약을 따름

---

## 14. Accessibility

최소 Gate:

- 일반 text contrast WCAG AA — 단, positive primary CTA의 white label은 아래 `USER-APPROVED CONTRAST EXCEPTION`
- 44×44px touch target
- keyboard로 모든 interactive control 접근
- focus-visible이 hover와 별도로 보임
- icon-only button에 accessible name
- `aria-current`, `aria-live`, `role=alert/status`의 의미 있는 사용
- modal focus trap·return focus
- 색 외의 status 단서
- 200% zoom에서 기능 손실 0
- reduced motion 대응
- 긴 한국어·영문 ID·URL overflow 0
- screen reader reading order와 visual order 일치
- disabled control만으로 필수 정보를 숨기지 않음

Positive primary CTA는 hosted와 같은 `#ff6b6b` surface + white `on-action-primary`를 사용한다. 이 조합은 contrast `2.78:1`의 `USER-APPROVED CONTRAST EXCEPTION`이며 WCAG AA contrast PASS로 간주하지 않는다. 나머지 accessibility Gate는 그대로 유지한다.

---

## 15. Visual verification matrix

### 15.1 Fixed viewports

```text
360 × 800   compact Android Phone
390 × 844   modern Phone
436 × 880   Angmoo Browser Device frame baseline
1440 × 1000 desktop Browser with centered Phone
1440 × 900  Creator Studio wide
1440 × 900  Relationship Graph wide
```

Windows Tauri:

```text
100% display scale
125% display scale
150% display scale
Phone default size
Phone user resize
```

### 15.2 Required routes

- Device Home
- World Home
- World Feed
- World Post detail·reply
- 내 앵무
- Character create·detail·profile
- autonomy setup
- Settings current scope
- Creator Studio list·World edit·create·import
- Relationship Graph
- login/local owner gate
- static not-found·window mismatch

### 15.3 Required states

- normal data
- long Korean
- media 0·1·many where supported
- loading
- empty
- validation error
- 403
- 404
- backend offline
- scheduler failed
- graph degraded
- retrying
- disabled
- scheduled/running

Visual screenshot는 deterministic fixture를 사용한다. intentional baseline update는 PR에서 이유와 before/after를 review한다. screenshot만으로 기능 PASS를 주장하지 않고 route·API·interaction test와 함께 사용한다.

---

## 16. Implementation rules

사용자에게 보이는 frontend를 수정하기 전에 다음을 수행한다.

1. 관련 기능 계획과 이 `DESIGN.md`를 읽는다.
2. surface가 Phone인지 현재 구현된 wide workspace인지 확인한다.
3. shared token·primitive·presentation component를 먼저 찾는다.
4. hosted reference가 `DIRECT`, `ADAPTED`, `LOCAL`, `REJECTED` 중 무엇인지 기록한다.
5. payload capability와 route parity를 확인한다.
6. loading·empty·forbidden·not found·degraded·error를 분리한다.
7. Next Browser와 Tauri static route에서 같은 component를 검증한다.
8. visual diff와 behavior non-regression을 함께 남긴다.

UI-A의 reference·provenance·inventory와 UI-B의 token·primitive·fixture·visual baseline은 다음 명령으로 검증한다.

```bash
uv run --project backend python scripts/ci/check_frontend_design_contract.py --check
```

시각 회귀 검증은 저장소 루트의 기존 `browser-tests` Playwright 1.62.1 harness를 canonical 기반으로 확장한다. frontend package 아래에 중복 harness·별도 browser dependency graph를 만들지 않는다.

금지:

- page-local raw color·spacing·button 복제 증가
- hosted auth·quota·admin·single-active semantics 재유입
- UI 이식을 이유로 backend·schema·scheduler 의미 변경
- sibling hosted/private repository runtime import
- static route 없는 clickable nav
- 작동하지 않는 action을 `0` count로 표시
- Tauri/Browser feature fork
- 계획 또는 screenshot만으로 `FRONTEND COMPLETE` 판정

### 16.1 Provenance

hosted 구현을 이식할 때 PR에 다음을 기록한다.

- source repository와 commit
- 참고한 source file
- Local target component
- `DIRECT` 또는 `ADAPTED` 판정
- 제거한 hosted-only dependency
- asset·font·icon license와 attribution 영향

코드는 현재 Local repository가 소유한다. private path가 없어도 clean clone과 CI가 build·review 가능해야 한다.

---

## 17. Frontend PR checklist

- [ ] 이 `DESIGN.md`를 읽고 영향 surface를 기록했다.
- [ ] hosted adoption 등급을 기록했다.
- [ ] 새 raw color 증가가 없다.
- [ ] shared component를 우선 재사용했다.
- [ ] capability에 없는 action을 노출하지 않았다.
- [ ] World·owner·destructive scope를 보존했다.
- [ ] Phone에서 left/right rail이 나타나지 않는다.
- [ ] scroll owner가 하나다.
- [ ] safe-area와 44px touch target을 확인했다.
- [ ] keyboard·focus-visible·contrast를 확인했다.
- [ ] loading·empty·error·degraded를 구분했다.
- [ ] Next build와 static build를 모두 확인했다.
- [ ] static router와 Next route parity를 확인했다.
- [ ] fixed viewport screenshot을 갱신·review했다.
- [ ] Tauri Phone과 필요한 wide window를 smoke했다.
- [ ] backend·API·schema·scheduler 의미 diff가 없다거나 별도 승인으로 분리됐다.
- [ ] provenance와 license 영향을 기록했다.

---

## 18. 현재 conformance와 목표 판정

UI-E recent-result follow-up local technical snapshot 시점의 현재 상태:

- global Feed·Post detail과 World Feed·World-scoped detail이 feature-owned `SocialPostRow`와 하나의 social presentation 계약을 공유한다.
- Local `WorldSocialFeed`는 큰 검증용 form/card나 접힘 토글 대신 compact World context·항상 보이는 owner composer·flat divided timeline을 사용한다.
- `shared/ui/semantic-tokens.css`가 palette·text·border·action·state·type·spacing·radius·elevation·motion의 semantic source of truth를 제공하며 `globals.css`의 기존 Tailwind alias도 같은 역할로 연결한다.
- `shared/ui/public.ts`를 통해 Button·form control·surface·Avatar·Badge·StatusChip·Tabs·PageHeader·BottomNavigation·Dialog·feedback state primitive를 공개한다.
- World Package export/import가 실제 shared primitive 소비자로 전환됐고 기존 `ProfileAvatar`·`StatusBadge`는 compatibility bridge로 새 primitive를 사용한다.
- Device Home·World App·일반 compatibility route는 하나의 feature-owned `DeviceShell`로 수렴했고 Creator Studio와 Relationship Graph는 dedicated wide shell을 유지한다.
- Social core는 payload와 실제 capability가 소유한 handle·avatar·media·action·count만 표시한다. read 응답의 authoritative `reply_count`·`like_count`는 실제 `0`까지 표시하고, payload에 없는 repost·follow·mutation capability나 count는 만들지 않는다.
- `features/characters/public.ts`가 Next와 static/Tauri의 `/agents` dashboard를 함께 소유하고, 여러 Character의 독립 ON/OFF·scheduler 상태·active hours·World timezone next activity·recent result를 shared primitive로 표시한다. feature-owned recent-activity presenter는 raw result payload를 읽지 않고 사용자용 action summary와 authoritative `target_post_id` link만 제공한다. legacy `components/agents-dashboard-client.tsx`는 compatibility export만 유지한다.
- Character activity control/list, Studio World-local leave, Device Home launchability, runtime state, Relationship Graph state, Settings와 local-owner surface의 UI-E 범위가 semantic token·shared component·capability-driven state로 수렴했다. public/World 작성자를 owner 전용 `/agents/{id}`로 잘못 연결하지 않는다.
- raw style 기준선은 UI-A placeholder 59 files·1,938 occurrences에서 UI-B 56 files·1,894 occurrences, UI-C 53 files·1,860 occurrences, UI-D 후속 50 files·1,794 occurrences를 거쳐 UI-E checker 측정 42 files·1,496 occurrences로 감소했다. 이 수치는 남은 migration inventory이지 전역 conformance PASS가 아니다.
- `features/device-shell/model/device-navigation.ts`가 Local Phone route capability를 소유하고 Next-only destination을 fail-closed로 숨긴다.
- `/agents`, `/studio/import`, World Post detail direct-open과 두 legacy Studio alias의 static/window parity가 코드와 functional contract에 반영됐다.

### 18.1 UI-B local technical evidence

- feature-first deterministic fixture는 `features/ui-foundation`이 소유하며 Next와 static exact route `/ui-foundation`이 같은 component를 렌더링한다. 이 route는 `noindex`·unlinked test fixture이고 제품 navigation destination이 아니다.
- BottomNavigation fixture는 button-only local state·touch·overflow·단일 `aria-current`만 검증한다. 실제 product `href`·capability·route parity는 UI-C 소유다.
- canonical visual baseline은 digest-pinned `mcr.microsoft.com/playwright:v1.62.1-noble` Ubuntu 24.04 container·Playwright 1.62.1 Chromium에서 436×880, DPR 1, `ko-KR`, `Asia/Seoul`, light color scheme, reduced motion으로 고정한다. Core CI host의 font package 차이가 baseline을 바꾸지 않도록 container digest까지 contract로 검사한다.
- Next production과 static export는 `browser-tests/snapshots/ui-b/semantic-foundation-phone.png` 한 장을 공유하며 pixel parity와 keyboard·focus·contrast·dialog·reduced-motion behavior를 함께 검증한다.
- fixture asset은 first-party `/icon.svg`만 사용하고 remote font·image·runtime network dependency를 만들지 않는다.
- UI-B는 backend·API·schema·migration·scheduler 의미, 제품 shell·route destination, social presentation, Local-only 전체 화면을 변경하지 않았다.
- UI-A와 UI-B는 merge 및 post-merge Gate를 통과했다.

### 18.2 UI-C closeout and remaining Windows scale Gate

- neutral `DeviceFrame`은 frame과 단일 scroll owner만 제공하고 product route를 선택하지 않는다.
- `features/device-shell`이 page-owned optional header slot, safe-area bottom navigation, Browser 중앙 Phone, 모바일·Tauri full-viewport Phone을 소유하며 compatibility shell이 페이지 위에 generic header를 중복 주입하지 않는다.
- Tauri Phone은 page-owned header 유무와 관계없이 native 창 이동·최소화·닫기 controls 아래에 최소 44 CSS px의 titlebar exclusion 영역을 예약한다. 핵심 CTA·상태 badge·텍스트는 이 영역과 겹치면 안 된다.
- Phone·Creator Studio·Relationship Graph 제품 shell은 각각 `main` landmark를 하나만 소유하고, 내부 page/client는 `section` 또는 `div` content container를 사용한다.
- static/Tauri에서 지원하지 않는 Next-only 목적지는 클릭 가능한 모양을 유지하지 않는다. `aria-disabled`·unavailable 안내·비활성 cursor/color를 함께 제공하고 상위 clickable row로 event가 전파되지 않게 한다.
- 기존 `AppShell`은 `DeviceShell`에 위임하는 compatibility facade이며 hosted three-column rail을 더 이상 렌더링하지 않는다.
- `LocalProductLink`는 Next-only profile·message·hosted 문서 destination을 static/Tauri에서 inert presentation으로 축소해 clickable not-found route를 노출하지 않는다.
- Feed·Character profile pagination과 pull-to-refresh는 단일 Device scroll owner를 우선 사용하며 shell 없는 compatibility 화면에서만 `window` fallback을 사용한다.
- Rust Phone allowlist가 `/agents`와 `/worlds/{worldId}/posts/{postId}`를 수용하고 reserved World ID `new`를 거부한다.
- Relationship Graph는 `RelationshipGraphFrame`을 통해 wide window를 유지하고 Phone frame을 중첩하지 않는다.
- static direct-open·반복·빈 query를 보존하는 alias canonicalization·Phone fixed-width·overflow·navigation·inner-scroll pagination·unsupported-link assertions을 기존 Playwright graph에 추가하되 UI-B screenshot은 한 장으로 유지한다.
- UI-C는 local technical·Hosted CI·사용자 merge·post-merge Gate와 Windows 100%·125%·150% WebView scale 사용자 확인을 통과했다. UI-F 최종 exact-SHA의 네 실행 경로와 Windows scale 재확인은 별도 최종 Gate다.

### 18.3 UI-D0 closeout and UI-D local technical evidence

- UI-D0는 static `/posts/{postId}`가 async thread/error 결과를 확정하기 전에 `PostDetailClient`를 mount하지 않는 composition-owned ready Gate를 고정했다. post identity가 바뀌면 child를 remount하고 stale response를 버린다.
- UI-D0는 merge와 post-merge Actions까지 닫혔으며 UI-D는 그 exact merge를 base로 한다.
- `features/social/public.ts`가 product-neutral `SocialPostPresentation`, `SocialPostActionPresentation`, `SocialPostRow`와 canonical global detail API를 공개한다.
- global Feed·Post detail과 World Feed·World detail·reply는 같은 row anatomy를 사용하지만 endpoint 권한은 섞지 않는다. World adapter는 `/worlds/{worldId}/manual-social/**`만 사용하고 global adapter는 `/posts/{postId}/thread`를 사용한다.
- World payload는 exact World·owner actor·root post·direct reply parent를 fail-closed로 검증한다. write 결과도 operation·World·owner·reply target·`provider_call_count = 0`을 확인한 뒤에만 성공으로 표시한다.
- paired Next/static World 회귀는 항상 보이는 compact owner composer, 분리된 제목·본문, 정확한 World-scoped write·idempotency·성공/실패 상태, long-text expansion, text-selection-safe post keyboard navigation, 실제 World reply write, 403·404·503·scope mismatch·retry를 고정한다. static 회귀는 media 0·1·2·3·4+와 top-level/nested global reply를 추가로 고정하고, UI-D0 회귀는 global delayed load·offline·Feed click/Enter/Space·post identity를 소유한다. loading·empty 표현은 구현 계약에 존재하지만 확장된 cross-runtime state·visual corpus는 UI-F에서 닫는다.
- 게시글 action과 option menu는 44px touch target을 유지한다. 실제 detail route가 있는 reply는 link로, authoritative `like_count`는 focus되지 않는 read-only metric으로 표현하고, payload/capability에 없는 like mutation·repost·follow는 숨긴다.
- UI-D와 UI-D0는 각 public lifecycle·사용자 Gate·merge·post-merge Actions까지 닫혔다. exact UI-D merge는 `3152aaee56a868e50abff943d6f14cf92cd45302`이며 UI-E는 이 SHA를 base로 시작했다.

### 18.4 UI-E local technical evidence

- `/agents`는 feature-owned flat Character rows와 shared `PageHeader`·`ListRow`·`ProfileAvatar`·`StatusChip`·`Button`·`Dialog`·feedback primitive를 사용한다. 한 Character의 mutation은 exact Character endpoint와 pending state만 바꾸며 다른 active Character를 끄지 않는다.
- 저장 instant는 UTC로 정규화하고 next activity·recent result는 payload의 World timezone으로 표시한다. Character 생성의 기본 active hours는 backend canonical `14:00–22:00`과 일치하며 현재 KST 시각에 따라 임의 변경하지 않는다.
- Studio의 `이 World에서 제거`는 exact confirmation name, 자율활동 정지, 현재 version 재조회, versioned leave 순서를 지키고 Character 자체·다른 World·기존 활동/사건/관계 근거 보존 범위를 안내한다.
- Device Home은 World launchability와 runtime health를 별도 state로 표시한다. unavailable World는 link가 아니며 runtime은 starting·ready·degraded·failed·recovery-required·stopping·stopped를 합치지 않는다.
- Relationship Graph는 ready·empty·degraded·rebuilding·unavailable·failed를 분리하고 canonical fallback 또는 lagging projection을 healthy LadybugDB로 표시하지 않는다.
- Settings/local owner는 installation ID·label·owner·local session을 표시한다. 공개 Local runtime에 없는 owner 전체 `DELETE /auth/me`는 노출하지 않고, Character 삭제·World-local leave·session 종료의 exact scope를 구분한다.
- UI-E의 최초 구현은 Issue #208·branch push·Draft PR #209와 pre-Hotfix exact-head Hosted CI까지 진행했다. 후속 Hotfix local technical 검증은 Next production build, Tauri static export, feature architecture/design checker, 전체 backend 회귀, Next/static Playwright와 Local Settings fail-closed 회귀를 포함한다. 후속 signed commit·같은 branch push·새 exact-head Hosted CI와 사용자 Ready·merge·post-merge Actions는 서로 별도 Gate로 남는다.

UI-E PR #209 후속 Hotfix는 사용자 visual에서 발견된 `최근 결과` raw JSON 노출만 frontend presentation 범위에서 교정한다. `CharacterRecentActivityPresentation`은 `action_type`·`created_at`·authoritative `target_post_id`만 신뢰하고 `result`를 사용자 문구나 route source로 읽지 않는다. 동일 Character component를 사용하는 Next와 static/Tauri 회귀는 production-shaped JSON·4,000자 내부 payload·malformed/unknown action·missing target·historical/empty fallback을 검증하며, visible JSON key·internal ID `0`, 360·390·436px overflow `0`, keyboard result-link route를 요구한다. backend·DB·API·scheduler·provider 의미 diff, 새 raw color·contrast exception, hosted code·asset·font 복사는 모두 `0`이다. 이 follow-up은 구현과 local technical Gate를 닫았지만, 새 exact-head Hosted CI와 사용자 recent-result visual 확인 전에는 Ready 또는 merge할 수 없다.

따라서 현재 허용되는 판정:

```text
ANGMOO LOCAL DESIGN CONTRACT ESTABLISHED
UI-A DESIGN CONTRACT CLOSEOUT PASS
UI-B SEMANTIC TOKEN·PRIMITIVE FOUNDATION PASS
UI-C PHONE SHELL·NAVIGATION·ROUTE PARITY PASS / MERGED / POST-MERGE PASS
UI-D0 STATIC POST DETAIL HANDOFF FULL PASS / MERGED / POST-MERGE PASS
UI-D SOCIAL CORE HOSTED PARITY FULL PASS / MERGED / POST-MERGE PASS
UI-E CHARACTER·AUTONOMY·LOCAL-ONLY SURFACE FOLLOW-UP IMPLEMENTED / LOCAL TECH PASS / EXACT-HEAD HOSTED CI PENDING / USER READY BLOCKED
UI-F VISUAL·CROSS-RUNTIME CLOSEOUT NOT STARTED
UI-C WINDOWS 100%·125%·150% SCALE USER GATE PASS / UI-F FINAL EXACT-SHA RECHECK PENDING
```

token·shell·social core·Local-only surface·visual/runtime Gate와 사용자 승인을 모두 통과한 뒤에만 허용되는 판정:

```text
ANGMOO LOCAL DESIGN FOUNDATION PASS
P10-L VISUAL FOUNDATION PARTIAL SLICE COMPLETE
```

그 뒤에도 별도 단계 없이 금지되는 판정:

```text
P10-L PASS
FRONTEND COMPLETE
LOCAL ALPHA PASS
RELEASE READY
PRODUCTION
```

---

## 19. 최종 원칙

> **angmoo.com의 모바일 UI는 버리는 과거 코드가 아니라 검증된 Angmoo 시각 유산이다. Feed·Post·Thread·Profile·Agent의 anatomy는 높은 수준으로 계승한다.**

> **그러나 hosted 서비스의 account·quota·auth·global SNS 의미는 계승 대상이 아니다. Local의 World scope·owner identity·다중 autonomy·runtime 상태·Tauri window 계약이 항상 우선한다.**

> **Local에만 있는 Device Home·World App·Creator Studio·Relationship Graph는 별개의 임시 디자인으로 남기지 않고, 같은 token·type·navigation·state 문법으로 만든다. 앞으로 L5~P10의 frontend도 이 문서를 읽고 같은 시스템에 합류한다.**
