# FinancialAuditAI 公开验收完成版说明书

## 当前版本声明

- 当前版本名称：`FinancialAuditAI v1.0-public-acceptance`。
- 当前定位：`Non-Production Public Acceptance Complete Release`。
- 本版本表示项目的 code / test / docs / CI 主链路已经完成，公开或合成验收材料已经覆盖 OCR、Classification、Extraction、RAG、Provider readiness 和 Security reference。
- 本版本不声明 `production fully_satisfied`。
- 本版本不声明真实客户项目落地。
- 本版本不声明 hosted production deployment。
- 本版本不声明 enterprise security governance complete。
- 本版本不包含真实或脱敏客户数据、真实生产标签、客户项目复核材料、生产级 SLA 证明或企业级安全治理证明。

当前内部验证记录：

| 验证项 | 当前状态 |
| --- | --- |
| Backend pytest | `230 passed, 5 warnings` |
| Frontend `npm test` | `4 passed` |
| Frontend `npm run build` | passed |
| GitHub Actions CI | PASS |
| `local_storage` / `.env` Git tracking | not tracked |
| 原执行手册 Git tracking | removed from tracking, kept locally, ignored by `.gitignore` |

## 项目定位

FinancialAuditAI 是一个面向金融文档审核、采购付款穿行、证据链追踪、人工复核和报告导出的智能审核平台。系统使用 OCR、文档分类、字段抽取、Rule Engine、RAG、Agent Workflow、Review Center、Report Center 和 Evaluation Center，把文档处理、规则判断、证据引用、复核留痕和质量回归串成可审计链路。

本公开验收完成版的重点是：证明项目主链路、工程结构、公开/合成验收机制和安全边界已经形成闭环。它不是生产交付声明，也不是客户项目验收声明。

## 项目边界

本项目覆盖：

- 创建和管理金融文档审核任务。
- 上传 PDF、扫描件、图片、DOCX、Excel 导出的 PDF 等底稿文件。
- 执行 OCR，并保留页码、文本块、表格、bbox、confidence 和页图像引用。
- 自动识别文档类型，保存分类理由、confidence 和人工复核信号。
- 按文档类型抽取字段、line_items 和来源证据。
- 对采购申请单、合同、入库单、发票、凭证、付款回单进行业务归集。
- 使用 Rule Engine 校验时间、数量、金额、名称、品种、税率、缺字段和证据不足。
- 使用 RAG 检索公开资料和任务底稿证据，输出 citation、limitations 和 no-answer。
- 将低置信度、缺字段、高风险异常、证据不足和失败状态路由到 Review Center。
- 支持字段修正、异常确认/驳回、复核意见、重跑规则和审计留痕。
- 导出控制表、异常清单、证据索引和审核报告摘要。
- 记录 Bad Case，并通过 Evaluation Center 进行回归评测。

本项目不声明：

- 不替代注册会计师、律师、投行人员或合规人员的专业判断。
- 不输出无法追溯证据来源的结论。
- 不使用真实敏感客户数据作为公开样例。
- 不构成审计、法律、投资或合规认证意见。
- 不宣称生产落地、客户使用、商业收益或 hosted production deployment。

销售穿行、函证、访谈和合同审核在本说明书中作为扩展场景能力描述；当前公开验收完成版不把这些场景写成生产验收完成。

## 核心链路

采购穿行主链路：

```text
audit_task
  -> upload documents
  -> OCR
  -> document classification
  -> field extraction
  -> business linkage
  -> Rule Engine
  -> RAG evidence retrieval
  -> Review Center
  -> Report Center
  -> Bad Case / Evaluation Center
```

证据链路：

```text
document file
  -> document_page
  -> OCR block
  -> extracted_field
  -> audit_result evidence
  -> review_comment
  -> control_table_row
  -> report evidence index
```

质量闭环：

```text
sample set
  -> run OCR / classify / extract / rules / RAG / agent
  -> compare expected output
  -> record failed cases
  -> update prompt / schema / rule / retrieval / workflow
  -> rerun evaluation
```

## 技术架构

系统分层：

