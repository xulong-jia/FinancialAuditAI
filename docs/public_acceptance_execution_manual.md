# FinancialAuditAI 金融文档智能审核平台｜公开验收版项目开发执行手册

## 0. 项目总判断

FinancialAuditAI 应被开发为金融文档智能审核平台，而不是 OCR 展示 demo，也不是普通 RAG chatbot。系统目标是把金融底稿、采购付款证据、规则审核、知识检索、人工复核、报告导出和质量评测连接成可追溯、可复核、可回归的工程闭环。

本手册定义的目标版本为 `v1.0-public-acceptance`。最终交付目标是 `public acceptance complete`：代码、测试、文档、CI 和公开/合成验收链路应达到可运行、可验证、可审计的状态，但不声明真实客户生产落地，不要求 hosted production deployment，不要求企业级 DLP/KMS/SSO/monitoring/backups/IR 证据。

系统应具备六层能力：

| 层级 | 能力 |
| --- | --- |
| 文档层 | 文件上传、格式校验、OCR、页图像、bbox、confidence、表格与文本块 |
| 结构化层 | 文档分类、字段抽取、line_items、标准化、source evidence |
| 规则层 | 采购穿行规则、金额/时间/数量/名称/税率/缺字段/证据不足判断 |
| 知识层 | regulation、inquiry_case、prospectus、workpaper 四库 RAG |
| 工作流层 | Agent 状态机、工具白名单、Review routing、Report generation |
| 质量层 | Evaluation Center、Bad Case、public/synthetic acceptance、CI guardrails |

系统开发应遵守四项原则：

- 证据优先：所有字段、规则结果、RAG 回答和报告结论都应能回溯到文档、页码、bbox、source_text、citation 或 review record。
- 确定性优先：能用规则、schema、parser、database constraint 或 deterministic evaluator 判断的事项，不交给 LLM 猜测。
- 人机协同：低置信度、缺字段、高风险异常、证据不足和失败状态应进入 Review Center，不自动闭环。
- 评测闭环：OCR、Classification、Extraction、Rule Engine、RAG、Agent、Report 和 E2E 路径都应有测试或评测样例，并记录 metrics 与 failed_cases。

## 1. 项目总定位

### 1.1 项目名称

FinancialAuditAI 金融文档智能审核平台。

### 1.2 一句话定位

FinancialAuditAI 是面向金融文档审核和采购付款穿行的智能审核平台，基于 FastAPI、React、PostgreSQL、OCR、LLM Provider abstraction、RAG、Rule Engine、Human Review、Agent Workflow 和 Evaluation Center，实现证据可追溯、规则可解释、复核可留痕、质量可回归的 non-production public acceptance 版本。

### 1.3 项目边界

本版本应实现：

- 金融文档审核任务创建、列表、详情和状态流转。
- PDF、扫描件、图片、DOCX、Excel 导出 PDF 等文件的上传校验和处理入口。
- OCR Provider abstraction，保存页级文本、blocks、tables、bbox、confidence 和 page image。
- 文档分类，覆盖采购六类文档和扩展场景类型，保留 confidence、reason 和 review flag。
- 字段抽取，覆盖 fields、line_items、source_text、source_page、source_bbox 和标准化结果。
- 采购付款六类文件归集与穿行审核。
- Rule Engine，覆盖 pass、warning、fail、not_applicable、need_review、evidence_insufficient。
- RAG 四库，支持 chunking、embedding、retrieval、rerank、answer、citation、no-answer 和 metadata filter。
- Agent Workflow，使用状态机和工具白名单编排 OCR、分类、抽取、规则、RAG、复核和报告。
- Review Center，支持队列、字段修正、确认/驳回、重跑、before/after 和 audit logs。
- Report Center，支持 xlsx、csv、md、pdf、控制表、异常清单、证据索引和边界声明。
- Bad Case Center 和 Evaluation Center，支持 dataset manifest、external manifest、metrics、failed_cases 和 regression。
- Repository safety：`.env`、`local_storage`、上传文件、下载数据和 provider artifact 不进入 Git。
- GitHub Actions CI，覆盖安全检查、backend pytest、frontend test/build 和 docker compose config。
- OCR、Classification、Extraction、RAG、Provider readiness、Security reference 的 public/synthetic acceptance。

本版本不做：

- 不替代注册会计师、律师、投行人员、审计人员或合规人员的专业判断。
- 不构成审计、法律、投资或监管合规意见。
- 不使用真实敏感客户数据作为公开样例。
- 不要求真实或合规脱敏客户资料作为本版本验收输入。
- 不要求 hosted production deployment。
- 不要求企业级 DLP、KMS、SSO、集中监控、备份或事件响应材料。
- 不把 public_dataset、synthetic、deterministic、fallback、mock、fixture 或 images-only robustness 写成生产验证。

## 2. 业务背景与公开验收边界

金融文档审核通常需要核对合同、发票、凭证、付款回单、入库单、申请单、函证、访谈记录、合同条款和公开监管资料。人工审核关注点包括真实性、完整性、一致性、金额口径、时间顺序、证据链完整度、异常解释和复核留痕。

本版本应以公开数据集、合成数据、fixture、deterministic/local provider 和本地验收资料完成 public/synthetic acceptance。公开验收材料可用于证明：

- 文件路径、manifest、dataset guard 和 evaluator 机制可运行。
- OCR、分类、抽取、RAG 和 Provider readiness 的工程路径可验证。
- 安全边界、Git 忽略规则和本地资料归档策略可验证。
- CI 不依赖真实 provider credentials 或本地私有样本。

公开/合成材料不能证明：

- 真实客户项目效果。
- 生产部署稳定性。
- 企业级安全治理完成。
- 真实 provider SLA。
- 真实业务标签下的模型质量。

