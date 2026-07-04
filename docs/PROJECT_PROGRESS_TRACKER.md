# FinancialAuditAI Project Progress Tracker

本文件是 FinancialAuditAI 项目开发进度追踪文件。

本文件是开发过程中的 single source of truth。后续新增功能必须先写进本文件，再进入开发。不在本文件中的功能默认不做。每次完成一个功能、测试或交付物，都必须同步更新对应 Phase 的 checkbox 和 `Status`。

Status 可选值：`TODO`, `IN_PROGRESS`, `DONE`, `BLOCKED`, `DEFERRED`。

## 开发原则

- 先完成 vertical slice，再做横向扩展。
- 先完成采购穿行 MVP，再做 RAG / Agent / Evaluation。
- Rule Engine 优先于 Agent。
- Human Review 优先于自动结论。
- 证据链优先于漂亮 UI。
- 不在 tracker 里的功能默认不开发。
- Phase 11-20 必须在 Phase 10 完成并验收后再开始。
- MVP 阶段只允许完成采购穿行闭环，不允许提前扩展销售、函证、访谈、合同审核、完整 RAG、完整 Agent、完整 RBAC、完整 Evaluation Center。

## MVP 边界说明

MVP 只交付采购穿行 vertical slice。MVP 不实现完整 RAG 四库、完整 Evaluation Center、完整 Bad Case Center UI、完整 Agent Workflow、完整 RBAC，也不实现销售、函证、访谈、合同审核扩展场景。

MVP 中允许保留证据索引、规则 evidence、基础测试、demo data、Provider 接口和后续扩展接口，但不得提前开发 Post-MVP 功能。

## Phase 总览

| Phase | Phase 名称 | MVP / Post-MVP | Status | 主要交付物 |
| --- | --- | --- | --- | --- |
| Phase 0 | 项目初始化与工程骨架 | MVP | DONE | 可启动的 FastAPI、React、PostgreSQL、Docker Compose 骨架 |
| Phase 1 | 任务中心与文件上传 | MVP | DONE | 采购任务创建、六类文件上传、文件落盘 |
| Phase 2 | OCR / 文档解析 / 页级文本保存 | MVP | DONE | 页级文本、OCR blocks、document_pages |
| Phase 3 | 文档分类 | MVP | DONE | 六类采购文件 doc_type、置信度、分类理由 |
| Phase 4 | 字段抽取与 Schema 校验 | MVP | DONE | 六类采购字段、line_items、Pydantic 校验 |
| Phase 5 | 采购业务归集 | MVP | DONE | business_key、document_relations |
| Phase 6 | Rule Engine MVP | MVP | DONE | Python rule registry、六条采购规则、audit_results |
| Phase 7 | Audit Workbench 前端工作台 | MVP | DONE | 三栏审核工作台 |
| Phase 8 | Review Center 基础复核闭环 | MVP | DONE | 字段修正、异常确认、驳回、重跑规则 |
| Phase 9 | Report Center 控制表与异常清单导出 | MVP | DONE | xlsx 控制表、异常清单、证据索引 |
| Phase 10 | MVP 测试、演示数据、README 和 Docker 交付 | MVP | DONE | 可复现 MVP、测试、README、Docker、demo seed |
| Phase 11 | RAG 四库扩展 | Post-MVP | DONE | regulation / inquiry_case / prospectus / workpaper 检索、citation、no-answer |
| Phase 12 | Rule Center 规则版本化与参数配置 | Post-MVP | TODO | 规则版本、启用状态、参数配置 |
| Phase 13 | Agent Workflow 状态机与工具调用 | Post-MVP | TODO | agent_runs、agent_steps、状态机、重试 |
| Phase 14 | Bad Case Center 与 Evaluation Center | Post-MVP | TODO | bad_cases、evaluation_results、回归评测 |
| Phase 15 | 销售穿行扩展 | Post-MVP | TODO | 销售穿行 Schema、规则、控制表 |
| Phase 16 | 函证模块扩展 | Post-MVP | TODO | 函证字段抽取、差异比对、复核 |
| Phase 17 | 访谈模块扩展 | Post-MVP | TODO | 访谈字段、关键回答、底稿交叉验证 |
| Phase 18 | 合同审核模块扩展 | Post-MVP | TODO | 合同条款抽取、风险提示、证据索引 |
| Phase 19 | RBAC、审计、安全、工程化完善 | Post-MVP | TODO | 用户角色权限、安全、审计、异步工程化 |
| Phase 20 | 最终验收、文档整理、作品集展示材料 | Post-MVP | TODO | 最终验收清单、文档、截图、展示材料 |

## Phase 0: 项目初始化与工程骨架

- Phase 名称：项目初始化与工程骨架
- 是否属于 MVP：是
- Status: DONE

### Notes

- 2026-07-04: Docker Desktop 启动后，`docker compose config` 通过，PostgreSQL 容器实际启动验证通过，`pg_isready` 返回 accepting connections，`select 1` 查询成功，容器状态为 healthy。

### 阶段目标

建立最小可运行工程骨架，支持后端、前端、数据库和本地 Docker Compose 启动。

### 后端任务

- [x] 创建 `backend/app/main.py`。
- [x] 创建后端基础目录：`api`, `core`, `db`, `models`, `schemas`, `services`。
- [x] 实现 FastAPI app 初始化。
- [x] 实现统一 API prefix：`/api/v1`。
- [x] 创建配置读取文件，支持 `.env`。

### 前端任务

- [x] 创建 React + TypeScript + Ant Design 工程。
- [x] 创建基础路由结构。
- [x] 创建空布局：顶部导航、侧边菜单、内容区。
- [x] 创建占位页面：Task Center、Audit Workbench、Review Center、Report Center。

### 数据库 / Migration 任务

- [x] 初始化 SQLAlchemy session。
- [x] 初始化 Alembic。
- [x] 配置 PostgreSQL 连接。
- [x] 保留后续 pgvector 扩展入口，但本阶段不启用 RAG。

### API 任务

- [x] `GET /health`。
- [x] `GET /api/v1/config`。

### 测试任务

- [x] 添加 `backend/tests/test_health_api.py`。
- [x] 验证 FastAPI app 可启动。
- [x] 验证前端 dev server 可启动。
- [x] 验证 Docker Compose 可启动数据库。

### 验收标准

- [x] 后端本地可启动。
- [x] 前端本地可启动。
- [x] PostgreSQL 可连接。
- [x] `GET /health` 返回正常。
- [x] `.env.example` 包含必要配置但不包含真实密钥。

### 交付物

- [x] `backend/` 工程骨架。
- [x] `frontend/` 工程骨架。
- [x] `docker-compose.yml`。
- [x] `.env.example`。
- [x] 最小 README 启动说明。

### 风险点

- [x] 依赖安装过多导致启动复杂。
- [x] 过早引入认证、异步任务或 RAG 造成范围膨胀。
- [x] 配置文件泄露真实密钥。

### 不允许额外扩展的边界说明

- [x] 不实现登录、RBAC、RAG、Agent、Evaluation。
- [x] 不添加 Celery / Redis。
- [x] 不创建与采购 MVP 无关的业务页面。

## Phase 1: 任务中心与文件上传

- Phase 名称：任务中心与文件上传
- 是否属于 MVP：是
- Status: DONE

### Notes

- 2026-07-04: Phase 1 完成任务 CRUD、六类采购文件上传、基础文件安全校验、`audit_tasks` / `documents` migration、Task Center 页面和 API 测试。未实现 Phase 2 OCR 或任何后续模块。

### 阶段目标

支持创建采购穿行审核任务，上传六类采购文件，保存文件元数据和本地存储路径。

### 后端任务

- [x] 实现 `TaskService` 创建、查询、更新任务。
- [x] 实现 `DocumentService` 文件校验、hash、保存。
- [x] 支持六类采购文件上传。
- [x] 记录上传状态和文件基础信息。