| 层级 | 说明 |
| --- | --- |
| Frontend | React / TypeScript / Ant Design，用于任务中心、审核工作台、复核、报表、知识库、规则、评测和 Admin 页面 |
| Backend API | FastAPI / Pydantic / SQLAlchemy，提供任务、文档、OCR、分类、抽取、规则、RAG、复核、报告和评测 API |
| Application Services | Task、Document、OCR、Classification、Extraction、Rule Engine、RAG、Agent、Review、Report、Evaluation |
| AI Layer | OCR Provider、LLM Provider、Embedding Provider、Reranker、Prompt Templates、Output Validators |
| Data Layer | PostgreSQL、pgvector、File Storage、Evaluation Datasets |
| Governance Layer | RBAC、Audit Logs、Model Invocations、Bad Cases、Metrics、Safety Checks |

核心数据流：

```text
1. 用户创建 audit_task
2. 上传 documents
3. OCR 写入 document_pages
4. 文档分类写入 documents.doc_type 和 confidence
5. 字段抽取写入 extracted_fields
6. 业务归集写入 document_relations 和 business_key
7. Rule Engine 写入 audit_results
8. RAG 检索 rag_chunks 并写入 citations
9. Review Center 写入 review_comments 和 audit_logs
10. Report Center 写入 control_table_rows 和 reports
11. Bad Case 与 Evaluation Center 写入 bad_cases 和 evaluation_results
```

## 数据库设计摘要

数据库使用 PostgreSQL，核心设计原则是 UUID 主键、结构化证据留痕、JSONB 承载灵活字段和模型输出、pgvector 支持 RAG、人工修正不覆盖原始证据。

核心表摘要：

| 表 | 作用 |
| --- | --- |
| `users`, `roles`, `user_roles` | 用户、角色和权限 |
| `audit_tasks` | 审核任务主表 |
| `documents` | 上传文档、分类结果和处理状态 |
| `document_pages` | 页级 OCR 文本、blocks、tables、bbox、confidence |
| `extracted_fields` | 字段、标准化值、source_page、source_bbox、source_text |
| `document_relations` | 同一业务链路内的文档归集关系 |
| `audit_rules` | 规则定义、参数、版本和启用状态 |
| `audit_results` | 规则运行结果、证据、RAG 引用和复核状态 |
| `review_comments` | 人工复核意见、字段修正、异常确认/驳回 |
| `control_table_rows`, `reports` | 控制表、异常清单、证据索引和导出记录 |
| `rag_documents`, `rag_chunks` | RAG 文档、切片、metadata 和 embedding |
| `agent_runs`, `agent_steps` | Agent 工作流运行和每步工具调用 |
| `audit_logs` | 关键操作审计日志 |
| `model_invocations` | 模型调用、版本、耗时、Token、错误和成本估算 |
| `bad_cases` | 错误样例、根因、修复计划和回归状态 |
| `evaluation_results` | 评测结果、指标、样本数和 failed_cases |

## 任务中心与文档处理

任务中心负责创建、查看和推进审核任务；文档处理负责上传校验、文件 hash、页渲染、OCR、分类、抽取和处理状态更新。系统保留文档原始文件引用、页级结果、分类结果、抽取结果和后续复核状态，保证每个业务判断能回到具体文档和页码。

## OCR 与文档分类

OCR 输出保留：

- `page_number`
- `raw_text`
- `ocr_blocks`
- `table_blocks`
- `bbox`
- `confidence`
- page image reference

分类输出保留：

- `doc_type`
- `confidence`
- `reason`
- `alternative_types`
- `need_human_review`

公开验收完成版已经有 synthetic external OCR、SROIE public OCR、SRD images-only robustness 和 1_Images / Zenodo images-only robustness 证据。它们证明 OCR 接入、manifest 加载、公开样本处理、bbox/confidence/table 检查和图片渲染路径可运行；不证明真实客户项目 OCR 质量或生产级 Provider SLA。

## 字段抽取

字段抽取模块根据文档类型 Schema 从 OCR 文本和表格中抽取结构化字段、line_items 和来源证据。字段应包含：

- `field_name`
- `value`
- `confidence`
- `source_page`
- `source_bbox`
- `source_text`
- normalization result
- warning / missing-field signal