## 3. 目标用户与角色权限

系统应支持以下角色：

| 角色 | 职责 |
| --- | --- |
| analyst | 创建任务、上传文档、触发处理、查看审核结果、发起复核 |
| reviewer | 查看复核队列、修正字段、确认/驳回异常、写复核意见 |
| manager | 查看任务总览、异常趋势、报告和评测概览 |
| admin | 管理用户、角色、Provider readiness、规则、系统配置和安全检查入口 |
| viewer | 只读查看任务、报告和证据，不触发处理、不修改结果 |

RBAC 行为应可测试：

- viewer 不能上传文件、触发 OCR、触发抽取、运行规则、修改字段、确认异常或生成报告。
- analyst 可以创建任务和触发普通处理，但不能管理 provider readiness 或用户角色。
- reviewer 可以处理 Review Center 中的字段修正和异常状态，但不能修改系统级配置。
- admin 可以访问 Admin Center、Provider readiness、用户/角色管理和安全检查摘要。
- reviewer 与 admin 的权限差异应有后端 API 测试和前端行为测试。

## 4. 产品模块设计

| 模块 | 职责 | 输入 | 输出 | 验收标准 |
| --- | --- | --- | --- | --- |
| Dashboard | 展示任务、异常、复核、评测和系统状态摘要 | task、audit_results、evaluation_results | 指标卡、趋势、待办入口 | 能加载摘要数据；无权限用户只读；错误态可见 |
| Task Center | 创建、筛选、查看审核任务 | task metadata、scenario、period | audit_task | 支持创建、列表、详情、状态展示和权限控制 |
| Audit Workbench | 处理文档、字段、规则、RAG 和证据 | documents、pages、fields、rules | workbench view、evidence links | 能查看文档页、字段证据、规则结果和 RAG citation |
| Review Center | 处理复核队列和人工修正 | need_review items、fields、audit_results | review_comments、audit_logs、rerun request | 支持 confirm/dismiss/correct/rerun/bad case |
| Rule Center | 管理和查看规则 | audit_rules、parameters | rule definitions、rule results | 支持规则分类、版本、参数和测试覆盖 |
| Knowledge Center | 管理 RAG 文档与检索 | rag_documents、rag_chunks、query | citations、answer、no-answer | 支持四库、metadata filter、citation 和 no-answer |
| Report Center | 生成控制表和报告 | fields、results、reviews、citations | xlsx/csv/md/pdf、evidence index | 报告包含异常、证据、复核意见和边界声明 |
| Bad Case Center | 记录失败样例和回归资产 | failed_cases、manual reports | bad_cases、regression link | 支持创建、筛选、状态更新和回归关联 |
| Evaluation Center | 管理数据集和评测结果 | dataset manifest、external manifest | metrics、failed_cases、evaluation_results | 支持 public/synthetic/manual 类型和 guard |
| Admin Center | 管理 Provider readiness、安全状态和用户权限 | configuration、role data、readiness checks | readiness summary、RBAC state | 不输出 secrets；CI 和普通测试不依赖真实 credentials |

产品页面不应以 hosted production 或真实客户流程作为验收前提。所有页面应能使用 synthetic、fixture、deterministic/local 或 public acceptance 数据完成 non-production 验收。

## 5. 技术架构

系统应采用以下技术栈：

| 层级 | 技术 | 要求 |
| --- | --- | --- |
| Backend API | FastAPI、Pydantic、SQLAlchemy | API、schema validation、service orchestration、database access |
| Frontend | React、TypeScript、Ant Design | 工作台、复核、报表、知识库、规则、评测和 Admin |
| Database | PostgreSQL、pgvector | 结构化数据、JSONB、vector retrieval、test extension |
| Migration | Alembic | schema 版本化、CI/test DB 可初始化 |
| OCR | OCR Provider abstraction | Azure Document Intelligence provider path + local/deterministic test path |
| LLM | LLM / Embedding / Rerank / Answer Provider abstraction | 分类、抽取、解释、RAG answer、rerank、embedding |
| Evaluation | Dataset runners、external manifest loaders | public_dataset、synthetic_external_acceptance、manual_acceptance、public_reference |
| Deployment reproduction | Docker Compose | 本地 Postgres/pgvector/config validation |
| CI | GitHub Actions | safety checks、backend tests、frontend tests/build、compose config |
| Local evidence | `local_storage` | ignored external acceptance materials，不进入 Git |

核心数据流：

```text
create task
  -> upload documents
  -> validate and store file refs
  -> OCR pages
  -> classify document
  -> extract fields and line_items
  -> link business documents
  -> run Rule Engine
  -> retrieve RAG evidence
  -> route Review Center
  -> generate Report Center outputs
  -> record Bad Cases and Evaluation results
```

## 6. GitHub 目录结构

目标版本应采用以下目录结构：

```text
FinancialAuditAI/
  backend/
    app/
      api/
      agents/
      core/
      models/
      providers/
      rag/
      repositories/
      rules/
      schemas/
      services/
      evaluation/
    alembic/
      versions/
    tests/
  frontend/
    src/
      api/
      components/
      pages/
      routes/
      tests/
    e2e/
  docs/
    README and project docs
    database_schema docs
    evaluation docs
    external acceptance checklist
    security and status docs
    public_acceptance_execution_manual.md
  evals/
    datasets/
      manual_acceptance/
      production_readiness/
  scripts/
    danger_check.py
    production_safety_check.py
    provider_readiness.py
  .github/
    workflows/
      ci.yml
  docker-compose.yml
  .gitignore
  local_storage/
```

Git 规则：