### 前端任务

- [x] 实现 Task Center 任务列表。
- [x] 实现新建采购任务表单。
- [x] 实现 Document Upload 组件。
- [x] 展示上传文件列表、文件类型、大小、状态。

### 数据库 / Migration 任务

- [x] 创建 `audit_tasks` 表。
- [x] 创建 `documents` 表。
- [x] 添加任务状态字段：`draft`, `uploaded`, `failed`。
- [x] 添加文件 hash、storage_path、doc_type、处理状态字段。

### MVP 用户字段处理说明

- MVP 阶段不实现完整 RBAC。
- MVP 阶段所有 user 相关字段使用 nullable UUID、nullable string 或 `actor_name` 记录操作者，不强制 FK 到 `users`。
- Phase 19 实现 users / roles / user_roles 后，再评估是否回填真实外键。
- 在 Phase 19 前，不允许为了 owner_id / uploaded_by / reviewed_by 等字段提前实现完整认证系统。

### API 任务

- [x] `POST /api/v1/tasks`。
- [x] `GET /api/v1/tasks`。
- [x] `GET /api/v1/tasks/{task_id}`。
- [x] `PATCH /api/v1/tasks/{task_id}`。
- [x] `POST /api/v1/tasks/{task_id}/documents`。
- [x] `GET /api/v1/tasks/{task_id}/documents`。
- [x] `GET /api/v1/documents/{document_id}`。

### 测试任务

- [x] 添加任务创建 API 测试。
- [x] 添加任务列表 API 测试。
- [x] 添加文件上传 API 测试。
- [x] 测试不支持文件类型会被拒绝。
- [x] 测试文件 hash 和 storage_path 会写入数据库。

### 验收标准

- [x] 可创建 `procurement` 场景任务。
- [x] 可上传采购申请单、采购合同、入库单、发票、记账凭证、付款回单。
- [x] 文件保存到 `local_storage/uploads`。
- [x] 数据库存在对应 `documents` 记录。
- [x] 上传失败不会产生脏数据。

### 交付物

- [x] Task Center 页面。
- [x] Document Upload 页面或组件。
- [x] `audit_tasks` 和 `documents` migration。
- [x] task/document API。

### 风险点

- [x] 文件大小和类型校验不足。
- [x] 重复上传导致重复业务记录。
- [x] local storage 路径设计不稳定。

### 不允许额外扩展的边界说明

- [x] 不做销售、函证、访谈、合同审核上传流程。
- [x] 不做云存储。
- [x] 不做复杂权限控制。

## Phase 2: OCR / 文档解析 / 页级文本保存

- Phase 名称：OCR / 文档解析 / 页级文本保存
- 是否属于 MVP：是
- Status: DONE

### Notes

- 2026-07-04: Phase 2 完成 `document_pages` migration、文本型 PDF 页级解析、Basic OCR Provider 边界、OCR 状态/错误记录、pages API、Task Center 页级文本查看和 OCR API 测试。未实现 Phase 3 文档分类或后续模块。

### 阶段目标

将上传文件解析为页级文本、OCR blocks、表格块和置信度，为分类和抽取提供输入。

### 后端任务

- [x] 实现 `OCRService`。
- [x] 支持 PDF 文本解析。
- [x] 支持图片或扫描件通过 OCR Provider 处理。
- [x] 保存页码、raw_text、ocr_blocks、table_blocks。
- [x] OCR 失败时记录失败状态和错误原因。

### 前端任务

- [x] 在文档详情展示 OCR 状态。
- [x] 展示页级 raw_text。
- [x] 支持页码切换。
- [x] 展示 OCR 失败提示。

### 数据库 / Migration 任务

- [x] 创建 `document_pages` 表。
- [x] 为 `documents` 增加或使用 `ocr_status`, `page_count`。
- [x] 保留 `ocr_blocks` JSONB。
- [x] 保留 `table_blocks` JSONB。

### API 任务

- [x] `POST /api/v1/documents/{document_id}/ocr`。
- [x] `GET /api/v1/documents/{document_id}/pages`。

### 测试任务

- [x] 测试 PDF 样例可解析出页级文本。
- [x] 测试 OCR 失败不会导致任务不可查看。
- [x] 测试 `document_pages` 页码顺序正确。
- [x] 测试空文本页面会标记 warning。

### 验收标准

- [x] 每份文档至少生成一条或多条 `document_pages`。
- [x] 每页包含 `page_number`, `raw_text`, `ocr_blocks`。
- [x] OCR 状态可从前端看到。
- [x] 后续分类服务可以读取页级文本。

### 交付物

- [x] OCR/解析服务。
- [x] `document_pages` migration。
- [x] OCR API。
- [x] 页级文本查看组件。

### 风险点

- [x] 扫描件质量差导致 OCR 不稳定。
- [x] 表格结构识别错列。
- [x] OCR 处理耗时导致请求超时。

### 不允许额外扩展的边界说明

- [x] 不做复杂 bbox 高亮。
- [x] 不做表格纠错 UI。
- [x] 不引入 Celery / Redis，除非 Phase 10 后重新评估。

## Phase 3: 文档分类

- Phase 名称：文档分类
- 是否属于 MVP：是
- Status: DONE

### Notes

- 2026-07-04: Phase 3 完成规则关键词 + 文件名启发式 `ClassificationService`、六类采购文档分类、低置信度 `unknown` / `need_review` 标记、人工修正文档类型、原始分类快照保留、分类 API、Task Center 分类展示与修正入口，以及后端分类测试。未实现 Phase 4 字段抽取或任何 Post-MVP 分类扩展。

### 阶段目标

识别六类采购文档类型，输出 doc_type、置信度、分类理由和低置信度复核标记。

### 后端任务

- [x] 实现 `ClassificationService`。
- [x] 支持六类采购 doc_type。
- [x] 使用 OCR 文本和文件名进行分类。
- [x] 输出置信度、分类理由、候选类型。
- [x] 低置信度时标记需要复核。

### 前端任务

- [x] 在文档列表展示 doc_type 和置信度。
- [x] 展示分类理由。
- [x] 提供人工修正文档类型入口。
- [x] 标记低置信度文档。

### 数据库 / Migration 任务

- [x] 使用 `documents.doc_type`。
- [x] 使用 `documents.doc_type_confidence`。
- [x] 使用 `documents.classification_reason`。
- [x] 使用 `documents.review_status` 标记低置信度复核。
- [x] 使用 `documents.alternative_types` 保存候选类型。
- [x] 使用 `documents.original_classification` 保存人工修正前的原始分类快照。

### API 任务

- [x] `POST /api/v1/documents/{document_id}/classify`。
- [x] `PATCH /api/v1/documents/{document_id}` 支持人工修正 doc_type。

### 测试任务

- [x] 六类采购样例分类测试。
- [x] 低置信度阈值测试。
- [x] 人工修正 doc_type 测试。
- [x] 未 OCR 文档不允许分类或返回明确错误。

### 验收标准

- [x] 六类采购文件可被分类。
- [x] 分类结果包含 doc_type、confidence、reason。
- [x] 低置信度进入复核队列或被标记为需要复核。
- [x] 人工修正分类不覆盖原始分类理由。

### 交付物

- [x] ClassificationService。
- [x] 分类 API。
- [x] 文档分类展示和修正 UI。

### 风险点

- [x] 发票、付款回单、记账凭证字段相似导致混淆。
- [x] 文件名误导分类。
- [x] 低置信度阈值设置不合理。

### 不允许额外扩展的边界说明

- [x] 不支持销售、函证、访谈、合同审核分类标签的完整流程。
- [x] 不做复杂训练系统。
- [x] 不做分类 Evaluation Center UI。

## Phase 4: 字段抽取与 Schema 校验

- Phase 名称：字段抽取与 Schema 校验
- 是否属于 MVP：是
- Status: DONE

### Notes