公开验收完成版已经有 SROIE entities public extraction 和 FATURA public invoice layout/extraction 证据。它们证明公开票据/收据字段映射、normalized matching、address token overlap、numeric total matching、source text 和 bbox-backed evidence 可以被 Evaluation Center 验收；不证明项目特定真实或脱敏底稿抽取质量。

## Rule Engine

Rule Engine 读取标准化字段、line_items、文档归集关系、规则参数和业务配置，输出可解释、可追踪、可复核的审核结果。

规则结果状态包括：

- `pass`
- `warning`
- `fail`
- `not_applicable`
- `need_review`
- `evidence_insufficient`

覆盖的规则类型包括时间顺序、数量一致性、金额一致性、名称一致性、品种一致性、税率、缺字段、多品种、含税/不含税口径和重复/缺失证据。当前公开验收完成版的 Rule Engine 主要由代码、单元测试和合成评测覆盖，不把合成规则样例写成真实生产规则验收。

## RAG

RAG 模块管理四类知识库：

| 知识库 | 用途 |
| --- | --- |
| `regulation` | 法规条款和监管要求检索 |
| `inquiry_case` | 公开问询函、审核问询与回复、公开案例摘要 |
| `prospectus` | 公开招股书或 SEC filing 的业务、风险和披露内容 |
| `workpaper` | 当前任务 OCR 文本、字段结果和复核后结构化证据 |

RAG 输出必须包含 citation 和 limitations；检索不到依据时应返回 no-answer / evidence_insufficient，不生成无来源结论。

公开验收完成版已经有 SEC EDGAR Apple 10-K public RAG acceptance，覆盖公开 filing 入库、chunking、embedding/retrieval 路径、citation metadata、answer/no-answer 和 metadata check。该证据不等于项目特定 workpaper RAG 生产验收。

## Agent Workflow

Agent Workflow 使用状态机和白名单工具调用编排审核流程，记录每个步骤的输入、输出、状态、耗时和错误。Agent 不允许绕过 Rule Engine 直接生成审核结论，不允许把检索不到的依据写成结论，不允许自动确认高风险异常。

主要工具包括：

- `run_ocr(document_id)`
- `classify_document(document_id)`
- `extract_fields(document_id, doc_type)`
- `link_business_documents(task_id)`
- `run_rule_engine(task_id)`
- `retrieve_evidence(query, kb)`
- `create_review_ticket(result_id)`
- `generate_control_table(task_id)`
- `record_bad_case(payload)`

当前公开验收完成版覆盖 Agent 记录、状态约束、工具白名单、错误处理和人工复核路由的工程路径；不声明真实业务 Agent workflow 生产验收。

## Review Center

Review Center 处理低置信度、缺字段、规则失败、高风险 warning、RAG 证据不足、Agent 失败和人工标记事项。复核动作包括字段修正、异常确认、驳回异常、要求重新抽取、重跑规则、添加复核意见和转 Bad Case。

复核要求：

- 字段修正保留 before / after。
- 异常驳回必须记录原因。
- 高风险异常不能自动通过。
- 字段修正后支持重跑相关规则。
- 复核意见进入报告。
- 关键复核动作写入 audit logs。

## Report Center 与 Evidence Index

Report Center 把字段、规则结果、RAG 引用、人工复核意见和证据索引整理为控制表、异常清单、审核摘要和可下载文件。

支持输出：

- Excel 控制表。
- CSV 数据表。
- Markdown / PDF 摘要。
- 异常清单。
- Evidence Index。
- 报告导出记录。

报告边界：报告应标注数据来源、证据限制和用途边界，不把公开/合成样例写成真实生产审计结论。

## Bad Case

Bad Case 体系记录 OCR、分类、抽取、规则、RAG、Agent 和复核流程中的错误，并把错误转化为可复查、可归因、可修复、可回归的工程资产。

处理流程：

```text
发现错误
  -> 记录 bad_cases
  -> 标注 expected_output
  -> 分析 root_cause
  -> 修改 OCR / prompt / schema / rule / retrieval / workflow
  -> 加入 evaluation dataset
  -> 运行回归评测
  -> verified 后关闭
```