- `local_storage/` 不进入 Git。
- `.env` 和 `.env.*` 不进入 Git，`.env.example` 可以作为模板。
- downloaded public datasets、raw OCR output、provider artifacts、uploaded files、reports、vector indexes 不进入 Git。
- 原本地最终版执行手册和已撤回的公开验收完成说明不作为目标版本必须提交文件。
- 本手册 `docs/public_acceptance_execution_manual.md` 应作为公开开发规格文档提交。

## 7. FastAPI 后端开发规格

后端应按分层结构开发：

| 层 | 责任 |
| --- | --- |
| `api` | route、dependency、RBAC、request/response mapping |
| `schemas` | Pydantic request/response、dataset manifest、provider payload |
| `models` | SQLAlchemy ORM、enum/status、relationships |
| `repositories` | database query and persistence |
| `services` | task/document/OCR/classification/extraction/review/report/evaluation business logic |
| `providers` | OCR、LLM、embedding、rerank、answer provider abstraction |
| `rules` | deterministic rule registry、rule evaluation、evidence handling |
| `rag` | document ingestion、chunking、embedding、retrieval、rerank、answer |
| `agents` | state machine、tool whitelist、run/step recording |
| `core` | config、security、auth、logging、redaction、errors |
| `evaluation` | dataset runners、external manifest loaders、metrics、failed_cases |

主要 API 分类：

- Auth / users / roles。
- Task Center APIs。
- Document upload and processing APIs。
- OCR / classification / extraction APIs。
- Rule Engine APIs。
- RAG document and query APIs。
- Agent workflow APIs。
- Review Center APIs。
- Report Center APIs。
- Bad Case APIs。
- Evaluation Center APIs。
- Admin / provider readiness / safety summary APIs。

通用响应应包含：

```json
{
  "success": true,
  "data": {},
  "error": null,
  "request_id": "uuid"
}
```

错误处理要求：

- validation error 应返回明确字段和原因。
- permission error 应返回 403，不泄露内部实现。
- provider error 应记录 sanitized error，不输出 credentials。
- OCR/extraction/RAG/Agent step failure 应保留状态和可复核错误信息。
- failed_cases 不应保存完整敏感原文或 provider raw secret material。

Provider 抽象要求：

- OCR provider 支持 Azure Document Intelligence path 和 local/deterministic test path。
- LLM provider 支持 classification、extraction、explain、RAG answer。
- Embedding、rerank、answer provider 应可独立 readiness check。
- 普通 pytest 和 CI 不调用真实外部 Provider。
- real provider integration 只能通过显式开关在本地执行，并写 sanitized summary。

`model_invocations` 要求：

- 记录 provider、model_name、invocation_type、prompt_version、status、latency、token usage 或估算、sanitized error。
- 不保存 credentials、authorization header、raw secret、`.env` 内容。

测试要求：

- API tests 覆盖权限、状态流转、错误处理和主要业务路径。
- service tests 覆盖 OCR/classification/extraction/rule/RAG/agent/review/report/evaluation。
- provider tests 使用 fake/local provider。
- database tests 能初始化 Alembic schema 和 pgvector extension。

## 8. React 前端开发规格

前端应按页面、路由、API client、权限行为和测试组织。

页面应覆盖：

- Dashboard。
- Task Center。
- Audit Workbench。
- Review Center。
- Report Center。
- Knowledge Center。
- Rule Center。
- Evaluation Center。
- Admin Center。

前端开发要求：

- 使用 React、TypeScript、Ant Design。
- API client 应统一处理 auth token、错误状态、loading 和空状态。
- 页面路由应体现角色权限；无权限操作隐藏或禁用，同时后端仍必须强制校验。
- 任务、文档、字段、规则、复核、报告、评测页面应有错误态和空态。
- 证据 UI 应能展示 document、page、bbox、source_text、rule evidence 和 RAG citation。
- 表格、筛选、状态标签、详情抽屉或详情页应保持一致的设计语言。

RBAC 前端行为：

- viewer 只能查看，不显示处理、修改、确认、生成、管理类操作。
- analyst 可创建任务、上传文档和触发普通处理。
- reviewer 可处理复核队列。
- admin 可访问 Admin Center、provider readiness 和用户角色配置。

测试和 build：

- `npm test` 应通过，目标为 4 passed。
- `npm run build` 应通过。
- Playwright E2E 可使用 synthetic/mocked API 验证导航、权限和工作流，但必须在文档和测试命名中标明不是 production E2E。

## 9. PostgreSQL 与 Alembic 数据库规格

数据库设计原则：

- 主键统一使用 UUID。
- 核心表包含 `created_at`、`updated_at`。
- 灵活字段、模型输出、证据、metrics 使用 JSONB。
- RAG chunks 使用 pgvector embedding。
- 人工修正通过 review、audit_log、before/after 记录，不覆盖原始证据。
- 规则结果、RAG citation、review comment 和 report evidence 必须可追溯。

核心表：

| 表 | 作用 |
| --- | --- |
| `users` | 用户和登录状态 |
| `roles` | 角色、权限点 |
| `user_roles` | 用户角色关系 |
| `audit_tasks` | 审核任务 |
| `documents` | 上传文件、分类、处理状态 |
| `document_pages` | OCR 页、raw_text、blocks、tables、bbox、confidence、page image |
| `extracted_fields` | 字段、标准化值、source evidence、correction refs |
| `audit_rules` | 规则定义、版本、参数 |
| `audit_results` | 规则执行结果、证据、review status、RAG citations |
| `review_comments` | 复核意见、字段修正、确认/驳回 |
| `reports` | 报告导出记录 |
| `rag_documents` | RAG 文档 metadata |
| `rag_chunks` | chunk text、embedding、metadata、page range |
| `agent_runs` | Agent workflow run |
| `agent_steps` | Agent step、tool、input/output refs、error |
| `document_relations` | 业务文档归集关系 |
| `control_table_rows` | 控制表行和 evidence refs |
| `audit_logs` | 操作审计 |
| `model_invocations` | 模型调用记录和 sanitized error |
| `bad_cases` | 错误样例、root cause、fix plan、status |
| `evaluation_results` | eval metrics、sample_count、failed_cases |