- 2026-07-04: Phase 4 完成 `extracted_fields` migration、六类采购文档 MVP Schema、规则/正则 `ExtractionService`、日期/金额/税率/名称基础标准化、缺失字段 null + warning、基础 `line_items` 结构、extract/fields API、Task Center 字段表和后端抽取测试。未实现 Phase 5 业务归集、Phase 6 规则判断、Phase 8 字段人工修正或任何 Post-MVP 功能。

### 阶段目标

按六类采购文档 Schema 抽取关键字段、line_items、标准化值和来源证据，并通过 Pydantic 校验。

### 后端任务

- [x] 实现 `ExtractionService`。
- [x] 定义通用字段结构：field_name、value、confidence、source_page、source_text、source_bbox。
- [x] 定义六类采购文档 MVP Schema。
- [x] 支持日期、金额、税率、名称标准化。
- [x] 缺失字段输出 null 和 warning，不允许编造。
- [x] 保存字段到 `extracted_fields`。

### 前端任务

- [x] 展示字段表。
- [x] 展示字段置信度。
- [x] 展示字段来源页和来源文本。
- [x] 标记缺失字段和低置信度字段。

### 数据库 / Migration 任务

- [x] 创建 `extracted_fields` 表。
- [x] 支持 `value_text`。
- [x] 支持 `value_normalized` JSONB。
- [x] 支持 `source_page`, `source_bbox`, `source_text`。
- [x] 支持 `is_required`, `is_verified`, `corrected_by`, `corrected_at`。

### API 任务

- [x] `POST /api/v1/documents/{document_id}/extract`。
- [x] `GET /api/v1/documents/{document_id}/fields`。
- [x] `GET /api/v1/tasks/{task_id}/fields`。

### 测试任务

- [x] Pydantic Schema 校验测试。
- [x] 缺字段输出 null 和 warning 测试。
- [x] 金额和日期标准化测试。
- [x] line_items 基础结构测试。
- [x] LLM 输出非法 JSON 时失败可记录。

### 验收标准

- [x] 六类采购文档都有 MVP 字段列表。
- [x] 每个字段都能追溯到页码和来源片段。
- [x] 必填字段缺失不会默认通过。
- [x] 抽取结果可被 Rule Engine 读取。

### 交付物

- [x] ExtractionService。
- [x] 六类采购 Pydantic Schema。
- [x] `extracted_fields` migration。
- [x] 字段表 UI。

### 风险点

- [x] LLM 编造缺失字段。
- [x] OCR 表格错列导致金额、税额、数量串位。
- [x] 多行明细被合并。

### 不允许额外扩展的边界说明

- [x] 不做所有行业字段。
- [x] 不做复杂单位换算。
- [x] 不做完整合同条款抽取。

## Phase 5: 采购业务归集

- Phase 名称：采购业务归集
- 是否属于 MVP：是
- Status: DONE

### Notes

- 2026-07-04: Phase 5 完成 `LinkageService`、`documents.business_key`、`document_relations` migration、任务内采购文档归集 API、Task Center 业务链路展示、合同号/发票号/付款用途/凭证摘要辅助归集、供应商+日期+金额低置信度归集、低置信度 `need_review` 标记和后端 linkage 测试。未实现 Phase 6 Rule Engine、Review Center、复杂图谱匹配、跨任务归集或人工关系编辑。

### 阶段目标

将同一笔采购业务下的申请单、合同、入库单、发票、凭证、付款回单归集为 business_key 和 document_relations。

### 后端任务

- [x] 实现 `LinkageService`。
- [x] 优先按合同号、发票号、银行流水号、凭证摘要归集。
- [x] 缺少显式编号时使用供应商、日期、金额组合匹配。
- [x] 低置信度归集标记为需要复核。
- [x] 支持一合同多发票、多付款的基础聚合。

### 前端任务

- [x] 展示 business_key。
- [x] 展示同一业务链路下的文件关系。
- [x] 标记低置信度归集。
- [x] 提供人工查看关系的入口。

### 数据库 / Migration 任务

- [x] 创建 `document_relations` 表。
- [x] 使用 `documents.business_key`。
- [x] relation 记录 source_document_id、target_document_id、relation_type、confidence、evidence。

### API 任务

- [x] `POST /api/v1/tasks/{task_id}/link-documents`。
- [x] `GET /api/v1/tasks/{task_id}/document-relations`。

### 测试任务

- [x] 合同号归集测试。
- [x] 发票号/回单用途归集测试。
- [x] 低置信度归集测试。
- [x] 一对多发票或付款基础聚合测试。

### 验收标准

- [x] 能为采购样例生成 business_key。
- [x] 能生成 document_relations。
- [x] 归集证据可查看。
- [x] 低置信度归集不自动通过。

### 交付物

- [x] LinkageService。
- [x] `document_relations` migration。
- [x] 业务链路 API。
- [x] 业务链路展示 UI。

### 风险点

- [x] 编号缺失导致错配。
- [x] 分批付款被误认为异常。
- [x] 供应商别名导致主体不一致误报。

### 不允许额外扩展的边界说明

- [x] 不做复杂图谱匹配。
- [x] 不做跨任务归集。
- [x] 不做销售链路归集。

## Phase 6: Rule Engine MVP

- Phase 名称：Rule Engine MVP
- 是否属于 MVP：是
- Status: DONE

### Notes

- 2026-07-04: Phase 6 完成确定性 `RuleEngineService`、`RuleContext`、`RuleResult`、`EvidenceRef`、Python rule registry、六条采购 MVP 规则、`audit_rules` / `audit_results` migration 和六条规则初始化、audit/rules API、Task Center 规则结果只读展示、规则 pass/non-pass/缺字段/evidence/多发票多付款/低置信度 warning 测试。未实现 Phase 7 Audit Workbench、Phase 8 Review Center、Phase 12 Rule Center、RAG、Agent 或 LLM pass/fail 判断。

### 阶段目标

使用 Python rule registry 实现采购穿行核心规则，输出可追溯、可复核、可测试的 audit_results。

### 后端任务

- [x] 实现 `RuleEngineService`。
- [x] 定义 `RuleContext`。
- [x] 定义 `RuleResult`。
- [x] 实现规则注册表。
- [x] 实现 `PROC_MISSING_001`。
- [x] 实现 `PROC_TIME_001`。
- [x] 实现 `PROC_AMOUNT_001`。
- [x] 实现 `PROC_NAME_001`。
- [x] 实现 `PROC_QTY_001`。
- [x] 实现 `PROC_TAX_001`。
- [x] 规则结果写入 `audit_results`。

### 前端任务

- [x] 展示规则结果表。
- [x] 展示 rule_code、status、severity、message。
- [x] 展示 expected_value、actual_value。
- [x] 展示 evidence。
- [x] 标记需要人工复核的规则结果。

### 数据库 / Migration 任务

- [x] 创建 `audit_rules` 表。
- [x] 创建 `audit_results` 表。
- [x] 初始化六条采购规则数据。
- [x] 支持规则启用状态、版本、参数。

### API 任务

- [x] `POST /api/v1/tasks/{task_id}/audit`。
- [x] `GET /api/v1/tasks/{task_id}/audit-results`。
- [x] `GET /api/v1/audit-results/{result_id}`。
- [x] `GET /api/v1/rules`。

### 测试任务

- [x] 每条规则至少一个 pass 样例。
- [x] 每条规则至少一个 fail 或 need_review 样例。
- [x] 缺字段不得 pass 测试。
- [x] 规则结果 evidence 非空测试。
- [x] 一合同多发票/付款基础金额测试。

### 验收标准

- [x] 六条 MVP 规则可执行。
- [x] 规则输出包含 rule_code、status、severity、message、expected_value、actual_value、evidence。
- [x] 缺字段输出 need_review。
- [x] 高风险 fail 进入 Review Center。
- [x] 规则单测可运行。

