---
id: PAY-MP-001
task: FE-P0-1
status: blocked
owner: qa-agent-kuhn
role: qa-agent
scope: frontend
tested_at: 2026-08-12
---

# PAY-MP-001 FE-P0-1 独立前端 QA 报告

## Verdict

`blocked`。

在可执行的自动化与静态范围内，App 和 Admin 均未发现新的可复现产品代码失败；但 P0 支付主链路尚不能独立签署通过：支付轨配置仍存在开启风险，backend QA 当前为 `blocked-current-recheck`，且真实本地/测试后端、设备浏览器、3DS、键盘和屏幕阅读器未由本前端 QA 任务执行。未启用支付轨，也未操作生产系统或数据库。

## Tested fingerprint and scope

- Repository HEAD: `e169bff`。
- QA 开始时 working-tree：106 个 dirty/untracked 条目；已有改动全部保留。
- QA 开始时 `git diff --binary` SHA-256：`3751bf71d02eb9c48e1b8adc014f8bb4cb49c6cf44ccdb7ab41b5106d90c73dd`。
- `git diff --check`：通过。
- App 目标：React Native / Expo 54，TypeScript，Jest，Web bundle；未执行 iOS/Android 真机或模拟器 UI。
- Admin 目标：Next.js 16；执行 TypeScript、Webpack production build 和既有支付页 smoke；未修改 Admin 产品代码。
- 审查范围：FE-P0-1 交接列出的 App API、支付方式、Checkout coordinator、充电、支付结果、导航、三语言和测试文件；同时扩展到钱包充值、wallet/direct-card/free 充电、D1 欠费阻止、Reset Password Deep Link、共享 API client、共享支付组件及 Admin 支付页。

## Commands and exact results

| Area | Command | Result |
|---|---|---|
| App type safety | `cd app && npx tsc --noEmit` | PASS, exit 0, 0 errors |
| App full regression | `cd app && npm test -- --runInBand` | PASS, 41 suites / 169 tests passed, 0 failed |
| App web build | `cd app && npx expo export --platform web --output-dir /private/tmp/eslatin-app-export` | PASS, Web bundle 855 modules; exported to `/private/tmp/eslatin-app-export` |
| App diff hygiene | `git diff --check` | PASS |
| Admin type safety | `cd admin && npx tsc --noEmit` | PASS, exit 0 |
| Admin default build | `cd admin && npm run build` | BLOCKED by sandbox: Next/Turbopack failed while CSS processing attempted to bind a port (`Operation not permitted`); no application diagnostic was emitted |
| Admin build verification | `cd admin && npx next build --webpack` | PASS, compiled, TypeScript, static pages and route optimization completed |
| Admin payment smoke | `cd admin && npx vitest run 'app/(dashboard)/payments/__tests__/payments-nullable.integration.test.tsx'` | PASS, 1 file / 1 test |
| App static security/localization checks | targeted `rg` scans over payment, charging, navigation and i18n sources | PASS for no production App references to PAN/card-token form APIs; only legacy unused translation keys remain; no payment-related debug payload logging found in the reviewed FE-P0-1 paths |

App has no lint script in `app/package.json`; no separate App lint command was available to run.

## Regression matrix