Alembic 要求：

- migrations 应覆盖目标 schema。
- 测试数据库应能从空库 upgrade 到 head。
- pgvector extension 应在本地和 CI test DB 中可初始化。
- enum/type/table 创建应避免重复创建错误。
- migration 不应依赖 `.env` 或 `local_storage`。

## 10. 核心业务流

任务创建：

```text
create task
  -> validate scenario / period / owner / reviewer
  -> initialize status
  -> write audit_log
```

文档上传：

```text
upload
  -> validate file type and content
  -> calculate hash
  -> store file reference
  -> create documents
```

OCR：

```text
document
  -> render pages
  -> run OCR provider
  -> save document_pages
  -> preserve page_count / raw_text / blocks / tables / bbox / confidence / image refs
```

文档分类：

```text
document_pages
  -> classify document
  -> save doc_type / confidence / reason / alternative_types
  -> route low confidence to Review Center
```

字段抽取：

```text
doc_type + OCR result
  -> apply schema
  -> extract fields and line_items
  -> normalize value
  -> save source_text / source_page / source_bbox
  -> warn on missing or low-confidence fields
```

业务归集：

```text
documents + extracted_fields
  -> build business_key
  -> create document_relations
  -> record confidence and evidence
```

Rule Engine：

```text
fields + line_items + relations + rules
  -> run deterministic checks
  -> write audit_results
  -> route fail/warning/need_review/evidence_insufficient
```

RAG：

```text
rag documents
  -> parse / chunk / embed
  -> retrieve / rerank
  -> answer with citations or no-answer
```

Review：

```text
need_review item
  -> reviewer opens evidence
  -> correct / confirm / dismiss / rerun / bad case
  -> write review_comments and audit_logs
```

Report：

```text
fields + results + reviews + citations
  -> control table
  -> exception list
  -> evidence index
  -> xlsx / csv / md / pdf
```

Bad Case：

```text
failed sample or reviewer mark
  -> create bad_case
  -> root cause / fix plan
  -> add to regression dataset
```

Evaluation：

```text
dataset manifest
  -> run evaluator
  -> compute metrics
  -> save evaluation_results
  -> create failed_cases / bad_cases when applicable
```

## 11. 采购穿行模块

采购穿行应覆盖六类采购付款文件：

| 文档类型 | 关键字段 |
| --- | --- |
| `purchase_request` | request_no、request_date、department、applicant、supplier_name、item、quantity、estimated_amount、approval_status |
| `purchase_contract` | contract_no、signing_date、buyer、supplier_name、item、quantity、unit_price、amount、tax_rate、payment_terms |
| `warehouse_receipt` | receipt_no、receipt_date、supplier_name、item、quantity、warehouse、receiver |
| `invoice` | invoice_no、invoice_date、seller_name、buyer_name、amount_excluding_tax、tax_amount、amount_including_tax、tax_rate |
| `accounting_voucher` | voucher_no、voucher_date、account_name、counterparty、debit_amount、credit_amount、summary |
| `payment_receipt` | payment_no、payment_date、payer、payee、bank_account、payment_amount、payment_method |

字段 schema 要求：

- 每个字段应定义 `field_name`、`field_type`、required、normalization、source evidence requirement。
- 多品种、多单位、多税率应使用 `line_items`。
- 日期统一为 `YYYY-MM-DD`。
- 金额统一为 numeric，币种单独记录。
- 税率统一为 decimal。
- 不确定字段应输出 null、warning 或 need_review，不允许补全。

规则要求：

| 类别 | 规则 |
| --- | --- |
| 时间 | 申请、合同、入库、发票、凭证、付款时间顺序 |
| 数量 | 合同、入库、发票数量一致或累计一致 |
| 金额 | 合同、发票、凭证、付款金额一致或容差内 |
| 名称 | 供应商、开票方、收款方、往来单位一致 |
| 品种 | 品名、规格、单位、item_key 匹配 |
| 税率 | 不含税金额、税额、含税金额、税率一致 |
| 缺字段 | 必填字段、规则依赖字段、低置信度字段进入 need_review |
| 多品种 | 分行、单位换算、逐行匹配 |
| 含税/不含税 | 统一金额口径后比较 |
| 证据不足 | 缺 source evidence 或 citation 时返回 evidence_insufficient |

验收目标应使用 synthetic/public/local acceptance。不得要求真实生产采购数据集作为本版本验收前提。

## 12. 扩展场景模块

销售穿行、函证、访谈和合同审核应作为扩展能力规格，而不是本版本生产验收承诺。

扩展能力应满足：

- 有基础 schema。
- 有规则入口。
- 可复用 Review Center。
- 可复用 RAG citation 和 no-answer。
- 可复用 Report Center 的异常清单和证据索引。
- 可纳入 Evaluation Center 的 synthetic/manual dataset。
- 不要求真实生产验收样本。

场景摘要：

| 场景 | 基础能力 |
| --- | --- |
| 销售穿行 | sales_order、sales_contract、delivery_order、invoice、receipt、voucher 的字段和一致性规则入口 |
| 函证 | confirmation amount、counterparty、reply status、difference reason 和 evidence |
| 访谈 | interviewee、date、topic、key statements、risk tags、source evidence |
| 合同审核 | parties、amount、term、payment clause、termination、risk clause 和 RAG reference |

## 13. OCR 与 Classification 开发规格