### MVP 规则边界补充

- MVP 中 `PROC_QTY_001` 只覆盖基础 `line_items` 数量一致性。
- MVP 中 `PROC_TAX_001` 只覆盖基础税率、税额、含税/不含税口径校验。
- 完整品种一致性、复杂多品种逐行匹配、单位换算、item_key 标准化和复杂品种映射后置到 Post-MVP Rule Center / 规则增强阶段。
- MVP 不新增独立 `PROC_ITEM_001`，除非 Phase 6 完成后仍有明确时间。

### 交付物

- [x] Python rule registry。
- [x] Procurement rules。
- [x] Rule Engine API。
- [x] 规则结果 UI。

### 风险点

- [x] 规则误报或漏报。
- [x] 缺字段被错误当成通过。
- [x] 多品种和多付款聚合不准确。

### 不允许额外扩展的边界说明

- [x] 不做复杂 DSL。
- [x] 不做 Rule Center 可视化配置。
- [x] 不让 LLM 直接判断 pass/fail。

## Phase 7: Audit Workbench 前端工作台

- Phase 名称：Audit Workbench 前端工作台
- 是否属于 MVP：是
- Status: DONE

### Notes

- 2026-07-04: Phase 7 完成只读 Audit Workbench 三栏工作台，复用现有任务文档、页级 OCR、任务字段和审计结果 API；实现左侧文档状态列表、中间 OCR 页级文本与证据片段、右侧字段表和规则结果表、字段 source_text 跳转、规则 evidence 到字段来源页映射、ReviewDrawer 只读占位入口、Task Center 进入工作台入口。未新增数据库表、未新增规则、未实现 Phase 8 Review Center 操作、字段修正、异常确认/驳回或规则重跑。

### 阶段目标

实现采购穿行核心审核工作台：左侧文档列表，中间 OCR 文本和证据片段，右侧字段表、规则结果、复核操作入口。

### 后端任务

- [x] 提供工作台所需聚合数据接口或组合查询。
- [x] 确保文档、页、字段、规则结果可按 task_id 查询。
- [x] 提供证据引用跳转所需数据。

### 前端任务

- [x] 实现 `AuditWorkbenchPage`。
- [x] 实现左侧 DocumentList。
- [x] 实现中间 DocumentViewer / OCRTextViewer。
- [x] 实现右侧 FieldTable。
- [x] 实现右侧 RuleResultTable。
- [x] 实现 ReviewDrawer 入口。
- [x] 支持从规则 evidence 定位到文档页和来源文本。

### 数据库 / Migration 任务

- [x] 不新增表。
- [x] 校验现有字段足够支撑证据定位。

### API 任务

- [x] `GET /api/v1/tasks/{task_id}/workbench` 或复用已有 API。
- [x] `GET /api/v1/documents/{document_id}/pages`。
- [x] `GET /api/v1/tasks/{task_id}/fields`。
- [x] `GET /api/v1/tasks/{task_id}/audit-results`。

### 测试任务

- [x] 手工验证三栏布局。
- [x] 测试规则结果点击后能定位证据。
- [x] 测试字段缺失和异常状态展示。
- [x] 测试空任务和无文档状态。

### 验收标准

- [x] 用户可在一个页面查看文档、字段、规则结果。
- [x] 异常可以定位到来源文档和页级文本。
- [x] 页面不依赖完整 bbox 高亮也能完成复核。
- [x] 页面能支撑 MVP 演示。

### 交付物

- [x] Audit Workbench 页面。
- [x] DocumentViewer。
- [x] FieldTable。
- [x] RuleResultTable。
- [x] Evidence 跳转能力。

### 风险点

- [x] 过早追求复杂 UI。
- [x] bbox 高亮消耗过多时间。
- [x] 前端状态管理过度复杂。

### 不允许额外扩展的边界说明

- [x] 不做复杂 bbox 高亮。
- [x] 不做 RAG citation 面板。
- [x] 不做 Agent timeline。
- [x] 不做多场景工作台。

## Phase 8: Review Center 基础复核闭环

- Phase 名称：Review Center 基础复核闭环
- 是否属于 MVP：是
- Status: DONE

### Notes

- 2026-07-04: Phase 8 完成 `ReviewService`、`review_comments` / `audit_logs` migration、Review Queue、字段修正 before/after 留痕、字段修正保留原始 `source_page` / `source_text` / `source_bbox`、异常确认、驳回异常强制原因、调用既有 `RuleEngineService.run_audit` 重跑规则、review comments 查询和新增、Review Center 队列 UI、复核意见历史、Audit Workbench ReviewDrawer 真实复核操作接入、后端 review API 测试。未实现 Phase 9 Report Center、xlsx 导出、完整 Bad Case Center、完整 RBAC、RAG、Agent 或 Post-MVP 功能。

### 阶段目标

实现低置信度、缺字段、规则异常的人工复核闭环，包括字段修正、异常确认、驳回异常、重跑规则和审计留痕。

### 后端任务

- [x] 实现 `ReviewService`。
- [x] 支持字段修正并保留 before / after。
- [x] 支持异常确认。
- [x] 支持驳回异常并要求填写原因。
- [x] 支持字段修正后重跑相关规则。
- [x] 所有复核动作写入 audit_logs。

### 前端任务

- [x] 实现 Review Center 复核队列。
- [x] 实现字段修正表单。
- [x] 实现确认异常按钮。
- [x] 实现驳回异常按钮。
- [x] 实现重跑规则按钮。
- [x] 展示复核意见历史。

### 数据库 / Migration 任务

- [x] 创建 `review_comments` 表。
- [x] 创建 `audit_logs` 表。
- [x] 使用 `audit_results.review_status`。
- [x] 使用 `extracted_fields.is_verified`, `corrected_by`, `corrected_at`。

### API 任务

- [x] `GET /api/v1/review/queue`。
- [x] `POST /api/v1/review/comments`。
- [x] `PATCH /api/v1/fields/{field_id}`。
- [x] `POST /api/v1/audit-results/{result_id}/confirm`。
- [x] `POST /api/v1/audit-results/{result_id}/dismiss`。
- [x] `POST /api/v1/audit-results/{result_id}/rerun`。

### 测试任务

- [x] 字段修正 before / after 测试。
- [x] 驳回异常必须填写原因测试。
- [x] 高风险异常不能自动关闭测试。
- [x] 修正后重跑规则测试。
- [x] audit_logs 写入测试。

### 验收标准

- [x] 异常结果能进入复核队列。
- [x] 字段修正不覆盖原始证据。
- [x] 确认和驳回异常可记录。
- [x] 字段修正后可重跑规则。
- [x] 复核动作可审计。

### Bad Case 边界补充

- MVP 阶段 Review Center 不实现完整 Bad Case Center UI。
- MVP 阶段可以在代码注释、接口设计或 review action 枚举中预留 `bad_case_candidate`，但不开发完整 Bad Case 流程。
- 实际 Bad Case 创建、筛选、根因分析、修复方案和回归评测在 Phase 14 完成。

### 交付物

- [x] Review Center 页面。
- [x] ReviewService。
- [x] 复核 API。
- [x] audit_logs。

### 风险点

- [x] 人工修正覆盖原始数据。
- [x] 复核意见没有进入报告。
- [x] 高风险异常被错误自动关闭。

### 不允许额外扩展的边界说明

- [x] 不做完整用户角色权限。
- [x] 不做复杂工单系统。
- [x] 不做 Bad Case Center UI。

## Phase 9: Report Center 控制表与异常清单导出

- Phase 名称：Report Center 控制表与异常清单导出
- 是否属于 MVP：是
- Status: DONE

### Notes