## Evaluation Center

Evaluation Center 管理测试集、执行评测、记录指标、展示 failed_cases，并支持 Bad Case 回归。公开验收完成版明确区分：

- `synthetic_external_acceptance`
- `public_dataset`
- `public_reference`
- `manual_acceptance`
- `production_evaluation=false`

合成、公开、fixture、mock、fallback、deterministic 或 images-only robustness 结果均不能写成 production fully_satisfied。

评测范围包括：

| 类型 | 主要指标 |
| --- | --- |
| Classification | Accuracy、Macro F1、Low-confidence Rate |
| OCR | CER / WER、Table Structure Accuracy、Numeric Accuracy、BBox Quality |
| Extraction | Field Precision / Recall / F1、Exact Match、Source Accuracy |
| Rule Engine | Rule Accuracy、False Positive / Negative、Rule Coverage、Explainability |
| RAG | Recall@K、Citation Accuracy、Groundedness、No-answer Accuracy |
| Agent Workflow | Workflow Success、Step Failure、Review Routing、State Transition |
| E2E | Control Table Accuracy、Exception Detection、Evidence Completeness |
| Regression | Regression Pass Rate、Reopened Cases、Fix Impact |

## 安全与隐私边界

本版本包含基础安全和仓库安全边界：

- 基础 authentication 和 RBAC。
- 上传文件类型和内容校验。
- API key、token、`.env` 和 Provider artifact 不进入仓库。
- `danger_check.py` 检查 tracked/staged secret、runtime artifact 和危险路径。
- `production_safety_check.py` 检查生产安全配置风险。
- `local_storage` 用于本地外部验收材料归档，并保持 Git ignored / untracked。
- Provider readiness artifact 只保留本地安全摘要，不提交原始 artifact body。

这些措施是 repository guardrails 和 non-production public acceptance 边界，不等于企业级 DLP、KMS、SSO、集中监控、备份、事件响应或生产审计日志治理已经完成。

## 扩展场景能力

销售穿行、函证、访谈和合同审核作为扩展场景能力存在于产品设计和规则/评测结构中。当前公开验收完成版可以描述这些扩展方向和部分工程支持，但不把它们写成真实生产验收完成，也不把合成规则样例写成真实业务验证。

## 公开验收完成标准

### Internal Validation

| 项目 | 状态 |
| --- | --- |
| Backend tests | `230 passed, 5 warnings` |
| Frontend tests | `4 passed` |
| Frontend build | passed |
| GitHub Actions CI | PASS |
| JSON status document validation | passed in latest documented verification |
| Docker Compose config validation | passed in latest documented verification |
| Git safety | `local_storage` / `.env` not tracked; original execution manual not tracked and ignored |

### Public / Synthetic Evidence

当前公开/合成验收材料覆盖：

- OCR synthetic external acceptance。
- SROIE OCR public acceptance。
- Classification synthetic external acceptance。
- SROIE extraction public acceptance。
- FATURA extraction/layout public acceptance。
- SEC EDGAR Apple 10-K public RAG acceptance。
- SRD images-only OCR robustness。
- 1_Images / Zenodo images-only OCR robustness。
- Provider readiness artifact。
- OWASP ASVS security reference mapping。

### Release Boundaries

本版本明确不包含：

- production fully_satisfied。
- 真实或脱敏客户项目数据集。
- 真实生产 labels。
- hosted deployment evidence。
- enterprise DLP / KMS / SSO / monitoring / backups / incident response evidence。
- real provider SLA attestation。
- 真实客户项目落地、真实审计意见或正式合规认证。

## Evidence Ledger