OCR 输出必须包含：

```json
{
  "document_id": "uuid",
  "page_count": 1,
  "pages": [
    {
      "page_number": 1,
      "raw_text": "text",
      "blocks": [{"text": "amount", "bbox": [1, 2, 3, 4], "confidence": 0.95}],
      "tables": [],
      "ocr_confidence": 0.95,
      "page_image_path": "ignored-or-managed-path"
    }
  ]
}
```

OCR Provider 要求：

- 支持 Azure Document Intelligence provider path。
- 支持 local/deterministic test path。
- 支持 PDF、扫描 PDF、PNG、JPG。
- 支持多页、表格、bbox、confidence 和 page image reference。
- provider error 应记录 sanitized error。
- CI 默认不调用真实外部 Provider。

Classification 输出必须包含：

```json
{
  "document_id": "uuid",
  "doc_type": "invoice",
  "confidence": 0.93,
  "reason": "matched invoice fields",
  "alternative_types": [],
  "need_human_review": false
}
```

Classification 验收：

- 应支持采购六类 synthetic external acceptance，`sample_count=6`。
- 应输出 accuracy、macro_f1、low_confidence_rate、confidence_threshold_accuracy、human_review_flag_accuracy。
- 低置信度或未知类型应进入 Review Center。
- 不要求真实客户分类 labels。

OCR public evidence 要覆盖：

- OCR synthetic external acceptance，`sample_count=3`。
- SROIE OCR public acceptance，`sample_count=5`。
- SRD images-only OCR robustness，`sample_count=5`。
- 1_Images / Zenodo images-only OCR robustness，`sample_count=5`。

images-only robustness 只能验收 public image ingestion/rendering robustness，不证明 OCR text、bbox、table、confidence 或 extraction quality。

## 14. Extraction 开发规格

Extraction 应支持：

- `fields`。
- `line_items`。
- `source_text`。
- `source_page`。
- `source_bbox`。
- normalized values。
- missing-field warnings。
- low-confidence review routing。

字段输出示例：

```json
{
  "field_name": "amount_including_tax",
  "field_type": "money",
  "value_text": "123.45",
  "value_normalized": {"amount": 123.45, "currency": "CNY"},
  "confidence": 0.94,
  "source_page": 1,
  "source_bbox": [10, 20, 100, 40],
  "source_text": "Total 123.45"
}
```

Public extraction 要求：

- 支持 SROIE public extraction，`sample_count=5`。
- 支持 FATURA invoice/layout extraction，`sample_count=5`。
- 支持 normalized matching。
- 支持 address fuzzy/token overlap。
- 支持 numeric total matching。
- 支持 source text evidence。
- FATURA 应支持 source_bbox coverage。
- manifest path 必须限制在 `local_storage/external_acceptance` 下，拒绝绝对路径和 `..` traversal。

本版本不要求真实客户 extraction labels。

## 15. Rule Engine 开发规格

Rule Engine 应作为确定性审核核心开发。

规则配置应包含：

- rule_code。
- name。
- scenario。
- category。
- severity。
- description。
- parameters。
- required_fields。
- version。
- enabled。

规则结果应包含：

- status：`pass`、`warning`、`fail`、`not_applicable`、`need_review`、`evidence_insufficient`。
- severity。
- expected_value。
- actual_value。
- evidence。
- review routing reason。
- rule version。

要求：

- 支持规则参数和版本追踪。
- 支持 pass/warning/fail/not_applicable/need_review/evidence_insufficient。
- 支持 rule evaluation dataset。
- 不允许缺字段 silent pass。
- 缺依赖字段、低置信度字段、证据缺失应返回 need_review 或 evidence_insufficient。
- 规则失败、高风险 warning 和证据不足应进入 Review Center。

## 16. RAG 开发规格

RAG 应支持四库：

| 知识库 | 内容 |
| --- | --- |
| `regulation` | 法规、规则、指引 |
| `inquiry_case` | 公开问询、审核案例、回复摘要 |
| `prospectus` | 招股书、SEC filing、公开披露 |
| `workpaper` | 当前任务底稿 OCR、字段、复核后证据 |

RAG pipeline：

```text
parse document
  -> chunk
  -> metadata
  -> embedding
  -> retrieval
  -> metadata filter
  -> rerank
  -> answer
  -> citation / no-answer
```

要求：

- chunk 保存 title、section、page_start、page_end、knowledge_base、metadata。
- retrieval 支持 metadata filter。
- answer 必须带 citation 和 limitations。
- 无依据时返回 no-answer 或 evidence_insufficient。
- workpaper 与公开知识库应隔离，至少通过 task_id 或 metadata scope 控制。
- 支持 SEC EDGAR Apple 10-K public RAG acceptance，`sample_count=4`。
- 不要求 project-specific workpaper production labels。

## 17. Agent Workflow 开发规格

Agent Workflow 应采用状态机 + 工具白名单 + 规则约束 + 人工复核路由。

核心表：

- `agent_runs`。
- `agent_steps`。

状态机：

```text
DRAFT
  -> FILES_UPLOADED
  -> OCR_PENDING -> OCR_RUNNING -> OCR_COMPLETED
  -> CLASSIFICATION_PENDING -> CLASSIFICATION_COMPLETED
  -> EXTRACTION_PENDING -> EXTRACTION_COMPLETED
  -> RULE_AUDIT_PENDING -> RULE_AUDIT_COMPLETED
  -> EVIDENCE_RETRIEVAL_PENDING -> EVIDENCE_RETRIEVAL_COMPLETED
  -> HUMAN_REVIEW_REQUIRED / AUTO_PASS
  -> REVIEWING
  -> REPORT_READY
  -> COMPLETED
```