- 2026-07-04: Phase 9 完成 `ReportService`、标准库 xlsx 生成器、Summary / Procurement Control Table / Exceptions / Evidence Index / Field Corrections / Rule Definitions 六个 sheet、`control_table_rows` / `reports` migration、报告保存到 `local_storage/reports` 并写入 `reports.storage_path`、控制表行写入 `control_table_rows`、报告摘要和预览写入 `summary`、生成/列表/下载 API、Report Center 报告生成状态、控制表预览、报告历史和 xlsx 下载入口、Task Center 进入 Report Center 入口、后端 report API/xlsx sheet 测试。未实现 Phase 10 README/Docker 最终交付整理、PDF 报告、复杂模板、Dashboard、RAG、Agent、Evaluation、RBAC 或 Post-MVP 功能。

### 阶段目标

导出采购穿行控制表、异常清单、证据索引、字段修正记录和规则定义 xlsx 文件。

### 后端任务

- [x] 实现 `ReportService`。
- [x] 生成 Summary sheet。
- [x] 生成 Procurement Control Table sheet。
- [x] 生成 Exceptions sheet。
- [x] 生成 Evidence Index sheet。
- [x] 生成 Field Corrections sheet。
- [x] 生成 Rule Definitions sheet。
- [x] 保存报告文件并写入 `reports`。

### 前端任务

- [x] 实现 Report Center 页面。
- [x] 展示控制表预览。
- [x] 展示报告生成状态。
- [x] 提供 xlsx 下载入口。
- [x] 展示报告历史。

### 数据库 / Migration 任务

- [x] 创建 `control_table_rows` 表。
- [x] 创建 `reports` 表。
- [x] 报告路径保存到 `storage_path`。
- [x] 报告摘要保存到 `summary` JSONB。

### API 任务

- [x] `POST /api/v1/tasks/{task_id}/reports/control-table`。
- [x] `GET /api/v1/tasks/{task_id}/reports`。
- [x] `GET /api/v1/reports/{report_id}/download`。

### 测试任务

- [x] xlsx 文件可生成测试。
- [x] sheet 名称完整测试。
- [x] 异常清单包含 rule_code 和 evidence 测试。
- [x] 字段修正记录导出测试。
- [x] 报告记录写入 `reports` 测试。

### 验收标准

- [x] 可导出 xlsx。
- [x] xlsx 包含全部 MVP sheet。
- [x] 控制表每行可追溯 business_key。
- [x] 异常清单不隐藏失败规则。
- [x] 证据索引包含文件、页码、来源文本。

### 交付物

- [x] ReportService。
- [x] Report Center 页面。
- [x] xlsx 导出文件。
- [x] `control_table_rows` 和 `reports` migration。

### 风险点

- [x] 导出数据与页面展示不一致。
- [x] 复核意见漏导。
- [x] 报告路径泄露本地敏感目录。

### 不允许额外扩展的边界说明

- [x] 不做 PDF 报告。
- [x] 不做复杂报表模板系统。
- [x] 不做管理层 Dashboard。

## Phase 10: MVP 测试、演示数据、README 和 Docker 交付

- Phase 名称：MVP 测试、演示数据、README 和 Docker 交付
- 是否属于 MVP：是
- Status: DONE

### Notes

- 2026-07-04: 完成 Phase 10 MVP 可复现交付。已补齐 `model_invocations` model 和 migration、synthetic demo samples、`scripts/seed_demo_data.py`、MVP smoke test、README、本地/Docker 启动说明、API 草稿和 MVP 验收记录。验证通过：`alembic upgrade head`、全量 `pytest`、前端 `npm run build`、`docker compose config`、PostgreSQL 容器 healthy、`pg_isready`、`select 1`、临时空库顺序执行全部 migrations。未开发 Phase 11 或 Post-MVP 功能。

### 阶段目标

完成采购穿行 MVP 的可复现交付：测试、演示数据、README、Docker Compose、基础文档。

### 后端任务

- [x] 清理 MVP API 响应结构。
- [x] 记录模型调用到 `model_invocations`。
- [x] 补齐错误处理。
- [x] 补齐 seed demo data 脚本。

### 前端任务

- [x] 打磨 MVP 演示路径。
- [x] 处理空状态、错误状态、加载状态。
- [x] 确保 Task Center -> Workbench -> Review -> Report 链路可用。

### 数据库 / Migration 任务

- [x] 创建 `model_invocations` 表。
- [x] 检查 Phase 0-9 migrations 可从空库顺序执行。
- [x] 准备 demo seed 数据。

### API 任务

- [x] 确认 MVP API 路径稳定。
- [x] 补齐 API 文档草稿。
- [x] 确认下载接口可在 Docker 环境工作。

### 测试任务

- [x] 规则单测全部通过。
- [x] 关键 API 测试通过。
- [x] 报告导出测试通过。
- [x] 端到端采购 demo smoke test 通过。
- [x] Docker Compose 启动验证通过。

### 验收标准

- [x] 新环境可以按 README 启动。
- [x] 采购穿行 MVP 能从任务创建跑到报告导出。
- [x] 不包含真实密钥和真实敏感数据。
- [x] 测试命令可运行。
- [x] Phase 10 完成后才允许启动 Phase 11-20。

### 交付物

- [x] README。
- [x] Docker Compose。
- [x] demo samples。
- [x] seed 脚本。
- [x] MVP 测试报告。

### 风险点

- [x] 演示数据不足。
- [x] Docker 环境和本地环境不一致。
- [x] README 与实际命令不一致。

### 不允许额外扩展的边界说明

- [x] 不在 MVP 结束前引入 Post-MVP 模块开发。
- [x] 不补做完整 RAG、Agent、Evaluation、RBAC。
- [x] 不加入未验收的多场景功能。

## Phase 11: RAG 四库扩展

- Phase 名称：RAG 四库扩展
- 是否属于 MVP：否
- Status: DONE

### Notes

- 2026-07-04: Phase 11 完成 RAG 四库扩展。已启用 pgvector extension，新增 `rag_documents` / `rag_chunks` migration 和模型，实现 deterministic local embedding provider、文本/PDF 基础解析、按段落/固定长度 chunking、metadata filter、pgvector 相似度检索、citation 输出、no-answer handling、workpaper 与公开知识库按 `knowledge_base` 强隔离、RAG API 和 Knowledge Center。验证通过：`alembic upgrade head`、临时空库 migration、RAG API tests、全量 `pytest`、前端 `npm run build`、`docker compose config`。未实现 Phase 12 Rule Center、Phase 13 Agent、Phase 14 Evaluation/Bad Case、RBAC 或其他 Post-MVP 场景。

### 阶段目标

在 MVP 完成后扩展 regulation、inquiry_case、prospectus、workpaper 四类知识库，支持 citation 和 no-answer handling。

### 后端任务

- [x] 实现 `RagService`。
- [x] 实现文档解析和 chunking。
- [x] 实现 embedding provider。
- [x] 实现 pgvector 检索。
- [x] 实现 metadata filter。
- [x] 实现 citation 输出。
- [x] 实现 no-answer handling。

### 前端任务

- [x] 实现 Knowledge Center。
- [x] 支持四库文档列表。
- [x] 支持检索测试。
- [x] 展示 citations、score、metadata。
- [x] 在异常结果中展示 RAG 引用。

### 数据库 / Migration 任务

- [x] 启用 pgvector extension。
- [x] 创建 `rag_documents` 表。
- [x] 创建 `rag_chunks` 表。
- [x] 为 chunk 保存 knowledge_base、title、section、page、metadata、embedding。

### API 任务

- [x] `POST /api/v1/rag/documents`。
- [x] `POST /api/v1/rag/documents/{doc_id}/index`。
- [x] `POST /api/v1/rag/query`。
- [x] `GET /api/v1/rag/chunks/{chunk_id}`。

### 测试任务

- [x] chunking 测试。
- [x] metadata filter 测试。
- [x] no-answer 测试。
- [x] citation schema 测试。
- [x] RAG smoke evaluation。

### 验收标准