| Surface | Evidence | Result |
|---|---|---|
| TypeScript and module integration | App and Admin type checks; App Expo Web bundle; Admin Webpack build | PASS |
| Payment-method canonical projection | credit/debit/prepaid/null/invalid runtime fixtures, shared label mapping, PaymentMethods and PaymentMethodBar tests | PASS in automation |
| Single-purpose Checkout | save-card request uses `new_card` + `save_card=true`; charging and wallet top-up requests use `save_card=false`; raw card fields absent | PASS in mocks/static review |
| Saved-card charging | canonical brand/type/last-four/default display and CVV re-entry hint; selected saved ID forwarded without App CVV collection | PASS in mocks/static review |
| Independent AddPayment | hosted URL validation, non-sensitive reference tracking, navigation to server-hosted page | PASS in mocks/static review |
| Checkout recovery | 404/expired cleanup; 409 read-only follow-up; 503/network reference retention; in-flight GET de-duplication; explicit restart | PASS in mocks/static review |
| Payment Deep Link | opaque `checkout_session_id` and allowlisted status only; token query ignored; Reset Password route regression | PASS in tests |
| 3DS/action URL | HTTPS Mercado Pago host allowlist and unsafe URL rejection | PASS in mocks/static review; real 3DS untested |
| Charging start | wallet/direct-card/free branches, ready Payment Intent gate, duplicate-start guard, `PAYMENT_INTENT_INVALID`, D1 `UNPAID_CHARGES` safe block | PASS in mocks/static review |
| Charging settlement | decimal-string normalization and unsafe next-action URL rejection | PASS in contract tests; real backend settlement untested |
| Wallet top-up | hosted session creation, amount validation, payment result route and wallet refresh path | PASS in tests |
| Loading/empty/error/retry | payment methods, saved-card load failure, Checkout status failures, start and settle error states | PASS in component tests/static review |
| Navigation/auth continuity | full App Jest suite, Reset Password Deep Link, RootNavigator pending checkout entry | PASS in tests; device lifecycle untested |
| Three locales | i18n integrity test and full App suite; payment/card/recovery keys present in `es`, `en`, `zh` | PASS in automation; visual language review untested |
| Accessibility | roles, labels, selected/disabled states, alerts and live regions present in reviewed components; existing accessibility tests passed | PARTIAL: no screen reader/focus/keyboard device run |
| Sensitive-data handling | hosted checkout boundary, App request fixtures, static source scan; no PAN/CVV/Card Token in App JSON builders or persisted recovery reference | PASS in reviewed App scope; proxy/network and real provider capture untested |
| Responsive behavior | Expo Web bundle succeeds | PARTIAL: no visual viewport or narrow-screen run |
| Admin payment page | TypeScript, Webpack production build, nullable payment integration smoke | PASS |

## Defects and blockers

### P0-QA-001 — Payment rail configuration conflicts with the release gate

- Severity: **Release blocker / configuration**.
- Evidence: `.env.production:72` has `PAYMENT_RAILS_ENABLED=true`; `docker-compose.prod.yml:135` passes this value to the backend. `STATUS.md` requires the rail to remain disabled until backend QA, frontend QA, E2E QA and human review complete.
- Reproduction: inspect `rg -n '^PAYMENT_RAILS_ENABLED=' .env.production` and `rg -n 'PAYMENT_RAILS_ENABLED=' docker-compose.prod.yml`; the effective production compose value is enabled unless explicitly overridden.
- Impact: backend payment paths can be enabled while the required independent QA gates are incomplete. This violates the task instruction and release gate.
- QA action: not modified. Project owner must keep the payment rail disabled before any deployment or real payment testing.

No additional App product-code defect was confirmed by the executed automated/static checks. The following remain validation blockers or residual risks, not fabricated passes: real provider behavior, browser-hosted checkout, 3DS, device lifecycle, accessibility hardware, and backend data integrity.

## Unexecuted surfaces and residual risks

- No production operations, production database, payment enablement, real credentials, real card data, or real Mercado Pago transaction was used.
- Backend QA has since resumed a bounded local/test recheck and remains `blocked-current-recheck`; no local/test backend integration or database/Redis verification was performed by this frontend QA task.
- Mercado Pago Colombia `getIdentificationTypes`, BIN/card-type identification, Secure Fields tokenization, saved-card CVV and real 3DS were not run.
- No iOS/Android simulator or device, browser visual viewport, mobile keyboard, focus traversal or screen-reader verification was run.
- Default Admin Turbopack build is environment-blocked by sandbox port permissions; the same production build passed with `--webpack`.
- Legacy unused card-form translation keys remain in `app/src/i18n/en.ts`, `es.ts` and `zh.ts` (`cardNumber`, `expMonth`, `expYear`, `cvc`, `holderName` and related messages). No production App source reference was found, but they should be removed or quarantined in a future product-code task to reduce accidental reintroduction risk.
- FE-4B unpaid-list, bank/wallet unpaid repayment UI and unpaid recovery experience remain deferred by owner and were not treated as a P0 pass criterion.
- E2E QA, backend QA and human review remain pending; this report does not authorize release or production payment activation.

## Ownership and changes

- QA-owned files changed: this report and the `frontend_qa` status field in `docs/features/PAY-MP-001/STATUS.md` only.
- No App product code, Admin product code, existing product test, backend code, contract, database, migration or production configuration was modified by this QA task.