失败状态应覆盖 OCR、classification、extraction、rule audit、evidence retrieval 和 report generation。

工具白名单：

- `run_ocr(document_id)`。
- `classify_document(document_id)`。
- `extract_fields(document_id, doc_type)`。
- `link_business_documents(task_id)`。
- `run_rule_engine(task_id)`。
- `retrieve_evidence(query, kb)`。
- `create_review_ticket(result_id)`。
- `generate_control_table(task_id)`。
- `record_bad_case(payload)`。

Agent 不允许：

- 绕过 Rule Engine 直接输出审核结论。
- 把检索不到的依据写成结论。
- 自动确认高风险异常。
- 跳过 Review Center。
- 在 logs 中输出 credentials 或完整敏感材料。

Agent 应支持 retry/error handling、review routing、Bad Case recording 和 evaluation labels。

## 18. Review Center 开发规格

Review Center 应支持：

- review queue。
- field correction。
- confirm/dismiss。
- rerun extraction。
- rerun rules。
- before/after。
- review comments。
- audit_logs。
- Bad Case conversion。

触发条件：

- 分类低置信度。
- OCR 页级低置信度。
- 必填字段缺失。
- 抽取低置信度。
- Rule Engine fail。
- high severity warning。
- evidence_insufficient。
- RAG no-answer。
- Agent step failed。
- 用户手动标记。

权限行为：

- reviewer 可处理复核项。
- admin 可查看和管理全部复核项。
- analyst 可查看相关任务复核状态，但不能越权处理。
- viewer 只读。

验收要求：

- 字段修正保留原值、新值、修正人和时间。
- confirm/dismiss 必须写入 review_comments。
- dismiss 必须填写原因。
- rerun 应写 audit_logs。
- 复核意见应进入 report。

## 19. Report Center 开发规格

Report Center 应支持输出：

- `xlsx`。
- `csv`。
- `md`。
- `pdf`。

报告内容：

- Summary。
- Procurement Control Table。
- Exception List。
- Field Corrections。
- Evidence Index。
- Rule Definitions。
- RAG Citations。
- Review Comments。
- Boundary Statement。

控制表字段应覆盖：

- task_no。
- business_key。
- supplier_name。
- contract_no。
- request_date。
- signing_date。
- receipt_date。
- invoice_date。
- voucher_date。
- payment_date。
- item_summary。
- contract_qty。
- receipt_qty。
- invoice_qty。
- contract_amount。
- invoice_amount。
- payment_amount。
- time_check。
- quantity_check。
- amount_check。
- name_check。
- item_check。
- tax_check。
- missing_field_check。
- overall_status。
- evidence_refs。
- reviewer_comment。

报告必须包含用途边界，明确公开/合成验收数据不能作为真实审计结论。

## 20. Bad Case 开发规格

Bad Case 类型：

| 类型 | 示例 |
| --- | --- |
| `ocr_error` | 金额识别错、页渲染失败、表格错列 |
| `classification_error` | 发票识别成付款回单 |
| `extraction_error` | 金额字段混淆、source_bbox 缺失 |
| `rule_error` | 分批付款误判、缺字段 silent pass |
| `rag_error` | citation 不相关、no-answer 失败 |
| `agent_error` | 状态非法、跳过复核、工具越权 |
| `review_dispute` | 证据不足、复核意见不清 |

Bad Case 字段：

- case_type。
- title。
- input_payload。
- model_output。
- expected_output。
- root_cause。
- fix_plan。
- status：open、fixed、verified、wont_fix。
- severity。
- regression link。

Bad Case 应与 Evaluation Center 集成：

- failed_cases 可转 Bad Case。
- Bad Case 可加入 regression dataset。
- 修复后应通过 regression 验证再标记 verified。

## 21. Evaluation Center 开发规格

Evaluation Center 应支持：

- dataset manifest。
- external manifest。
- `public_dataset`。
- `synthetic_external_acceptance`。
- `public_reference`。
- `manual_acceptance`。
- production guard。
- metrics。
- failed_cases。
- blocked_external_dependency 字段。

本版本目标不是 production evaluation。production guard 的作用是阻止 public/synthetic/mock/fallback/deterministic/images-only 结果被误标为生产验证。

评测要求：

- dataset manifest 应声明 eval_type、dataset_name、source_type、sample_count、is_production_evaluation。
- external manifest loader 应拒绝绝对路径和 `..` traversal。
- metrics 应真实反映 sample_count、failed_cases、pass_rate、source_type、evaluation_status。
- failed_cases 不得 silent pass。
- 当缺少外部资料、provider credentials 或显式 integration gate 时，应记录 blocked_external_dependency，而不是伪造通过。
- Evaluation Center 应保存结果到 `evaluation_results`。

## 22. Public / Synthetic Acceptance 数据集规格

本版本必须支持并跑通以下公开/合成验收。