- [x] 四库可分别入库和检索。
- [x] workpaper 与公开知识库隔离。
- [x] 回答包含 citations。
- [x] 检索不到依据时返回证据不足。

### 交付物

- [x] RagService。
- [x] Knowledge Center。
- [x] pgvector migration。
- [x] RAG API。

### 风险点

- [x] 检索结果不相关。
- [x] 公开知识库和 workpaper 混淆。
- [x] 引用不能支撑回答。

### 不允许额外扩展的边界说明

- [x] 不替代 Rule Engine。
- [x] 不让 RAG 输出最终审核结论。
- [x] 不做自动法规更新系统。

## Phase 12: Rule Center 规则版本化与参数配置

- Phase 名称：Rule Center 规则版本化与参数配置
- 是否属于 MVP：否
- Status: TODO

### 阶段目标

在 Rule Engine MVP 稳定后，增加规则启用状态、版本、参数、别名表和品种映射配置能力。

### 后端任务

- [ ] 扩展 `RuleEngineService` 参数加载。
- [ ] 支持规则启用/禁用。
- [ ] 支持规则版本号。
- [ ] 支持容忍差额参数。
- [ ] 支持供应商别名参数。
- [ ] 支持品种映射参数。

### 前端任务

- [ ] 实现 Rule Center 规则列表。
- [ ] 实现规则详情。
- [ ] 实现启用/禁用操作。
- [ ] 实现参数编辑。
- [ ] 实现规则测试入口。

### 数据库 / Migration 任务

- [ ] 扩展或确认 `audit_rules.parameters`。
- [ ] 扩展或确认 `audit_rules.version`。
- [ ] 扩展或确认 `audit_rules.enabled`。
- [ ] 记录规则修改 audit_logs。

### API 任务

- [ ] `GET /api/v1/rules`。
- [ ] `POST /api/v1/rules`。
- [ ] `PATCH /api/v1/rules/{rule_id}`。
- [ ] `POST /api/v1/rules/{rule_id}/evaluate`。

### 测试任务

- [ ] 规则启用/禁用测试。
- [ ] 参数变更影响规则结果测试。
- [ ] 规则版本写入 audit_results 测试。
- [ ] 规则修改审计日志测试。

### 验收标准

- [ ] 规则可启用和禁用。
- [ ] 规则参数可配置。
- [ ] 规则版本可追踪。
- [ ] 规则结果可复现。

### 交付物

- [ ] Rule Center 页面。
- [ ] 规则配置 API。
- [ ] 规则版本和参数测试。

### 风险点

- [ ] 过早设计 DSL。
- [ ] 参数配置导致历史结果不可复现。
- [ ] 非技术用户误改规则。

### 不允许额外扩展的边界说明

- [ ] 不做复杂 DSL。
- [ ] 不做可视化拖拽规则编辑器。
- [ ] 不允许规则绕过代码审查直接执行任意表达式。

## Phase 13: Agent Workflow 状态机与工具调用

- Phase 名称：Agent Workflow 状态机与工具调用
- 是否属于 MVP：否
- Status: TODO

### 阶段目标

在 Rule Engine、Review Center、Report Center 稳定后，引入受控状态机和工具调用，记录每一步输入、输出、状态和错误。

### 后端任务

- [ ] 实现 `AgentService`。
- [ ] 定义状态机。
- [ ] 定义工具白名单。
- [ ] 实现 agent run 创建。
- [ ] 实现 agent step 记录。
- [ ] 实现失败步骤重试。
- [ ] 实现人工复核路由。

### 前端任务

- [ ] 实现 AgentStateTimeline。
- [ ] 展示 agent run 状态。
- [ ] 展示步骤输入引用和输出引用。
- [ ] 提供失败步骤重试入口。

### 数据库 / Migration 任务

- [ ] 创建 `agent_runs` 表。
- [ ] 创建 `agent_steps` 表。
- [ ] 保存状态、输入引用、输出引用、错误、耗时。

### API 任务

- [ ] `POST /api/v1/agents/runs`。
- [ ] `GET /api/v1/agents/runs/{run_id}`。
- [ ] `GET /api/v1/agents/runs/{run_id}/steps`。
- [ ] `POST /api/v1/agents/runs/{run_id}/retry`。

### 测试任务

- [ ] 状态转移合法性测试。
- [ ] 失败步骤重试测试。
- [ ] 高风险异常进入人工复核测试。
- [ ] Agent 不绕过 Rule Engine 测试。

### 验收标准

- [ ] Agent 可从上传推进到报告生成。
- [ ] 每一步有状态、输入引用、输出引用和耗时。
- [ ] 失败步骤可重试。
- [ ] Agent 不能自动确认高风险异常。
- [ ] Agent 不能绕过 Rule Engine 直接生成 pass/fail。
- [ ] Agent 不能在无 citation 时生成依据性结论。

### 交付物

- [ ] AgentService。
- [ ] agent_runs / agent_steps migration。
- [ ] AgentStateTimeline。
- [ ] Agent API。

### 风险点

- [ ] Agent 状态混乱。
- [ ] Agent 重复执行造成结果不一致。
- [ ] 工具调用日志泄露敏感原文。

### 不允许额外扩展的边界说明

- [ ] Agent 不能绕过 Rule Engine。
- [ ] Agent 不能自动确认高风险异常。
- [ ] Agent 不能生成无证据审核结论。

## Phase 14: Bad Case Center 与 Evaluation Center

- Phase 名称：Bad Case Center 与 Evaluation Center
- 是否属于 MVP：否
- Status: TODO

### 阶段目标

建立错误样例和质量评测闭环，覆盖分类、OCR、字段抽取、Rule Engine、RAG、Agent、端到端采购穿行和 Bad Case 回归。

### 后端任务

- [ ] 实现 `BadCaseService`。
- [ ] 实现 `EvaluationService`。
- [ ] 支持创建、更新、筛选 Bad Case。
- [ ] 支持运行评测脚本。
- [ ] 支持失败样例转 Bad Case。
- [ ] 支持 Bad Case 回归集。

### 前端任务

- [ ] 实现 Bad Case Center。
- [ ] 实现 Evaluation Center。
- [ ] 展示评测指标。
- [ ] 展示失败样例。
- [ ] 支持 Bad Case 状态更新。

### 数据库 / Migration 任务

- [ ] 创建 `bad_cases` 表。
- [ ] 创建 `evaluation_results` 表。
- [ ] 保存 metrics、failed_cases、dataset_name、model_name、prompt_version、rule_version。

### API 任务

- [ ] `POST /api/v1/bad-cases`。
- [ ] `GET /api/v1/bad-cases`。
- [ ] `PATCH /api/v1/bad-cases/{case_id}`。
- [ ] `POST /api/v1/evaluations/run`。
- [ ] `GET /api/v1/evaluations/results`。

### 测试任务

- [ ] Bad Case CRUD 测试。
- [ ] 规则评测脚本测试。
- [ ] 字段抽取 expected JSON 对比测试。
- [ ] 回归评测测试。

### 验收标准

- [ ] 能创建和筛选 Bad Case。
- [ ] 每个 Bad Case 有输入、输出、期望、根因、修复方案。
- [ ] 评测结果记录指标和失败样例。
- [ ] Bad Case 能进入回归评测。

### 交付物

- [ ] Bad Case Center。
- [ ] Evaluation Center。
- [ ] 评测脚本。
- [ ] bad_cases / evaluation_results migration。

### 风险点

- [ ] 标注集不足。
- [ ] 指标不可复现。
- [ ] Bad Case 只记录不回归。

### 不允许额外扩展的边界说明

- [ ] 不做虚假的高指标展示。
- [ ] 不用真实敏感客户数据作为公开样例。
- [ ] 不把 Evaluation Center 放到 MVP 前置。

## Phase 15: 销售穿行扩展

- Phase 名称：销售穿行扩展
- 是否属于 MVP：否
- Status: TODO

### 阶段目标