| evidence name | source_type | sample_count | failed_cases | metrics summary | proves | does not prove |
| --- | --- | --- | --- | --- | --- | --- |
| OCR synthetic external acceptance | synthetic_external_acceptance | 3 | `[]` | `ocr_sample_pass_rate=1.0`; text/page/block/bbox/confidence/table accuracies `1.0`; `is_production_evaluation=false` | Real OCR Provider integration path, external manifest loading, multi-page/table/scanned-like sample checks, sanitized summary handling | Real/desensitized customer OCR quality, production OCR SLA, production fully_satisfied |
| SROIE OCR public acceptance | public_dataset | 5 | `[]` | OCR pass, text/page/block/bbox/confidence/table/key-information/box-line/normalized/fuzzy-address metrics `1.0`; `is_production_evaluation=false` | Public receipt OCR acceptance with normalized field-aware matching and Azure OCR path summary | Project-specific production OCR, customer data performance, production deployment |
| Classification synthetic external acceptance | synthetic_external_acceptance | 6 | `[]` | `accuracy=1.0`; `macro_f1=1.0`; `low_confidence_rate=0.0`; `confidence_threshold_accuracy=1.0`; `human_review_flag_accuracy=1.0`; `is_production_evaluation=false` | Classification manifest plumbing and deterministic/local classification behavior across six procurement document types | Real LLM classification quality, uploaded-document DB workflow production quality, real labels |
| SROIE extraction public acceptance | public_dataset | 5 | `[]` | Public extraction sample/field/company/date/address/total/evidence metrics `1.0`; `is_production_evaluation=false`; `production_evaluation=false` | Public receipt/invoice entity extraction mapping, source text evidence, normalized matching | Project-specific extraction labels, production invoice/receipt extraction quality |
| FATURA extraction/layout public acceptance | public_dataset | 5 | `[]` | Public extraction sample/field/company/date/address/total/evidence metrics `1.0`; `source_bbox_coverage=1.0`; `is_production_evaluation=false` | Public invoice annotation/layout loading, bbox-backed evidence, invoice field extraction plumbing | Real customer invoice extraction, production layout robustness, Provider SLA |
| SEC EDGAR Apple 10-K public RAG acceptance | public_dataset | 4 | `[]` | RAG external pass/citation/answer/no-answer/metadata metrics `1.0`; `external_rag_document_count=1`; `external_rag_chunk_count=7868`; `is_production_evaluation=false` | Public filing ingestion, chunking, retrieval, citation metadata and no-answer behavior | Project-specific workpaper RAG, real citation labels, production grounded-answer quality |
| SRD images-only OCR robustness | public_dataset | 5 | `[]` | `ocr_sample_pass_rate=1.0`; `page_count_accuracy=1.0`; `is_production_evaluation=false` | Public image ingestion/rendering robustness through local OCR path | OCR text accuracy, bbox/table/confidence quality, extraction quality, production evidence |
| 1_Images / Zenodo images-only OCR robustness | public_dataset | 5 | `[]` | `ocr_sample_pass_rate=1.0`; `page_count_accuracy=1.0`; `is_production_evaluation=false` | Additional public image ingestion/rendering robustness through local OCR path | OCR quality, extraction quality, Provider quality, production evidence |
| Provider readiness artifact | local_external_acceptance | 1 sanitized artifact summary | `forbidden_hits=[]` | JSON valid; top-level readiness artifact keys present; no API key/token/`.env` content recorded; ordinary pytest isolated from real Providers | Provider configuration/readiness mechanism and artifact redaction discipline | Publicly disclosable provider SLA, production integration attestation, production fully_satisfied |
| OWASP ASVS security reference mapping | public_reference | 1 reference mapping | N/A | ASVS reference archived locally; boundary documented as checklist only | Security review reference baseline and future control mapping vocabulary | Enterprise DLP/KMS/SSO/monitoring/backups/IR evidence, hosted security governance completion |

## Current Final Positioning

FinancialAuditAI v1.0-public-acceptance 的最终定位是：

```text
code/test/docs complete
+ CI green
+ expanded public/synthetic acceptance documented
+ non-production public acceptance complete
```

它不是：

```text
production fully_satisfied
hosted production deployment complete
real customer project acceptance complete
enterprise security governance complete
real provider SLA attested
```

公开读者可以把本版本理解为一个工程主链路完整、测试和 CI 通过、公开/合成验收材料充分归档的 non-production release。若未来进入生产验收，应另行提供真实或合规脱敏数据、真实标签、生产部署、安全治理和 Provider 证明材料；这些材料不属于当前公开验收完成版的行动目标。