| evidence | source_type | sample_count | manifest path pattern | expected metrics | proves | does not prove |
| --- | --- | --- | --- | --- | --- | --- |
| OCR synthetic external acceptance | `synthetic_external_acceptance` | 3 | `local_storage/external_acceptance/production_dataset/ocr/ocr_external_manifest.json` | `ocr_sample_pass_rate=1.0`; text/page/block/bbox/confidence/table checks `1.0`; `is_production_evaluation=false` | OCR provider path、external manifest、multi-page/table/scanned-like checks、sanitized summary | 真实客户 OCR 质量、生产 SLA、生产部署 |
| SROIE OCR public acceptance | `public_dataset` | 5 | `local_storage/external_acceptance/production_dataset/ocr/sroie_selected/sroie_external_manifest.json` | OCR pass、page/block/bbox/confidence/table/key-information/normalized/fuzzy-address metrics `1.0`; `is_production_evaluation=false` | public receipt OCR、normalized field-aware matching、bbox/confidence check | 项目特定 OCR 质量、真实业务样本 |
| Classification synthetic external acceptance | `synthetic_external_acceptance` | 6 | `local_storage/external_acceptance/production_dataset/classification/classification_external_manifest.json` | `accuracy=1.0`; `macro_f1=1.0`; `low_confidence_rate=0.0`; confidence/review flag checks `1.0`; `is_production_evaluation=false` | 六类采购文档分类 plumbing、deterministic/local classification | 真实 LLM 分类质量、真实 labels |
| SROIE extraction public acceptance | `public_dataset` | 5 | `local_storage/external_acceptance/production_dataset/extraction/sroie/sroie_extraction_external_manifest.json` | sample/field/company/date/address/total/evidence metrics `1.0`; `is_production_evaluation=false` | public receipt/invoice entity mapping、source_text evidence、normalized matching | 项目特定 extraction labels、真实客户抽取质量 |
| FATURA extraction/layout public acceptance | `public_dataset` | 5 | `local_storage/external_acceptance/production_dataset/extraction/fatura/fatura_extraction_external_manifest.json` | sample/field/company/date/address/total/evidence metrics `1.0`; `source_bbox_coverage=1.0`; `is_production_evaluation=false` | public invoice layout annotation、bbox-backed evidence、invoice field extraction plumbing | 真实客户 invoice extraction、生产 layout robustness |
| SEC EDGAR Apple 10-K public RAG acceptance | `public_dataset` | 4 | `local_storage/external_acceptance/production_dataset/rag/sec_edgar/sec_edgar_rag_external_manifest.json` | external pass/citation/answer/no-answer/metadata metrics `1.0`; document count `1`; chunk count recorded; `is_production_evaluation=false` | public filing ingestion、chunking、retrieval、citation metadata、no-answer | project-specific workpaper RAG、真实 citation labels |
| SRD images-only OCR robustness | `public_dataset` | 5 | `local_storage/external_acceptance/production_dataset/ocr/srd*/manifest.json` | `ocr_sample_pass_rate=1.0`; `page_count_accuracy=1.0`; `is_production_evaluation=false` | public image ingestion/rendering robustness | OCR text accuracy、bbox/table/confidence、extraction quality |
| 1_Images / Zenodo images-only OCR robustness | `public_dataset` | 5 | `local_storage/external_acceptance/production_dataset/ocr/1_images*/manifest.json` | `ocr_sample_pass_rate=1.0`; `page_count_accuracy=1.0`; `is_production_evaluation=false` | additional public image ingestion/rendering robustness | OCR quality、Provider quality、生产证据 |
| Provider readiness artifact | `local_external_acceptance` | 1 sanitized artifact summary | `local_storage/external_acceptance/provider_artifacts/*.json` | JSON valid、forbidden_hits empty、paths/providers/run metadata present | provider readiness mechanism、artifact redaction discipline | publicly disclosable SLA、生产 provider attestation |
| OWASP ASVS security reference mapping | `public_reference` | 1 reference mapping | `local_storage/external_acceptance/downloads/security/owasp_asvs/` | reference archived、mapping docs present | security review checklist baseline | enterprise security completion、hosted security governance |

所有 manifest under `local_storage` 只作为本地验收资料归档，不进入 Git。

## 23. Security / Privacy / Repo Safety 开发规格

安全与仓库边界：

- `.env` 不提交。
- `local_storage` 不提交。
- uploaded files 不提交。
- generated reports 不提交。
- downloaded datasets 不提交。
- provider artifacts 不提交，除非只提交 sanitized summary。
- credentials、tokens、authorization headers、raw provider responses 不写入 committed docs。
- failed_cases 和 evaluation results 不保存完整敏感原文。

脚本要求：

- `scripts/danger_check.py` 应检查 tracked/staged secrets、runtime artifact path、危险文件和 provider artifact 泄漏。
- `scripts/production_safety_check.py` 应检查生产配置风险、tracked/staged `.env`、runtime artifacts 和明显不安全配置。

系统要求：

- Auth 和 RBAC 应覆盖主要 API。
- upload validation 应检查文件扩展名、内容类型、大小和危险输入。
- log redaction 应覆盖 provider error、headers、tokens 和 secrets。
- OWASP ASVS mapping 只是 public_reference 和安全评审 checklist，不是 enterprise security completion。

## 24. CI / Docker / 本地复现规格

GitHub Actions CI 必须运行：

```text
python3 scripts/danger_check.py
python3 scripts/production_safety_check.py
cd backend && python -m pytest -q
cd frontend && npm test
cd frontend && npm run build
docker compose config
```

验收目标：

- backend pytest：`230 passed, 5 warnings`。
- frontend `npm test`：`4 passed`。
- frontend build：passed。
- CI：green。
- CI 不依赖 `.env`、`local_storage` 或真实 provider credentials。
- CI 应启动或配置 Postgres/pgvector test service。
- CI 应在 backend tests 前完成数据库初始化或 migration setup。

Docker Compose 要求：

- 支持本地 Postgres/pgvector。
- 支持 backend/frontend 服务配置。
- `docker compose config` 应通过。
- Compose validation 不应读取 `.env` secret 内容作为验收前提。

本地复现要求：

- 后端测试可使用 backend venv。
- 前端测试和 build 可在 frontend 目录运行。
- public/synthetic external acceptance 的原始材料保存在 ignored `local_storage`。

## 25. Documentation 规格

目标版本应维护以下文档类型：

- README。
- database_schema。
- evaluation。
- external_acceptance_materials_checklist。
- final audit/status docs。
- security_reference_mapping。
- 本执行手册。

文档要求：