复用采购穿行框架，扩展销售合同、订单、出库、物流签收、销售发票、收款凭证、记账凭证链路。

### 后端任务

- [ ] 定义销售穿行 doc_type。
- [ ] 定义销售字段 Schema。
- [ ] 扩展分类逻辑。
- [ ] 扩展字段抽取。
- [ ] 扩展销售业务归集。
- [ ] 实现销售穿行规则。
- [ ] 生成销售控制表。

### 前端任务

- [ ] Task Center 支持 sales 场景。
- [ ] Workbench 支持销售字段展示。
- [ ] Report Center 支持销售控制表。
- [ ] Review Center 复用销售异常。

### 数据库 / Migration 任务

- [ ] 优先复用现有表。
- [ ] 如必须新增字段，先在 tracker 中补充并评审。
- [ ] control_table_rows 支持 sales scenario。

### API 任务

- [ ] 复用 task/document/extraction/linkage/audit/report API。
- [ ] 增加 sales scenario 参数校验。
- [ ] 增加销售规则结果筛选。

### 测试任务

- [ ] 销售样例分类测试。
- [ ] 销售字段抽取测试。
- [ ] 销售时间顺序规则测试。
- [ ] 销售控制表导出测试。

### 验收标准

- [ ] 至少一组销售穿行样例端到端跑通。
- [ ] 销售异常能进入 Review Center。
- [ ] 销售报告可导出。
- [ ] 不影响采购 MVP。

### 交付物

- [ ] 销售 Schema。
- [ ] 销售规则。
- [ ] 销售控制表。
- [ ] 销售样例数据。

### 风险点

- [ ] 一合同多订单、多发货、多开票导致复杂度上升。
- [ ] 收入确认规则需要业务政策支持。
- [ ] 客户名称和付款方不一致导致误报。

### 不允许额外扩展的边界说明

- [ ] 不做完整收入准则判断。
- [ ] 不做跨期收入复杂审计模型。
- [ ] 不影响采购穿行规则。

## Phase 16: 函证模块扩展

- Phase 名称：函证模块扩展
- 是否属于 MVP：否
- Status: TODO

### 阶段目标

支持函证发函、回函、账面金额、回函金额和差异调节的字段抽取、规则比对和复核。

### 后端任务

- [ ] 定义 confirmation doc_type。
- [ ] 定义函证字段 Schema。
- [ ] 实现函证字段抽取。
- [ ] 实现账面金额和回函金额比对规则。
- [ ] 实现差异调节检查。

### 前端任务

- [ ] Task Center 支持 confirmation 场景。
- [ ] Workbench 支持函证字段展示。
- [ ] Review Center 支持函证差异复核。
- [ ] Report Center 支持函证差异清单。

### 数据库 / Migration 任务

- [ ] 优先复用 `documents`, `extracted_fields`, `audit_results`。
- [ ] 如差异调节需要结构化表，先补充 tracker 后再开发。

### API 任务

- [ ] 复用文档处理 API。
- [ ] 复用抽取 API。
- [ ] 复用 audit API。
- [ ] 复用 report API。

### 测试任务

- [ ] 函证字段抽取测试。
- [ ] 回函日期早于发函日期测试。
- [ ] 回函金额与账面金额不一致测试。
- [ ] 差异调节缺失测试。

### 验收标准

- [ ] 能抽取函证核心字段。
- [ ] 能比对账面金额、回函金额和差异金额。
- [ ] 差异样例进入 Review Center。
- [ ] 可导出函证差异清单。

### 交付物

- [ ] 函证 Schema。
- [ ] 函证规则。
- [ ] 函证差异报告。
- [ ] 函证样例数据。

### 风险点

- [ ] 回函格式差异大。
- [ ] 公章和签字识别不稳定。
- [ ] 差异调节表关联困难。

### 不允许额外扩展的边界说明

- [ ] 不做公章真伪鉴定。
- [ ] 不做外部函证平台集成。
- [ ] 不做自动替代人工函证判断。

## Phase 17: 访谈模块扩展

- Phase 名称：访谈模块扩展
- 是否属于 MVP：否
- Status: TODO

### 阶段目标

支持访谈记录字段抽取、关键回答摘要、签字检查，以及与底稿金额、主体、日期的交叉验证。

### 后端任务

- [ ] 定义 interview_record doc_type。
- [ ] 定义访谈字段 Schema。
- [ ] 抽取被访谈人、职务、单位、日期、主题、关键回答。
- [ ] 抽取提及金额和提及交易对手。
- [ ] 实现缺签字、日期异常、底稿差异规则。

### 前端任务

- [ ] Task Center 支持 interview 场景。
- [ ] Workbench 支持访谈长文本查看。
- [ ] 展示关键回答和来源片段。
- [ ] Review Center 支持访谈差异复核。

### 数据库 / Migration 任务

- [ ] 优先复用现有字段和规则结果表。
- [ ] 如长文本摘要需要版本记录，先补充 tracker。

### API 任务

- [ ] 复用 OCR/抽取/audit/review API。
- [ ] 增加访谈场景参数校验。

### 测试任务

- [ ] 访谈字段抽取测试。
- [ ] 关键回答来源证据测试。
- [ ] 缺签字规则测试。
- [ ] 提及金额与底稿差异测试。

### 验收标准

- [ ] 能抽取访谈核心字段。
- [ ] 能识别提及金额、主体、关键回答。
- [ ] 缺签字、日期异常和底稿差异进入 Review Center。

### 交付物

- [ ] 访谈 Schema。
- [ ] 访谈规则。
- [ ] 访谈样例数据。
- [ ] 访谈复核视图。

### 风险点

- [ ] 长文本摘要遗漏关键事实。
- [ ] 口语化内容结构化困难。
- [ ] 与底稿差异需要人工解释。

### 不允许额外扩展的边界说明

- [ ] 不做语音识别系统。
- [ ] 不做自动事实裁决。
- [ ] 不生成无证据访谈结论。

## Phase 18: 合同审核模块扩展

- Phase 名称：合同审核模块扩展
- 是否属于 MVP：否
- Status: TODO

### 阶段目标

支持重大合同基础字段、关键条款、特殊条款和缺失条款抽取，并输出风险提示和证据索引。

### 后端任务

- [ ] 定义 contract_review 场景。
- [ ] 定义合同字段和条款 Schema。
- [ ] 抽取主体、金额、期限、付款、交付、验收、违约、争议解决。
- [ ] 识别自动续期、排他、回购、价格调整等特殊条款。
- [ ] 实现关键条款缺失规则。

### 前端任务

- [ ] Task Center 支持 contract_review 场景。
- [ ] Workbench 支持条款结构化展示。
- [ ] 展示条款来源片段。
- [ ] Review Center 支持条款风险复核。
- [ ] Report Center 支持合同审核报告。

### 数据库 / Migration 任务

- [ ] 优先复用 `extracted_fields` 和 JSONB line_items/clauses。
- [ ] 如需独立 clause 表，先补充 tracker 后再开发。

### API 任务

- [ ] 复用文档处理和抽取 API。
- [ ] 复用规则和复核 API。
- [ ] 复用报告 API。

### 测试任务

- [ ] 合同基础字段抽取测试。
- [ ] 付款条款缺失测试。
- [ ] 特殊条款识别测试。
- [ ] 条款 evidence 测试。

### 验收标准

- [ ] 能抽取合同基础字段和关键条款。
- [ ] 能识别缺失条款和特殊条款。
- [ ] 条款风险能进入 Review Center。
- [ ] 报告包含条款证据。

### 交付物

- [ ] 合同审核 Schema。
- [ ] 合同规则。
- [ ] 合同审核报告。
- [ ] 合同样例数据。

### 风险点

- [ ] 合同文本长且结构不统一。
- [ ] 特殊条款解释需要专业复核。
- [ ] 补充协议可能改变主合同条款。

### 不允许额外扩展的边界说明

