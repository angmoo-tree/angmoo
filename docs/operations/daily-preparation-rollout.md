# 날짜별 하루 계획 로컬 기본 전환 — 2026-09-28

사용자가 기존 품질 사례를 구조 변경의 회귀라고 단정하기 어렵다는 점을 확인하고 로컬 전환을 명시적으로 요청했다. 이전 평가의 한계를 보존한 채 `DAILY_PREPARATION_ENABLED=True`를 기본으로 적용한다. 실제 AI 평가 전체 통과나 장기 자연 활동 품질 보장을 의미하지 않는다.

- 기존 World·키·ON/OFF·Topic·오늘 유효 계획과 과거 기록을 보존한다.
- 최초 일과+Topic, 이후 날짜 일과 전용 준비와 기존 SNS V2 네 단계 경로를 활성화한다.
- 기존 데이터 볼륨의 정지 백업 후 정식 v22→v23 upgrade. 기존 제품 137개 테이블의 기존 열/행 해시 보존, 변경은 스키마 버전 영수증, 준비 job 신규 0행. integrity ok, FK 위반 0.
- contributor Docker frontend/backend healthy, scheduler/projector ready. 설치 앱과 원격 환경은 변경하지 않았다.
- 기존 SNS 3캐릭터는 ON/14:00–24:00 유지. 전환 확인 시 활동 시간 밖이며 오늘 계획 pending/Topic ready. 강제 활동·새 평가·관찰 세션은 실행하지 않았다.
- 상세 설정 화면에서 daily_preparation을 구형 성향 분석으로 오분류하던 분기를 고쳤다. LOCAL 공용 UI이며 새 원격 시각 참조·색상 없음. 지원하지 않는 자동 행동 토글을 숨기되 과거 설정 저장값을 보존한다.
- 기본값 True에서 구 fixture 회귀 6건 실패를 기록한다. 기존 경로 False와 새 준비 True를 명시적으로 구분한 회귀 37건 통과. 전체 테스트의 새 기본값 일괄 통과로 표현하지 않는다.
- frontend lint/typecheck/구조/디자인·Next/static build 통과, 브라우저 Next 2건/static 2건 통과. 새 검사에서 fixture의 설정집 배열과 static trailing slash 기대를 수정한 이력은 workspace 결과에 남긴다.
- 실제 Edge의 Seraphina 설정과 활동 준비 화면에서 새 안내·pending 계획·유효 Topic·ON 상태 확인. 사용자 직접 검증·장기 실행 결과와 구분한다. 주요 변경 파일 4개의 로컬/컨테이너 해시 일치, 최종 frontend 이미지에도 수정 포함.

상세 백업/검증/한계/최종 커밋은 workspace `docs/plan/09-28 날짜별 하루 계획 새 구조 로컬 전환 실행 기록.md`에 있다. 백업과 원시 운영 자료는 저장소에 포함하지 않는다. 과거 frozen 테스트·체크포인트를 덮어쓰지 않는다.