- 不把 public/synthetic/manual/fixture/mock/fallback/deterministic/images-only evidence 写成生产验证。
- 不把本地可运行写成 hosted deployment。
- 不把 public dataset 验收写成真实客户项目验收。
- 不提交 `.env`、`local_storage`、raw provider artifact 或下载数据。
- 文档应区分 code/test/docs completeness、public/synthetic acceptance、future production scope。
- 本执行手册应是开发目标规格，不是完成状态报告、release note 或 README。

## 26. 最终交付验收标准

### 26.1 功能验收

- 能创建任务、上传文档、查看状态。
- 能执行 OCR、分类、抽取、业务归集、规则审核、RAG 检索、复核、报告导出。
- 能记录 Bad Case 和 Evaluation results。
- 前端能覆盖 Dashboard、Task、Workbench、Review、Rule、Knowledge、Report、Bad Case、Evaluation、Admin。

### 26.2 工程验收

- backend tests 目标为 `230 passed, 5 warnings`。
- frontend tests 目标为 `4 passed`。
- frontend build passed。
- GitHub Actions CI green。
- Docker Compose config validation passed。
- 普通测试不依赖真实 provider credentials。

### 26.3 数据库验收

- Alembic migrations 覆盖目标 schema。
- PostgreSQL/pgvector test DB 可初始化。
- 核心表存在并支持关系约束。
- JSONB、UUID、vector、audit fields 可用。

### 26.4 OCR / Classification 验收

- OCR 输出 page_count、raw_text、blocks、tables、bbox、confidence、page image。
- Azure provider path 和 local/deterministic path 均有工程入口。
- OCR synthetic external acceptance 3 samples 通过。
- SROIE OCR public acceptance 5 samples 通过。
- SRD images-only 5 samples 通过 ingestion/rendering robustness。
- 1_Images / Zenodo images-only 5 samples 通过 ingestion/rendering robustness。
- Classification synthetic external acceptance 6 samples 通过。

### 26.5 Extraction 验收

- fields、line_items、source_text、source_page、source_bbox 可保存和评测。
- SROIE public extraction 5 samples 通过。
- FATURA extraction/layout 5 samples 通过。
- normalized matching、address token overlap、source_bbox coverage 可验证。

### 26.6 Rule Engine 验收

- 规则可配置、可版本化、可测试。
- 支持 pass/warning/fail/not_applicable/need_review/evidence_insufficient。
- 缺字段不得 silent pass。
- 规则结果包含 evidence 和 review routing。

### 26.7 RAG 验收

- regulation/inquiry_case/prospectus/workpaper 四库可建模。
- chunking、embedding、retrieval、rerank、answer、citation、no-answer、metadata filter 可运行。
- SEC EDGAR Apple 10-K public RAG acceptance 4 samples 通过。

### 26.8 Agent 验收

- agent_runs 和 agent_steps 记录完整。
- 状态机合法。
- tool whitelist 生效。
- retry/error handling 可验证。
- review routing 生效。
- Agent 不绕过 Rule Engine，不自动确认高风险异常。

### 26.9 Review 验收

- review queue 可查看。
- field correction 记录 before/after。
- confirm/dismiss/rerun 写 audit_logs。
- reviewer/admin/viewer 权限行为可测。
- Bad Case conversion 可用。

### 26.10 Report 验收

- 支持 xlsx/csv/md/pdf。
- 控制表、异常清单、证据索引、复核意见可导出。
- 报告包含 boundary statement。

### 26.11 Evaluation 验收

- 支持 dataset manifest 和 external manifest。
- 支持 public_dataset、synthetic_external_acceptance、public_reference、manual_acceptance。
- production guard 生效。
- metrics、failed_cases、blocked_external_dependency 字段真实反映状态。
- 不允许 silent pass。

### 26.12 Security / Repo Safety 验收

- `.env` 不被 Git 跟踪。
- `local_storage` 不被 Git 跟踪。
- uploaded files、reports、provider artifacts 不被 Git 跟踪。
- danger_check passed。
- production_safety_check passed。
- secret redaction 和 RBAC 行为可测。

### 26.13 CI 验收

- GitHub Actions CI 必须 green。
- CI 覆盖 danger_check、production_safety_check、backend pytest、frontend test、frontend build、docker compose config。
- CI 不依赖 `.env`、`local_storage` 或真实 provider credentials。

### 26.14 Public / Synthetic Acceptance 验收

- OCR synthetic external acceptance：3 samples。
- SROIE OCR public acceptance：5 samples。
- Classification synthetic external acceptance：6 samples。
- SROIE extraction public acceptance：5 samples。
- FATURA extraction/layout public acceptance：5 samples。
- SEC EDGAR Apple 10-K public RAG acceptance：4 samples。
- SRD images-only OCR robustness：5 samples。
- 1_Images / Zenodo images-only OCR robustness：5 samples。
- Provider readiness artifact：sanitized summary only。
- OWASP ASVS security reference mapping：public reference only。

最终验收结论应写为：

```text
v1.0-public-acceptance complete
```

不得写成生产版本验收完成。

## 27. 版本边界与未来生产版说明

本手册定义的范围到 `v1.0-public-acceptance` 为止。若未来另行开发生产版本，应作为新目标处理，并由项目方准备：

- 真实或合规脱敏业务数据。
- 真实人工审核 labels。
- 可披露的 provider integration artifact。
- hosted deployment evidence。
- 企业安全治理证据，包括身份、密钥、DLP、监控、备份、事件响应和审计留存。

这些材料不属于本版本目标，也不应作为本版本 public acceptance complete 的验收阻塞项。本版本的正确定位是：从零开发后达到 code/test/docs complete、CI green、public/synthetic acceptance complete、repo safety guardrails complete 的 non-production public acceptance release。