- [ ] 不提供法律意见。
- [ ] 不做合同自动审批。
- [ ] 不替代律师或审计人员判断。

## Phase 19: RBAC、审计、安全、工程化完善

- Phase 名称：RBAC、审计、安全、工程化完善
- 是否属于 MVP：否
- Status: TODO

### 阶段目标

完善用户角色权限、审计日志、安全控制、异步任务和工程化稳定性。

### 后端任务

- [ ] 实现用户登录基础能力。
- [ ] 实现角色和权限点。
- [ ] 将关键操作接入权限校验。
- [ ] 完善 audit_logs。
- [ ] 增强上传文件安全校验。
- [ ] 评估是否引入 Celery / Redis。
- [ ] 增强错误处理和日志脱敏。

### 前端任务

- [ ] 实现登录页。
- [ ] 实现 Admin Center。
- [ ] 根据权限隐藏或禁用操作。
- [ ] 展示审计日志查询页面。

### 数据库 / Migration 任务

- [ ] 创建 `users` 表。
- [ ] 创建 `roles` 表。
- [ ] 创建 `user_roles` 表。
- [ ] 回填 owner/reviewer 外键。
- [ ] 检查敏感字段脱敏策略。

### API 任务

- [ ] Auth API。
- [ ] User API。
- [ ] Role API。
- [ ] Audit Log API。
- [ ] 权限校验中间件或依赖。

### 测试任务

- [ ] 登录测试。
- [ ] 权限拒绝测试。
- [ ] 只读用户不可触发处理测试。
- [ ] 敏感日志不输出完整原文测试。
- [ ] 上传安全校验测试。

### 验收标准

- [ ] 角色权限能限制关键操作。
- [ ] 字段修正、规则修改、报告导出有审计日志。
- [ ] API Key 和 `.env` 不提交。
- [ ] 上传、OCR 中间文件、报告不进入 Git。
- [ ] 日志不输出完整敏感底稿。

### 交付物

- [ ] RBAC。
- [ ] Admin Center。
- [ ] 安全检查文档。
- [ ] 审计日志查询。
- [ ] 工程化增强。

### 风险点

- [ ] 权限模型过度设计。
- [ ] 异步任务引入运维复杂度。
- [ ] 日志泄露敏感数据。

### 不允许额外扩展的边界说明

- [ ] 不做企业 SSO，除非有明确需求。
- [ ] 不做多租户计费系统。
- [ ] 不做生产级 KMS 集成。

## Phase 20: 最终验收、文档整理、作品集展示材料

- Phase 名称：最终验收、文档整理、作品集展示材料
- 是否属于 MVP：否
- Status: TODO

### 阶段目标

完成完整项目验收、文档整理、演示脚本、截图和作品集展示材料，确保项目边界真实、可复现、可解释。

### 后端任务

- [ ] 清理未使用 API。
- [ ] 确认所有服务错误处理一致。
- [ ] 确认 migrations 可从空库执行。
- [ ] 确认所有 seed 和 demo 脚本可运行。

### 前端任务

- [ ] 整理演示路径。
- [ ] 截取关键页面截图。
- [ ] 修复明显 UI 溢出和空状态问题。
- [ ] 确认移动端基础可读性。

### 数据库 / Migration 任务

- [ ] 输出数据库结构文档。
- [ ] 确认 demo 数据不含敏感信息。
- [ ] 确认 local_storage 不进入 Git。

### API 任务

- [ ] 输出 API reference。
- [ ] 确认 API 文档与实际接口一致。
- [ ] 确认错误响应格式一致。

### 测试任务

- [ ] 完整 pytest 通过。
- [ ] MVP E2E demo 通过。
- [ ] Post-MVP smoke tests 通过。
- [ ] 安全隐私 checklist 通过。
- [ ] 最终验收 checklist 通过。

### 验收标准

- [ ] README 可指导新环境启动。
- [ ] docs 覆盖架构、API、数据库、Rule Engine、RAG、Agent、Review、Evaluation、安全。
- [ ] 演示材料不夸大商业落地或真实客户使用。
- [ ] 作品集材料清楚说明使用模拟或公开数据。
- [ ] Final Project Acceptance Checklist 全部完成。

### 交付物

- [ ] 最终 README。
- [ ] docs 文档集。
- [ ] 演示脚本。
- [ ] 截图。
- [ ] 验收报告。
- [ ] 作品集展示材料。

### 风险点

- [ ] 文档与实际实现不一致。
- [ ] 展示材料过度宣称。
- [ ] 演示依赖本地隐藏配置。

### 不允许额外扩展的边界说明

- [ ] 不临时加入新功能。
- [ ] 不补做未经 tracker 记录的模块。
- [ ] 不使用真实敏感客户数据。

## MVP Completion Checklist

- [x] Phase 0 项目初始化与工程骨架完成。
- [x] Phase 1 任务中心与文件上传完成。
- [x] Phase 2 OCR / 文档解析 / 页级文本保存完成。
- [x] Phase 3 文档分类完成。
- [x] Phase 4 字段抽取与 Schema 校验完成。
- [x] Phase 5 采购业务归集完成。
- [x] Phase 6 Rule Engine MVP 完成。
- [x] Phase 7 Audit Workbench 前端工作台完成。
- [x] Phase 8 Review Center 基础复核闭环完成。
- [x] Phase 9 Report Center 控制表与异常清单导出完成。
- [x] Phase 10 MVP 测试、演示数据、README 和 Docker 交付完成。
- [x] 可创建采购穿行任务。
- [x] 可上传六类采购文件。
- [x] 可完成 OCR / 文本解析。
- [x] 可完成文档分类。
- [x] 可完成字段抽取。
- [x] 可完成业务归集。
- [x] 可执行六条采购 Rule Engine MVP 规则。
- [x] 异常可进入 Review Center。
- [x] 字段修正后可重跑规则。
- [x] 可导出 xlsx 控制表、异常清单、证据索引。
- [x] 基础 pytest 通过。
- [x] Docker Compose 可启动。

## Post-MVP Expansion Checklist

- [x] Phase 10 已标记 DONE。
- [x] Phase 11 RAG 四库扩展完成。
- [ ] Phase 12 Rule Center 规则版本化与参数配置完成。
- [ ] Phase 13 Agent Workflow 状态机与工具调用完成。
- [ ] Phase 14 Bad Case Center 与 Evaluation Center 完成。
- [ ] Phase 15 销售穿行扩展完成。
- [ ] Phase 16 函证模块扩展完成。
- [ ] Phase 17 访谈模块扩展完成。
- [ ] Phase 18 合同审核模块扩展完成。
- [ ] Phase 19 RBAC、审计、安全、工程化完善完成。
- [x] RAG 输出包含 citation 和 no-answer handling。
- [ ] Agent 不绕过 Rule Engine。
- [ ] Evaluation Center 可运行回归评测。
- [ ] 扩展场景不破坏采购穿行 MVP。

## Final Project Acceptance Checklist

- [ ] 所有 Phase 0-20 均为 DONE 或有明确 DEFERRED 说明。
- [ ] 后端 API 可启动且文档一致。
- [ ] 前端核心页面可运行。
- [ ] 数据库 migrations 可从空库执行。
- [ ] Rule Engine 规则可测试、可复现、可追溯。
- [ ] Review Center 保留 before / after 和 audit logs。
- [ ] Report Center 导出内容完整。
- [ ] RAG 四库隔离并有 citation。
- [ ] Agent Workflow 有状态机、工具白名单、失败重试。
- [ ] Bad Case 和 Evaluation 可形成回归闭环。
- [ ] 销售、函证、访谈、合同审核至少有基础端到端样例。
- [ ] 安全隐私检查通过。
- [ ] README 和 docs 可指导新开发者理解和启动项目。
- [ ] 作品集材料使用公开或模拟数据。
- [ ] 项目没有实现 tracker 外的临时功能。
