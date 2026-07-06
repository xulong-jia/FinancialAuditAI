# FinancialAuditAI 金融文档智能审核平台｜最终版项目开发执行手册

> 项目定位：FinancialAuditAI 是基于 **OCR + LLM + RAG + Rule Engine + Human Review + Agent Workflow + FastAPI + React + PostgreSQL** 的金融文档智能审核平台。
> 本手册面向正式项目开发过程，描述产品边界、角色权限、工程结构、数据库、核心业务流、采购穿行 MVP、扩展审核模块、规则引擎、RAG、Agent、人工复核、报告导出、Bad Case、评测体系和最终交付验收标准。

---

## 0. 项目总判断

FinancialAuditAI 应被定义为一个“金融文档智能审核平台”，而不是 OCR 识别 Demo、普通 RAG 问答系统或让大模型直接给出审核结论的工具。系统的核心价值在于把金融底稿审核中的文档输入、证据定位、字段抽取、跨文件关联、规则校验、依据检索、人工复核、审计留痕、报告导出和评测回归串成一条可追踪、可复核、可配置、可评测的工程链路。

项目应围绕六类能力展开：

| 能力层级 | 系统目标 | 工程重点 |
| --- | --- | --- |
| 文档层 | 将 PDF、扫描件、图片、表格底稿转换为可定位证据 | OCR、页码、bbox、置信度、原文片段 |
| 结构化层 | 对底稿进行分类、字段抽取和标准化 | doc_type、Schema、line_items、source evidence |
| 规则层 | 对时间、数量、金额、名称、品种、税率等进行确定性校验 | Rule Engine、规则版本、参数配置、证据输出 |
| 知识层 | 检索法规、问询案例、招股书和底稿依据 | RAG 四库、metadata、citation、grounded answer |
| 工作流层 | 编排 OCR、分类、抽取、规则、检索、复核和报告 | 状态机、工具调用、人工复核路由、运行日志 |
| 质量层 | 沉淀错误样本并持续回归 | Bad Case、Evaluation Center、指标、测试集 |

系统设计包含以下判断：

- OCR 负责把文档转化为带页码、坐标和置信度的证据，不负责业务判断。
- LLM 负责文档理解、分类、字段抽取和异常解释，不负责绕过规则直接输出审核结论。
- Rule Engine 是确定性审核核心，承担时间、数量、金额、名称、品种、缺字段、多品种和含税口径判断。
- RAG 是依据检索服务，提供法规、案例、招股书和底稿引用，不替代规则和人工判断。
- Human Review 是最终确认层，负责字段修正、异常确认、驳回异常、复核意见和审计留痕。
- Agent Workflow 是状态机 + 工具调用 + 规则约束 + 人工复核路由，不是自由聊天机器人。
- Report Center 负责导出控制表、异常清单、证据索引和审核摘要，不隐藏规则失败项。
- Evaluation Center 是独立质量模块，覆盖分类、OCR、字段抽取、规则、RAG、Agent 和端到端采购穿行评测。

项目开发应坚持四个原则：

1. 证据优先：字段、异常、复核意见和报告结论必须能回到原文件、页码、坐标和原文片段。
2. 确定性优先：能由规则判断的事项优先交给 Rule Engine，不让 LLM 自由裁决。
3. 人机协同：系统提供初步审核、异常解释和证据索引，人工复核保留最终判断。
4. 评测闭环：每次 OCR、分类、抽取、规则、RAG 或 Agent 错误都应进入 Bad Case 和回归评测。

---

## 1. 项目总定位

### 1.1 项目名称

**FinancialAuditAI 金融文档智能审核平台**

### 1.2 一句话定位

FinancialAuditAI 是面向 IPO 底稿、券商投行底稿复核、银行科技金融合规审核和金融文档证据抽取场景的智能审核平台，基于 OCR、LLM、RAG、Rule Engine、Human Review、Agent Workflow、FastAPI、React 和 PostgreSQL，实现采购穿行、销售穿行、函证、访谈、合同审核、证据定位、人工复核、控制表导出、Bad Case 与评测闭环。

### 1.3 项目边界

本项目要做：

- 创建和管理金融文档审核任务。
- 上传 PDF、扫描件、图片、DOCX、Excel 导出的 PDF 等底稿文件。
- 执行 OCR，保存页码、文本块、表格、bbox 和置信度。
- 自动识别文档类型并保留分类理由和置信度。
- 按文档类型 Schema 抽取字段、明细行和来源证据。
- 对同一笔业务的申请单、合同、入库单、发票、凭证、付款回单进行归集。
- 使用 Rule Engine 校验时间、数量、金额、名称、品种、税率、缺字段、多品种和含税/不含税口径。
- 使用 RAG 检索法规、公开案例、招股书和当前底稿证据，为异常解释提供引用。
- 将低置信度、缺字段、高风险异常和失败状态路由到 Review Center。
- 支持字段修正、异常确认、驳回异常、复核意见、重新运行规则和审计日志。
- 导出采购穿行控制表、异常清单、证据索引和审核报告摘要。
- 记录 Bad Case 并通过 Evaluation Center 进行回归评测。

本项目不做：

- 不做只有 OCR 识别结果展示的 Demo。
- 不做只有“上传文件问问题”的普通 RAG 系统。
- 不替代注册会计师、律师、投行人员或合规人员的专业判断。
- 不输出无法追溯证据来源的结论。
- 不宣称生产落地、客户使用、机构项目或商业收益。
- 不使用真实敏感客户数据作为公开样例。
- 不构成审计、法律或投资建议。

### 1.4 系统核心链路

采购穿行链路：

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
```

质量闭环：

```text
sample set
  -> run OCR / classify / extract / rules / RAG / agent
  -> compare expected output
  -> record bad case
  -> fix prompt / schema / rule / retrieval / workflow
  -> rerun evaluation
```

---

## 2. 真实业务背景

IPO、投行业务、银行授信、科技金融合规和金融机构内部审查中会产生大量底稿材料。常见材料包括采购申请单、采购合同、入库单、发票、记账凭证、付款回单、销售合同、销售订单、出库单、物流单、收款凭证、函证、回函、访谈记录、重大合同、补充协议、招股书、反馈问询函、监管规则和法律法规。

传统审核中的主要痛点：

- 文件数量多，格式不统一，扫描质量和表格结构差异较大。
- 同一笔业务的事实分散在合同、发票、凭证、回单和银行流水等多个文件中。
- 审核人员需要不断比对日期、金额、数量、供应商、客户、品种、税率和凭证摘要。
- 审核结论必须保留证据、依据、复核意见和过程留痕。
- 规则既包含确定性判断，也包含需要人工经验判断的例外场景。
- 人工翻阅底稿成本高，异常归因和报告导出容易重复劳动。

AI 系统可以解决的部分：

- 自动识别文档类型和关键字段。
- 自动建立同一笔业务的跨文件关联。
- 自动发现时间倒挂、金额超付、数量不一致、主体不一致、品种不一致、税率异常和缺字段问题。
- 自动检索法规、公开问询案例、招股书披露和当前任务底稿证据。
- 自动生成控制表、异常清单和证据索引。
- 将高风险、低置信度和规则失败事项集中交给人工复核。

系统不能替代的部分：

- 专业判断。
- 最终审核意见。
- 对真实项目事实的外部核验。
- 对法律、审计或投资结论的责任承担。

---

## 3. 目标用户与角色权限

### 3.1 用户角色

| 角色 | 典型职责 | 核心诉求 |
| --- | --- | --- |
| 分析师 | 创建任务、上传底稿、启动处理、查看初步结果 | 提高底稿整理、字段抽取和异常识别效率 |
| 复核人 | 复核 AI 结果、修正字段、确认异常、写复核意见 | 快速定位证据并保留复核痕迹 |
| 项目经理 | 查看任务进度、异常分布、人员处理情况和导出结果 | 管理审核质量、进度和交付物 |
| 管理员 | 管理用户、角色、规则库、知识库和模型配置 | 控制权限、配置、规则版本和系统状态 |
| 只读观察者 | 查看脱敏样例、报告和指标 | 只读查看结果，不修改数据 |

### 3.2 权限矩阵

| 功能 | 分析师 | 复核人 | 项目经理 | 管理员 | 只读观察者 |
| --- | --- | --- | --- | --- | --- |
| 创建审核任务 | 是 | 是 | 是 | 是 | 否 |
| 上传文档 | 是/本人任务 | 是/负责任务 | 是/项目范围 | 是 | 否 |
| 删除文档 | 本人草稿 | 否 | 项目范围 | 是 | 否 |
| 运行 OCR/分类/抽取 | 是 | 是 | 是 | 是 | 否 |
| 运行规则审核 | 是 | 是 | 是 | 是 | 否 |
| 修改抽取字段 | 草稿阶段 | 是 | 是 | 是 | 否 |
| 确认或驳回异常 | 否 | 是 | 是 | 是 | 否 |
| 管理规则库 | 否 | 建议修改 | 审批修改 | 是 | 否 |
| 管理 RAG 知识库 | 否 | 否 | 审批上传 | 是 | 否 |
| 导出控制表/报告 | 是 | 是 | 是 | 是 | 只读导出 |
| 查看 Bad Case 与评测 | 是 | 是 | 是 | 是 | 只读 |
| 管理用户和角色 | 否 | 否 | 否 | 是 | 否 |

### 3.3 权限设计原则

- 字段修正、异常确认、规则修改、报告导出和知识库更新必须写入 audit_logs。
- 只读角色不得触发 OCR、抽取、规则、复核或报告生成。
- 规则库、知识库和模型配置变更应记录版本。
- 复核动作不能覆盖原始 OCR、原始字段和原始规则结果，只能通过修正记录和复核状态体现。

---

## 4. 产品模块设计

### 4.1 模块总览

| 模块 | 核心职责 | 主要输出 |
| --- | --- | --- |
| 任务中心 | 创建任务、管理场景、上传文件、跟踪状态 | audit_task、task status、document list |
| 文档处理中心 | OCR、页级文本、bbox、表格块和文档分类 | document_pages、doc_type、classification_reason |
| 字段抽取中心 | 按 Schema 抽取字段、明细行、置信度和来源 | extracted_fields、line_items、source evidence |
| 采购穿行模块 | 打通申请、合同、入库、发票、凭证、付款链路 | procurement control table、audit_results |
| 销售穿行模块 | 扩展销售合同、订单、出库、物流、开票、收款链路 | sales control table、异常清单 |
| 函证模块 | 处理发函、回函、账面金额和差异调节 | confirmation result、差异记录 |
| 访谈模块 | 抽取访谈对象、主题、关键回答并与底稿交叉验证 | interview evidence、风险提示 |
| 合同审核模块 | 抽取合同条款并识别关键缺失和异常条款 | contract review result |
| Rule Engine | 执行确定性规则、规则版本和参数配置 | audit_results、规则证据 |
| RAG 知识库 | 管理法规、案例、招股书和底稿四库 | citations、grounded answer |
| Agent Workflow | 受控编排任务状态和工具调用 | agent_runs、agent_steps |
| Review Center | 人工复核、字段修正、异常确认和审计留痕 | review_comments、review_status |
| Report Center | 控制表、异常清单、证据索引和报告导出 | reports、control_table_rows |
| Bad Case | 记录错误样例、根因和修复策略 | bad_cases、regression set |
| Evaluation Center | 管理测试集、指标和回归评测 | evaluation_results、metrics |

### 4.2 产品页面

| 页面 | 功能 |
| --- | --- |
| Dashboard | 任务总数、待复核数、异常分布、通过率、最近评测摘要 |
| Task Center | 新建任务、上传文档、查看任务状态、启动处理流程 |
| Audit Workbench | 文档查看器、证据高亮、字段表、规则结果和 Agent 状态 |
| Review Center | 复核队列、字段修正、异常确认、驳回异常和复核意见 |
| Rule Center | 规则列表、版本、启用状态、参数、别名表和品种映射 |
| Knowledge Center | 法规库、案例问询库、招股书库、底稿库和检索测试 |
| Report Center | 控制表预览、异常清单、证据索引和导出历史 |
| Bad Case Center | 错误样例、根因、修复策略和回归状态 |
| Evaluation Center | 分类、OCR、抽取、规则、RAG、Agent 和端到端评测结果 |
| Admin Center | 用户、角色、权限、模型配置和审计日志 |

### 4.3 MVP 第一阶段

第一阶段聚焦采购穿行 MVP，目标是打通端到端闭环：

```text
创建采购穿行审核任务
  -> 上传六类采购文件
  -> OCR 识别
  -> 文档分类
  -> 字段抽取
  -> 同一笔业务归集
  -> Rule Engine 校验
  -> RAG 依据检索
  -> 人工复核
  -> 控制表导出
  -> Bad Case 与评测
```

MVP 必须做到：

- 覆盖采购申请单、采购合同、入库单、发票、记账凭证、付款回单六类文件。
- 每类文件有明确字段 Schema 和必填字段。
- 每条规则有输入字段、计算逻辑、输出状态、严重程度和证据来源。
- 每个异常可以回到原文件、页码、bbox 和原文片段。
- 每次人工修正、异常确认和驳回都有审计留痕。

---

## 5. 技术架构

### 5.1 系统分层

```text
Frontend
React / TypeScript / Ant Design
        |
Backend API
FastAPI / Pydantic / SQLAlchemy
        |
Application Services
Task / Document / OCR / Classification / Extraction
Rule Engine / RAG / Agent / Review / Report / Evaluation
        |
AI Layer
OCR Provider / LLM Provider / Embedding Provider / Reranker
Prompt Templates / Output Validators
        |
Data Layer
PostgreSQL / pgvector / File Storage / Evaluation Datasets
        |
Governance Layer
RBAC / Audit Logs / Model Invocations / Bad Cases / Metrics
```

### 5.2 推荐技术栈

| 层级 | 推荐技术 | 说明 |
| --- | --- | --- |
| 前端 | React, TypeScript, Ant Design | 审核工作台、复核中心、规则中心和报表中心 |
| 后端 | FastAPI, Pydantic, SQLAlchemy | API、Schema 校验、业务服务和数据访问 |
| 数据库 | PostgreSQL | 任务、文档、字段、规则、结果、复核、报告和评测 |
| 向量检索 | pgvector | RAG 四库向量检索 |
| OCR | PaddleOCR / 可替换 OCR Provider | 扫描件识别和表格解析 |
| LLM | OpenAI / DeepSeek / Qwen 可替换 | 分类、抽取、解释和摘要 |
| 文档解析 | PyMuPDF, pdfplumber, python-docx, openpyxl | PDF、DOCX、Excel 和图片处理 |
| 异步任务 | Celery / RQ / FastAPI BackgroundTasks | OCR、抽取、评测和报告生成 |
| 文件存储 | local storage / S3 compatible | 原文件、页图片、OCR JSON、导出报告 |
| 测试 | pytest | 规则、API、服务和评测脚本 |
| 部署 | Docker Compose | 后端、前端、PostgreSQL、pgvector 本地复现 |

### 5.3 核心数据流

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

### 5.4 模块间契约

| 上游 | 下游 | 契约 |
| --- | --- | --- |
| OCR Service | Classification Service | document_id、page raw_text、ocr_blocks |
| Classification Service | Extraction Service | doc_type、confidence、classification_reason |
| Extraction Service | Rule Engine | extracted_fields、line_items、source evidence |
| Document Linkage | Rule Engine | business_key、document_relations |
| Rule Engine | RAG Service | exception query、rule result、evidence summary |
| Rule Engine | Review Center | audit_result、severity、need_review reason |
| Review Center | Rule Engine | corrected fields、rerun request |
| Report Center | Audit Results | control_table_rows、exception list、evidence index |
| Bad Case Center | Evaluation Center | regression dataset membership |
| Agent Workflow | All Services | step input refs、output refs、status、error |

### 5.5 工程规则

- API 层只负责参数校验和响应封装，业务逻辑下沉到 Service 层。
- OCR、LLM、Embedding 和 Reranker 通过 Provider 抽象，避免绑定单一供应商。
- 所有 LLM 输出必须经过 Pydantic Schema 校验。
- Rule Engine 规则可配置、可版本化、可单元测试。
- 所有字段抽取和规则结果必须带证据引用。
- 人工修改不得覆盖原始数据，只能新增修正记录和复核状态。
- 日志不得输出完整敏感底稿、密钥、账号和未脱敏个人信息。

---

## 6. GitHub目录结构

推荐目录结构如下：

```text
financial-audit-ai/
├── README.md
├── docker-compose.yml
├── .env.example
├── .gitignore
├── docs/
│   ├── FinancialAuditAI_最终版项目开发执行手册.md
│   ├── api_reference.md
│   ├── architecture.md
│   ├── database_schema.md
│   ├── rule_engine.md
│   ├── rag_design.md
│   ├── agent_workflow.md
│   ├── review_center.md
│   ├── evaluation.md
│   └── screenshots/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   ├── tasks.py
│   │   │   ├── documents.py
│   │   │   ├── ocr.py
│   │   │   ├── extraction.py
│   │   │   ├── audit.py
│   │   │   ├── rules.py
│   │   │   ├── rag.py
│   │   │   ├── agents.py
│   │   │   ├── review.py
│   │   │   ├── reports.py
│   │   │   ├── bad_cases.py
│   │   │   └── evaluation.py
│   │   ├── core/
│   │   ├── schemas/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── services/
│   │   │   ├── task_service.py
│   │   │   ├── document_service.py
│   │   │   ├── ocr_service.py
│   │   │   ├── classification_service.py
│   │   │   ├── extraction_service.py
│   │   │   ├── linkage_service.py
│   │   │   ├── rule_engine_service.py
│   │   │   ├── rag_service.py
│   │   │   ├── agent_service.py
│   │   │   ├── review_service.py
│   │   │   ├── report_service.py
│   │   │   ├── bad_case_service.py
│   │   │   └── evaluation_service.py
│   │   ├── ai/
│   │   │   ├── ocr_provider.py
│   │   │   ├── llm_provider.py
│   │   │   ├── embedding_provider.py
│   │   │   ├── prompts/
│   │   │   └── validators.py
│   │   ├── rules/
│   │   │   ├── engine.py
│   │   │   ├── registry.py
│   │   │   ├── procurement.py
│   │   │   ├── sales.py
│   │   │   └── validators.py
│   │   ├── rag/
│   │   │   ├── chunking.py
│   │   │   ├── retriever.py
│   │   │   ├── reranker.py
│   │   │   └── citation.py
│   │   ├── agents/
│   │   │   ├── runner.py
│   │   │   ├── state.py
│   │   │   ├── tools.py
│   │   │   └── workflows.py
│   │   ├── evaluation/
│   │   └── db/
│   ├── tests/
│   │   ├── test_task_api.py
│   │   ├── test_document_api.py
│   │   ├── test_rule_engine.py
│   │   ├── test_procurement_rules.py
│   │   ├── test_rag_service.py
│   │   ├── test_agent_workflow.py
│   │   └── test_review_flow.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── routes/
│   │   ├── store/
│   │   ├── types/
│   │   └── utils/
│   └── package.json
├── evals/
│   ├── datasets/
│   ├── expected/
│   ├── results/
│   └── scripts/
├── samples/
│   ├── procurement/
│   ├── sales/
│   ├── confirmation/
│   ├── interview/
│   └── contract_review/
├── local_storage/
│   ├── uploads/
│   ├── pages/
│   ├── reports/
│   └── vector_index/
└── scripts/
    ├── seed_demo_data.py
    ├── run_evals.py
    └── danger_check.py
```

目录设计说明：

- `backend/app/api/` 保存路由，路由保持轻量。
- `backend/app/services/` 保存业务服务。
- `backend/app/rules/` 保存规则引擎核心、规则注册和场景规则。
- `backend/app/rag/` 保存切块、检索、重排和引用逻辑。
- `backend/app/agents/` 保存状态机、工具调用和工作流。
- `evals/` 保存评测数据、预期输出和结果。
- `local_storage/` 保存本地上传、页图片、导出报告和向量索引，不进入 Git。
- `samples/` 只保存可公开的模拟或脱敏样例。

---

## 7. FastAPI后端结构

### 7.1 后端职责

FastAPI 后端应负责：

- 用户认证、角色权限和审计日志。
- 审核任务、文档、OCR、分类、抽取、归集、规则审核和报告导出。
- RAG 四库文档入库、切块、embedding、检索和引用。
- Agent Workflow 状态机、工具调用、失败处理和人工复核路由。
- Review Center 的字段修正、异常确认、驳回异常和复核意见。
- Bad Case 与 Evaluation Center 的数据集、指标和回归结果。
- 稳定 JSON API 和一致错误响应。

### 7.2 后端分层

| 层级 | 职责 |
| --- | --- |
| api | HTTP 路由、参数校验、响应封装 |
| schemas | Pydantic 请求、响应、LLM 输出和规则输出模型 |
| services | 业务流程编排 |
| repositories | 数据库查询和持久化 |
| models | SQLAlchemy 数据模型 |
| ai | OCR、LLM、Embedding Provider 和 Prompt |
| rules | Rule Engine、规则注册、规则版本和规则评测 |
| rag | 文档切块、向量检索、重排和 citation |
| agents | 状态机、工具调用、运行日志 |
| evaluation | 数据集加载、指标计算、回归评测 |
| core | 配置、异常、日志、安全、RBAC 和依赖注入 |

### 7.3 API 规划

基础接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 服务健康检查 |
| GET | `/api/v1/config` | 查询前端配置 |

任务接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/tasks` | 创建审核任务 |
| GET | `/api/v1/tasks` | 任务列表 |
| GET | `/api/v1/tasks/{task_id}` | 任务详情 |
| PATCH | `/api/v1/tasks/{task_id}` | 修改任务信息 |
| POST | `/api/v1/tasks/{task_id}/run` | 启动端到端流程 |

文档接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/tasks/{task_id}/documents` | 上传文件 |
| GET | `/api/v1/tasks/{task_id}/documents` | 文档列表 |
| GET | `/api/v1/documents/{document_id}` | 文档详情 |
| GET | `/api/v1/documents/{document_id}/pages` | OCR 页结果 |
| POST | `/api/v1/documents/{document_id}/ocr` | 运行 OCR |
| POST | `/api/v1/documents/{document_id}/classify` | 文档分类 |
| POST | `/api/v1/documents/{document_id}/extract` | 字段抽取 |

审核与规则接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/tasks/{task_id}/link-documents` | 归集业务链路 |
| POST | `/api/v1/tasks/{task_id}/audit` | 运行规则审核 |
| GET | `/api/v1/tasks/{task_id}/audit-results` | 审核结果列表 |
| GET | `/api/v1/audit-results/{result_id}` | 审核结果详情 |
| GET | `/api/v1/rules` | 规则列表 |
| POST | `/api/v1/rules` | 创建规则 |
| PATCH | `/api/v1/rules/{rule_id}` | 更新规则 |
| POST | `/api/v1/rules/{rule_id}/evaluate` | 规则评测 |

复核接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/review/queue` | 复核队列 |
| POST | `/api/v1/review/comments` | 新增复核意见 |
| PATCH | `/api/v1/fields/{field_id}` | 修正字段 |
| POST | `/api/v1/audit-results/{result_id}/confirm` | 确认异常 |
| POST | `/api/v1/audit-results/{result_id}/dismiss` | 驳回异常 |
| POST | `/api/v1/audit-results/{result_id}/rerun` | 字段修正后重跑规则 |

RAG 接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/rag/documents` | 上传知识文档 |
| POST | `/api/v1/rag/documents/{doc_id}/index` | 构建索引 |
| POST | `/api/v1/rag/query` | 知识库查询 |
| GET | `/api/v1/rag/chunks/{chunk_id}` | 查看引用 Chunk |

Agent 接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/agents/runs` | 启动工作流 |
| GET | `/api/v1/agents/runs/{run_id}` | 查询运行详情 |
| GET | `/api/v1/agents/runs/{run_id}/steps` | 查询步骤 |
| POST | `/api/v1/agents/runs/{run_id}/retry` | 重试失败步骤 |

报告与评测接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/tasks/{task_id}/reports/control-table` | 生成控制表 |
| GET | `/api/v1/reports/{report_id}/download` | 下载报告 |
| POST | `/api/v1/bad-cases` | 新增 Bad Case |
| GET | `/api/v1/bad-cases` | Bad Case 列表 |
| POST | `/api/v1/evaluations/run` | 运行评测 |
| GET | `/api/v1/evaluations/results` | 评测结果 |

### 7.4 通用响应

成功响应：

```json
{
  "data": {},
  "request_id": "req_001"
}
```

错误响应：

```json
{
  "error": {
    "code": "rule_engine_failed",
    "message": "Rule engine execution failed.",
    "details": {}
  },
  "request_id": "req_001"
}
```

### 7.5 后端工程规则

- 上传文件必须校验后缀、MIME、大小、hash 和任务权限。
- OCR、抽取、评测、报告生成等长任务应记录状态，不长时间阻塞请求。
- LLM 输出必须 Schema 校验，不合格输出进入 Bad Case 候选。
- Rule Engine 结果必须包含 rule_code、status、severity、message、evidence。
- 复核接口必须写 audit_logs。
- API 不返回底层 traceback，不在日志中输出敏感原文。

---

## 8. React前端结构

### 8.1 前端职责

React 前端负责审核工作台交互、证据展示、人工复核、规则配置、知识库检索、报告预览和评测结果查看，不负责执行 OCR、LLM、规则计算或向量检索。

### 8.2 前端目录

```text
frontend/src/
├── api/
│   ├── client.ts
│   ├── tasks.ts
│   ├── documents.ts
│   ├── audit.ts
│   ├── rules.ts
│   ├── rag.ts
│   ├── agents.ts
│   ├── review.ts
│   ├── reports.ts
│   └── evaluation.ts
├── components/
│   ├── DocumentViewer.tsx
│   ├── EvidenceHighlighter.tsx
│   ├── FieldTable.tsx
│   ├── RuleResultTable.tsx
│   ├── ReviewDrawer.tsx
│   ├── AgentStateTimeline.tsx
│   ├── CitationList.tsx
│   └── ControlTablePreview.tsx
├── pages/
│   ├── DashboardPage.tsx
│   ├── TaskCenterPage.tsx
│   ├── AuditWorkbenchPage.tsx
│   ├── ReviewCenterPage.tsx
│   ├── RuleCenterPage.tsx
│   ├── KnowledgeCenterPage.tsx
│   ├── ReportCenterPage.tsx
│   ├── BadCaseCenterPage.tsx
│   ├── EvaluationCenterPage.tsx
│   └── AdminPage.tsx
├── store/
├── types/
├── routes/
└── utils/
```

### 8.3 页面设计

| 页面 | 功能 |
| --- | --- |
| Dashboard | 展示任务状态、异常数量、待复核数、通过率和最近评测 |
| Task Center | 新建任务、上传文件、启动流程和查看状态 |
| Audit Workbench | 文档查看、bbox 高亮、字段表、规则结果和 Agent 状态 |
| Review Center | 复核队列、字段修正、确认异常、驳回异常和意见 |
| Rule Center | 规则列表、规则版本、参数配置和规则测试 |
| Knowledge Center | RAG 四库管理、chunk 查看和检索测试 |
| Report Center | 控制表预览、异常清单、证据索引和下载 |
| Bad Case Center | 错误样例、根因、修复方案和回归状态 |
| Evaluation Center | 各模块评测结果、失败样例和版本对比 |
| Admin Center | 用户、角色、权限、模型配置和审计日志 |

### 8.4 前端工程规则

- 页面只调用 `src/api/` 中封装的接口。
- 文档查看器必须支持页码跳转和证据高亮。
- 规则结果必须展示 status、severity、message、actual_value、expected_value 和 evidence。
- RAG 引用必须展示知识库类型、标题、章节、score 和片段。
- 字段修正必须展示 before / after，并要求填写修正原因。
- 长任务展示状态、进度、错误和重试入口。

---

## 9. PostgreSQL数据库设计

### 9.1 设计原则

- 主键统一使用 UUID。
- 核心表包含 `created_at`、`updated_at`。
- AI 结果保留 `confidence`、`source_page`、`source_bbox`、`source_text` 或 `evidence`。
- 人工修改通过 review、audit_log 和 correction 字段记录，不覆盖原始证据。
- JSONB 用于灵活字段、规则参数、模型输出和证据列表。
- pgvector 用于 `rag_chunks.embedding`。
- `model_invocations` 记录模型调用、版本、耗时、Token、错误和成本估算。

### 9.2 users

用途：存储系统用户。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 用户 ID |
| email | VARCHAR UNIQUE | 登录邮箱 |
| password_hash | VARCHAR | 密码哈希 |
| full_name | VARCHAR | 姓名 |
| organization | VARCHAR | 机构或项目组 |
| title | VARCHAR | 职务 |
| status | VARCHAR | active / disabled |
| last_login_at | TIMESTAMP | 最近登录 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.3 roles

用途：存储角色和权限点。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 角色 ID |
| code | VARCHAR UNIQUE | analyst / reviewer / manager / admin / viewer |
| name | VARCHAR | 角色名称 |
| description | TEXT | 说明 |
| permissions | JSONB | 权限点数组 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.4 user_roles

用途：用户与角色多对多关系。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 关系 ID |
| user_id | UUID FK | 用户 |
| role_id | UUID FK | 角色 |
| created_at | TIMESTAMP | 创建时间 |

### 9.5 audit_tasks

用途：审核任务主表。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 任务 ID |
| task_no | VARCHAR UNIQUE | 任务编号 |
| name | VARCHAR | 任务名称 |
| scenario | VARCHAR | procurement / sales / confirmation / interview / contract_review |
| project_name | VARCHAR | 项目或模拟项目名称 |
| company_name | VARCHAR | 被审核主体 |
| fiscal_year | INTEGER | 会计年度 |
| period_start | DATE | 审核期间开始 |
| period_end | DATE | 审核期间结束 |
| status | VARCHAR | draft / uploaded / ocr_running / extracting / auditing / reviewing / completed / failed |
| risk_level | VARCHAR | low / medium / high |
| owner_id | UUID FK | 创建人 |
| reviewer_id | UUID FK | 默认复核人 |
| metadata | JSONB | 行业、币种、税率、样本来源等 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.6 documents

用途：文档主表，一份上传文件对应一条记录。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 文档 ID |
| task_id | UUID FK | 所属任务 |
| uploaded_by | UUID FK | 上传人 |
| original_filename | VARCHAR | 原始文件名 |
| file_ext | VARCHAR | pdf / docx / png / jpg / xlsx |
| file_size | BIGINT | 文件大小 |
| file_hash | VARCHAR | 文件哈希 |
| storage_path | TEXT | 原文件路径 |
| doc_type | VARCHAR | 文档类型 |
| doc_type_confidence | NUMERIC | 分类置信度 |
| business_key | VARCHAR | 业务归集键 |
| page_count | INTEGER | 页数 |
| ocr_status | VARCHAR | OCR 状态 |
| extraction_status | VARCHAR | 抽取状态 |
| review_status | VARCHAR | 复核状态 |
| classification_reason | TEXT | 分类理由 |
| metadata | JSONB | 文档来源、别名、脱敏标记等 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.7 document_pages

用途：页级 OCR 结果。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 页 ID |
| document_id | UUID FK | 文档 |
| page_number | INTEGER | 页码 |
| image_path | TEXT | 页图片 |
| raw_text | TEXT | OCR 全文 |
| ocr_blocks | JSONB | 文本块、bbox、confidence |
| table_blocks | JSONB | 表格识别结果 |
| width | INTEGER | 页面宽度 |
| height | INTEGER | 页面高度 |
| ocr_engine | VARCHAR | OCR 引擎 |
| ocr_confidence | NUMERIC | 页级置信度 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.8 extracted_fields

用途：字段抽取结果，每个字段一行。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 字段 ID |
| task_id | UUID FK | 任务 |
| document_id | UUID FK | 文档 |
| field_name | VARCHAR | 字段名 |
| field_label | VARCHAR | 中文名 |
| field_type | VARCHAR | string / date / number / money / array / boolean |
| value_text | TEXT | 原始文本值 |
| value_normalized | JSONB | 标准化值 |
| unit | VARCHAR | 单位 |
| currency | VARCHAR | 币种 |
| confidence | NUMERIC | 置信度 |
| source_page | INTEGER | 来源页 |
| source_bbox | JSONB | 来源坐标 |
| source_text | TEXT | 来源片段 |
| extraction_method | VARCHAR | llm / regex / ocr_table / manual |
| is_required | BOOLEAN | 是否必填 |
| is_verified | BOOLEAN | 是否人工确认 |
| corrected_by | UUID FK | 修正人 |
| corrected_at | TIMESTAMP | 修正时间 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.9 audit_rules

用途：规则库。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 规则 ID |
| rule_code | VARCHAR UNIQUE | 规则编码 |
| name | VARCHAR | 规则名称 |
| scenario | VARCHAR | 适用场景 |
| category | VARCHAR | time / quantity / amount / name / item / completeness / tax |
| severity | VARCHAR | info / warning / high / critical |
| description | TEXT | 规则说明 |
| expression | TEXT | 规则表达式或 DSL |
| parameters | JSONB | 容差、税率、别名表、字段映射 |
| required_fields | JSONB | 依赖字段 |
| enabled | BOOLEAN | 是否启用 |
| version | INTEGER | 规则版本 |
| created_by | UUID FK | 创建人 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.10 audit_results

用途：规则执行结果。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 结果 ID |
| task_id | UUID FK | 任务 |
| rule_id | UUID FK | 规则 |
| rule_code | VARCHAR | 规则编码 |
| business_key | VARCHAR | 业务链路 |
| status | VARCHAR | pass / fail / warning / not_applicable / need_review |
| severity | VARCHAR | 严重程度 |
| message | TEXT | 结果说明 |
| expected_value | JSONB | 期望值或阈值 |
| actual_value | JSONB | 实际值 |
| evidence | JSONB | 证据列表 |
| rag_citations | JSONB | RAG 引用 |
| review_status | VARCHAR | pending / confirmed / dismissed / fixed |
| reviewed_by | UUID FK | 复核人 |
| reviewed_at | TIMESTAMP | 复核时间 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.11 review_comments

用途：人工复核意见和修正记录。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 评论 ID |
| task_id | UUID FK | 任务 |
| document_id | UUID FK NULL | 文档 |
| audit_result_id | UUID FK NULL | 审核结果 |
| field_id | UUID FK NULL | 字段 |
| author_id | UUID FK | 评论人 |
| comment_type | VARCHAR | note / field_correction / exception_confirmation / rejection |
| content | TEXT | 内容 |
| before_value | JSONB | 修改前 |
| after_value | JSONB | 修改后 |
| attachment_path | TEXT | 附件 |
| created_at | TIMESTAMP | 创建时间 |

### 9.12 reports

用途：报告与控制表导出记录。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 报告 ID |
| task_id | UUID FK | 任务 |
| report_type | VARCHAR | control_table / audit_report / exception_list / evaluation_report |
| title | VARCHAR | 标题 |
| status | VARCHAR | generating / completed / failed |
| file_format | VARCHAR | xlsx / csv / pdf / md |
| storage_path | TEXT | 文件路径 |
| summary | JSONB | 摘要 |
| generated_by | UUID FK | 生成人 |
| generated_at | TIMESTAMP | 生成时间 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.13 rag_documents

用途：RAG 知识库文档。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 知识文档 ID |
| knowledge_base | VARCHAR | regulation / inquiry_case / prospectus / workpaper |
| title | VARCHAR | 标题 |
| source_type | VARCHAR | law / exchange_rule / inquiry_letter / prospectus / uploaded_workpaper |
| source_url | TEXT | 公开来源 URL |
| issuer_name | VARCHAR | 发行人或案例主体 |
| publish_date | DATE | 发布日期 |
| effective_date | DATE | 生效日期 |
| file_path | TEXT | 文件路径 |
| checksum | VARCHAR | 文件哈希 |
| metadata | JSONB | 行业、板块、章节、监管机构、来源标记 |
| created_by | UUID FK | 创建人 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.14 rag_chunks

用途：知识库切片和向量。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | Chunk ID |
| rag_document_id | UUID FK | 知识文档 |
| chunk_index | INTEGER | 序号 |
| chunk_text | TEXT | 文本 |
| embedding | VECTOR | 向量 |
| token_count | INTEGER | Token 数 |
| section_title | VARCHAR | 章节 |
| article_no | VARCHAR | 条号或问题编号 |
| page_start | INTEGER | 起始页 |
| page_end | INTEGER | 结束页 |
| metadata | JSONB | 主题、关键词、风险标签 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.15 agent_runs

用途：Agent 工作流运行记录。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 运行 ID |
| task_id | UUID FK | 任务 |
| workflow_name | VARCHAR | 工作流名称 |
| status | VARCHAR | pending / running / completed / failed / human_review_required |
| current_state | VARCHAR | 当前状态 |
| input_refs | JSONB | 输入引用 |
| output_refs | JSONB | 输出引用 |
| error | JSONB | 错误 |
| started_at | TIMESTAMP | 开始时间 |
| finished_at | TIMESTAMP | 结束时间 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.16 agent_steps

用途：Agent 每一步工具调用和状态变更。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 步骤 ID |
| run_id | UUID FK | 运行 ID |
| step_name | VARCHAR | 步骤名称 |
| step_order | INTEGER | 顺序 |
| tool_name | VARCHAR | 工具名称 |
| status | VARCHAR | pending / running / completed / failed / skipped |
| input_payload | JSONB | 输入，需脱敏 |
| output_payload | JSONB | 输出，需脱敏 |
| error | JSONB | 错误 |
| duration_ms | INTEGER | 耗时 |
| created_at | TIMESTAMP | 创建时间 |

### 9.17 document_relations

用途：记录同一笔业务中文档之间的关联。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 关系 ID |
| task_id | UUID FK | 任务 |
| business_key | VARCHAR | 业务归集键 |
| source_document_id | UUID FK | 来源文档 |
| target_document_id | UUID FK | 目标文档 |
| relation_type | VARCHAR | contract_invoice / invoice_payment / contract_receipt 等 |
| confidence | NUMERIC | 关联置信度 |
| evidence | JSONB | 关联证据 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.18 control_table_rows

用途：控制表行，支持前端预览和导出。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 行 ID |
| task_id | UUID FK | 任务 |
| business_key | VARCHAR | 业务归集键 |
| scenario | VARCHAR | 场景 |
| row_data | JSONB | 控制表字段 |
| overall_status | VARCHAR | pass / warning / fail / need_review |
| evidence_refs | JSONB | 证据 |
| reviewer_comment | TEXT | 复核意见 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.19 audit_logs

用途：关键操作审计日志。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 日志 ID |
| user_id | UUID FK | 操作人 |
| task_id | UUID FK NULL | 任务 |
| action | VARCHAR | 操作类型 |
| target_type | VARCHAR | 目标类型 |
| target_id | UUID | 目标 ID |
| before_value | JSONB | 操作前 |
| after_value | JSONB | 操作后 |
| ip_address | VARCHAR | IP |
| user_agent | TEXT | User Agent |
| created_at | TIMESTAMP | 创建时间 |

### 9.20 model_invocations

用途：模型调用记录。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 调用 ID |
| task_id | UUID FK NULL | 任务 |
| document_id | UUID FK NULL | 文档 |
| provider | VARCHAR | openai / qwen / deepseek / local |
| model_name | VARCHAR | 模型名称 |
| invocation_type | VARCHAR | ocr / classify / extract / embed / rerank / explain |
| prompt_version | VARCHAR | Prompt 版本 |
| input_hash | VARCHAR | 输入哈希 |
| output_schema | VARCHAR | 输出 Schema |
| status | VARCHAR | success / failed |
| latency_ms | INTEGER | 耗时 |
| token_usage | JSONB | Token 使用 |
| error | JSONB | 错误 |
| created_at | TIMESTAMP | 创建时间 |

### 9.21 bad_cases

用途：错误样例、根因和修复策略。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | Bad Case ID |
| task_id | UUID FK NULL | 来源任务 |
| document_id | UUID FK NULL | 来源文档 |
| case_type | VARCHAR | ocr / classification / extraction / rule / rag / agent / review |
| title | VARCHAR | 标题 |
| input_payload | JSONB | 输入 |
| model_output | JSONB | 输出 |
| expected_output | JSONB | 期望 |
| root_cause | TEXT | 根因 |
| fix_plan | TEXT | 修复方案 |
| status | VARCHAR | open / fixed / verified / wont_fix |
| severity | VARCHAR | low / medium / high |
| owner_id | UUID FK | 负责人 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 9.22 evaluation_results

用途：评测结果。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| id | UUID PK | 评测 ID |
| eval_name | VARCHAR | 评测名称 |
| eval_type | VARCHAR | classification / ocr / extraction / rule / rag / agent / end_to_end / regression |
| dataset_name | VARCHAR | 数据集 |
| model_name | VARCHAR | 模型 |
| prompt_version | VARCHAR | Prompt 版本 |
| rule_version | VARCHAR | 规则版本 |
| metrics | JSONB | 指标 |
| sample_count | INTEGER | 样本数 |
| failed_cases | JSONB | 失败样例 |
| report_path | TEXT | 报告路径 |
| created_by | UUID FK | 执行人 |
| created_at | TIMESTAMP | 创建时间 |

### 9.23 表关系

```text
users -> user_roles -> roles
users -> audit_tasks
audit_tasks -> documents -> document_pages
audit_tasks -> extracted_fields
audit_tasks -> document_relations
audit_tasks -> audit_results -> review_comments
audit_rules -> audit_results
audit_tasks -> control_table_rows -> reports
rag_documents -> rag_chunks
audit_tasks -> agent_runs -> agent_steps
audit_tasks -> bad_cases
evaluation_results -> bad_cases
audit_logs records all critical actions
model_invocations records AI calls
```

---

## 10. 核心业务流

### 10.1 任务创建业务流

```text
create task
  -> validate scenario and period
  -> assign owner and reviewer
  -> initialize task status
  -> write audit_log
```

### 10.2 文档处理业务流

```text
upload document
  -> validate file
  -> hash and store
  -> render pages
  -> run OCR
  -> save document_pages
  -> classify document
  -> extract fields by doc_type
  -> save extracted_fields
```

### 10.3 采购穿行业务流

```text
six procurement document types
  -> normalize fields
  -> link business documents
  -> build business_key
  -> run procurement rules
  -> generate audit_results
  -> route review
  -> generate control_table_rows
```

### 10.4 人工复核业务流

```text
need_review item
  -> reviewer opens evidence
  -> correct field or review audit result
  -> confirm / dismiss / fixed / re_extract_requested
  -> write review_comments and audit_logs
  -> rerun rules if needed
```

### 10.5 RAG 业务流

```text
rag document
  -> parse
  -> chunk
  -> metadata
  -> embedding
  -> pgvector index
  -> retrieval
  -> rerank
  -> citations
```

### 10.6 Agent 工作流

```text
agent_run
  -> intake
  -> OCR
  -> classification
  -> extraction
  -> linkage
  -> rule audit
  -> evidence retrieval
  -> review routing
  -> report generation
```

### 10.7 报告导出业务流

```text
audit_results + extracted_fields + review_comments
  -> build control_table_rows
  -> build exception list
  -> build evidence index
  -> export xlsx / csv / pdf
  -> save reports
```

---

## 11. 采购穿行模块

### 11.1 模块职责

采购穿行模块用于验证采购业务从申请、审批、合同签订、收货入库、取得发票、财务入账到付款的链路是否完整、一致、合理。该模块是 MVP 主线，必须打通端到端闭环。

### 11.2 输入

- 采购申请单 `purchase_request`。
- 采购合同 `purchase_contract`。
- 入库单 `warehouse_receipt`。
- 发票 `invoice`。
- 记账凭证 `accounting_voucher`。
- 付款回单 `payment_receipt`。
- OCR 文本、字段抽取结果、line_items、供应商别名表、品种映射表和规则参数。

### 11.3 输出

- `document_relations`。
- `audit_results`。
- `control_table_rows`。
- 异常清单。
- 证据索引。

### 11.4 六类采购文件字段 Schema

采购申请单 `purchase_request`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| request_no | string | 是 | 采购申请单号 |
| request_date | date | 是 | 申请日期 |
| applicant_dept | string | 建议 | 申请部门 |
| requester | string | 建议 | 申请人 |
| approver | string | 建议 | 审批人 |
| approval_date | date | 是 | 审批日期 |
| supplier_candidate | string | 可选 | 拟采购供应商 |
| item_lines | array | 是 | 品种、规格、数量、单位、预计单价、预计金额 |
| total_estimated_amount | money | 是 | 预计总金额 |
| budget_code | string | 可选 | 预算编号 |
| approval_status | string | 是 | 已审批、待审批、驳回 |
| source_text | string | 是 | 来源片段 |

采购合同 `purchase_contract`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| contract_no | string | 是 | 合同编号 |
| signing_date | date | 是 | 签署日期 |
| buyer_name | string | 是 | 采购方 |
| supplier_name | string | 是 | 供应商 |
| supplier_tax_no | string | 建议 | 供应商税号 |
| item_lines | array | 是 | 品种、规格、数量、单位、单价、金额、税率 |
| amount_excluding_tax | money | 建议 | 不含税金额 |
| tax_rate | number | 建议 | 税率 |
| tax_amount | money | 建议 | 税额 |
| amount_including_tax | money | 是 | 含税总金额 |
| payment_terms | string | 建议 | 付款条款 |
| delivery_terms | string | 建议 | 交付条款 |
| effective_date | date | 可选 | 生效日期 |
| expiry_date | date | 可选 | 到期日期 |
| seal_detected | boolean | 可选 | 是否识别盖章 |
| signature_detected | boolean | 可选 | 是否识别签字 |

入库单 `warehouse_receipt`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| receipt_no | string | 是 | 入库单号 |
| receipt_date | date | 是 | 入库日期 |
| supplier_name | string | 是 | 供应商 |
| warehouse_name | string | 建议 | 仓库 |
| receiver | string | 建议 | 收货人 |
| related_contract_no | string | 建议 | 关联合同号 |
| item_lines | array | 是 | 品种、规格、实收数量、单位 |
| quality_status | string | 可选 | 合格、不合格、待检 |
| source_text | string | 是 | 来源片段 |

发票 `invoice`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| invoice_code | string | 可选 | 发票代码 |
| invoice_no | string | 是 | 发票号码 |
| invoice_date | date | 是 | 开票日期 |
| seller_name | string | 是 | 销售方 |
| seller_tax_no | string | 建议 | 销售方税号 |
| buyer_name | string | 是 | 购买方 |
| buyer_tax_no | string | 建议 | 购买方税号 |
| item_lines | array | 是 | 名称、规格、数量、单价、金额、税率、税额 |
| amount_excluding_tax | money | 是 | 不含税金额 |
| tax_amount | money | 是 | 税额 |
| amount_including_tax | money | 是 | 价税合计 |
| invoice_type | string | 建议 | 专票、普票、电子发票 |
| checksum | string | 可选 | 校验码 |

记账凭证 `accounting_voucher`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| voucher_no | string | 是 | 凭证号 |
| voucher_date | date | 是 | 凭证日期 |
| summary | string | 是 | 摘要 |
| debit_subject | string | 是 | 借方科目 |
| credit_subject | string | 是 | 贷方科目 |
| amount | money | 是 | 凭证金额 |
| supplier_name | string | 建议 | 供应商或往来单位 |
| related_invoice_no | string | 建议 | 关联发票号 |
| preparer | string | 可选 | 制单人 |
| reviewer | string | 可选 | 审核人 |
| attachment_count | number | 可选 | 附件张数 |

付款回单 `payment_receipt`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| payment_no | string | 是 | 回单号或银行流水号 |
| payment_date | date | 是 | 付款日期 |
| payer_name | string | 是 | 付款方 |
| payee_name | string | 是 | 收款方 |
| payee_account_masked | string | 可选 | 收款账号脱敏 |
| bank_name | string | 可选 | 开户行 |
| amount | money | 是 | 付款金额 |
| currency | string | 是 | 币种 |
| payment_purpose | string | 建议 | 用途或摘要 |
| related_contract_no | string | 建议 | 关联合同号 |
| bank_serial_no | string | 可选 | 银行流水号 |

### 11.5 采购穿行规则

| 规则类型 | 校验逻辑 | 异常示例 |
| --- | --- | --- |
| 时间规则 | 申请/审批日期 <= 合同签署日期 <= 入库日期 <= 发票日期 <= 凭证日期 <= 付款日期 | 合同日期早于审批日期 |
| 数量规则 | 申请数量 >= 合同数量，合同数量 >= 入库数量，支持分批到货和累计 | 入库数量大于合同数量 |
| 金额规则 | 合同含税金额 >= 发票含税金额，累计付款金额 <= 合同含税金额 | 付款超过合同金额 |
| 名称一致性 | 合同供应商、发票销售方、回单收款方一致或命中别名表 | 合同供应商与发票销售方不一致 |
| 品种一致性 | 合同、入库、发票品种可标准化匹配 | 发票出现合同未包含品种 |
| 税率 | 合同税率与发票税率一致或有合理说明 | 合同 13%，发票 6% |
| 缺字段 | 必填字段缺失输出 need_review | 发票号缺失 |
| 多品种 | 按 item_key 分别比较数量、单价、金额 | 多个品种被合并成一行 |
| 含税/不含税 | 区分不含税金额、税额、含税金额和税率 | 用不含税金额直接比较含税合同金额 |

### 11.6 业务规则

- 同一笔业务优先通过合同号、发票号、银行用途、凭证摘要等显式字段归集。
- 显式字段不足时，可以使用供应商、日期区间、金额、品种组合匹配，但低置信度必须进入人工复核。
- 多张发票、多次付款必须累计比较。
- 多品种必须按明细行匹配，不得只比较总金额。
- 字段缺失不应默认通过。
- 所有异常必须保留证据列表。

### 11.7 风险点

| 风险 | 说明 | 处理方式 |
| --- | --- | --- |
| 文件链路不完整 | 六类文件缺失 | 输出 need_review |
| OCR 金额误识别 | 小数点、逗号、币种错误 | 来源高亮 + 人工复核 |
| 多品种错配 | 明细行无法对齐 | item_key 标准化 |
| 分批付款误判 | 一对多关系被当成一对一 | business_key 聚合 |
| 税口径误判 | 含税/不含税混用 | 金额字段拆分 |

### 11.8 验收标准

- 六类采购文件可上传、分类、抽取字段。
- 能生成 business_key 和 document_relations。
- 能执行时间、数量、金额、名称、品种、税率、缺字段、多品种和含税口径规则。
- 控制表每一行能追溯到字段证据和规则结果。
- 异常能进入 Review Center。

---

## 12. 销售穿行模块

### 12.1 模块职责

销售穿行模块复用采购穿行的 OCR、分类、抽取、归集、规则、复核和报告框架，验证销售业务从合同、订单、出库、签收、开票、收款和入账的链路一致性。

### 12.2 输入

- 销售合同、销售订单、出库单、物流/签收单、销售发票、收款凭证、记账凭证。

### 12.3 输出

- 销售业务归集关系。
- 销售穿行规则结果。
- 销售控制表。
- 异常清单。

### 12.4 核心字段 / Schema

| 文件 | 核心字段 |
| --- | --- |
| 销售合同 | 合同号、客户名称、签署日期、销售品种、数量、单价、金额、交付条款、收款条款 |
| 销售订单 | 订单号、客户名称、订单日期、品种、数量、金额 |
| 出库单 | 出库单号、出库日期、客户名称、品种、出库数量、仓库、经办人 |
| 物流/签收单 | 物流单号、发货日期、签收日期、收货单位、签收人、数量 |
| 销售发票 | 发票号、开票日期、购买方、货物名称、数量、税率、价税合计 |
| 收款凭证 | 收款日期、付款方、收款方、金额、用途、银行流水号 |
| 记账凭证 | 凭证号、凭证日期、收入科目、应收账款/银行存款、金额 |

### 12.5 业务规则

- 合同日期 <= 订单日期 <= 出库日期 <= 签收日期 <= 开票日期。
- 发票金额 <= 合同金额，累计收款金额 <= 合同金额。
- 客户名称在合同、订单、发票、收款方中一致。
- 出库数量、签收数量、开票数量一致或有差异说明。
- 收入确认时间与签收、验收、开票的关系可配置。
- 跨期收入识别高风险提示。

### 12.6 风险点

- 销售业务存在一合同多订单、多次交付、多次开票和多次收款。
- 物流签收与收入确认规则需要结合业务政策。
- 客户名称和付款方可能存在集团、子公司或代付款关系。

### 12.7 验收标准

- 能支持销售场景任务类型。
- 能抽取销售链路核心字段。
- 能输出销售穿行控制表。
- 高风险规则能路由 Review Center。

---

## 13. 函证模块

### 13.1 模块职责

函证模块处理外部确认信息与账面记录的一致性，覆盖发函、回函、差异调节和证据留痕。

### 13.2 输入

- 发函清单、函证模板、发送记录、回函扫描件、银行函证、往来函证、客户/供应商函证、差异调节表。

### 13.3 输出

- 函证字段抽取结果。
- 账面金额与回函金额比对结果。
- 差异调节记录。
- 复核队列。

### 13.4 核心字段 / Schema

| 字段 | 说明 |
| --- | --- |
| confirmation_no | 函证编号 |
| counterparty_name | 被函证单位 |
| counterparty_address | 函证地址 |
| sent_date | 发函日期 |
| replied_date | 回函日期 |
| confirmed_amount | 回函确认金额 |
| book_amount | 账面金额 |
| difference_amount | 差异金额 |
| seal_detected | 是否识别公章 |
| signatory | 签署人 |
| reply_channel | 回函方式 |
| exception_reason | 差异说明 |

### 13.5 业务规则

- 发函对象名称与账面客户/供应商名称一致。
- 回函金额与账面金额一致，不一致时必须有差异调节。
- 发函地址与主数据一致或有说明。
- 回函日期不应早于发函日期。
- 公章、签字、回函方式作为风险提示，不作为唯一判断依据。

### 13.6 风险点

- 回函格式多样，OCR 和字段抽取难度高。
- 差异调节表可能缺少清晰关联。
- 公章和签字识别不稳定。

### 13.7 验收标准

- 能抽取函证核心字段。
- 能比对账面金额、回函金额和差异金额。
- 差异样例进入 Review Center。

---

## 14. 访谈模块

### 14.1 模块职责

访谈模块处理访谈提纲、访谈记录和签字页，抽取被访谈人、主题、关键回答，并与合同、发票、函证等底稿进行交叉验证。

### 14.2 输入

- 访谈提纲、访谈记录、身份证明/名片、签字页、录音转写文本。

### 14.3 输出

- 访谈字段抽取结果。
- 关键回答摘要。
- 与交易底稿的差异提示。
- 签字和身份信息复核项。

### 14.4 核心字段 / Schema

| 字段 | 说明 |
| --- | --- |
| interview_date | 访谈日期 |
| interviewee_name | 被访谈人 |
| interviewee_title | 职务 |
| company_name | 所属单位 |
| interviewer | 访谈人 |
| location | 地点 |
| topics | 主题 |
| key_answers | 关键回答摘要 |
| mentioned_amounts | 提及金额 |
| mentioned_counterparties | 提及客户/供应商 |
| signature_detected | 是否签字 |

### 14.5 业务规则

- 被访谈人姓名、职务、单位与名片或公开资料一致。
- 访谈提及金额与合同、发票、函证金额差异提示。
- 访谈日期应在项目执行期间内。
- 缺少签字页或被访谈人信息时进入人工复核。

### 14.6 风险点

- 访谈文本较长，摘要可能遗漏关键事实。
- 口语化表达需要谨慎映射到结构化字段。
- 访谈内容与底稿差异需要人工解释。

### 14.7 验收标准

- 能抽取访谈核心字段。
- 能识别提及金额、主体和关键回答。
- 能将缺签字、日期异常和底稿差异路由 Review Center。

---

## 15. 合同审核模块

### 15.1 模块职责

合同审核模块覆盖重大合同和关键条款审阅，重点识别主体、金额、期限、付款、交付、验收、违约、特殊条款和缺失条款。

### 15.2 输入

- 重大合同、补充协议、框架协议、订单、验收单、附件。

### 15.3 输出

- 合同字段抽取结果。
- 条款风险提示。
- 与发票、出入库单、银行回单的关联结果。
- 复核项。

### 15.4 核心字段 / Schema

- 合同编号、合同名称、签署日期、生效日期、到期日期。
- 甲方、乙方、关联方、统一社会信用代码。
- 标的物、规格、数量、单价、总金额、税率。
- 付款条款、交付条款、验收条款、违约责任、争议解决。
- 自动续期、排他条款、回购条款、价格调整条款。
- 签字、盖章、附件、补充协议。

### 15.5 业务规则

- 合同有效期覆盖交易发生期间。
- 金额、单价、数量与发票和出入库单一致。
- 合同主体与发票、银行回单主体一致。
- 重大条款缺失提示，例如无付款条款、交付条款或验收标准。
- 回购、保底、可变对价、关联交易等特殊条款进入高风险复核。

### 15.6 风险点

- 合同条款长且结构不统一。
- 特殊条款的风险解释需要保留来源片段。
- 补充协议可能改变主合同条款。

### 15.7 验收标准

- 能抽取合同基础字段和关键条款。
- 能识别缺失条款和特殊条款。
- 能与相关底稿建立关联。

---

## 16. OCR与文档分类模块

### 16.1 模块职责

OCR 与文档分类模块负责将文件转化为页级可定位文本，并判断文档类型，为后续字段抽取和规则审核提供输入。

### 16.2 输入

- PDF、扫描 PDF、PNG、JPG、DOCX、Excel 导出的 PDF。
- 文件名、页图像、OCR 文本、表格结构和前几页摘要。

### 16.3 输出

OCR 输出：

```json
{
  "document_id": "uuid",
  "pages": [
    {
      "page_number": 1,
      "raw_text": "",
      "ocr_confidence": 0.94,
      "blocks": [
        {
          "text": "价税合计 123456.00",
          "bbox": [120, 310, 460, 342],
          "confidence": 0.91
        }
      ],
      "tables": []
    }
  ]
}
```

分类输出：

```json
{
  "document_id": "uuid",
  "doc_type": "purchase_contract",
  "confidence": 0.93,
  "reason": "文本包含合同编号、甲乙方、签署日期、付款条款等特征",
  "alternative_types": [
    {
      "doc_type": "sales_contract",
      "confidence": 0.18
    }
  ],
  "need_human_review": false
}
```

### 16.4 分类标签

| 标签 | 说明 |
| --- | --- |
| purchase_request | 采购申请单 |
| purchase_contract | 采购合同 |
| warehouse_receipt | 入库单 |
| invoice | 发票 |
| accounting_voucher | 记账凭证 |
| payment_receipt | 付款回单 |
| sales_contract | 销售合同 |
| sales_order | 销售订单 |
| delivery_order | 出库单 |
| logistics_receipt | 物流/签收单 |
| confirmation | 函证 |
| interview_record | 访谈记录 |
| prospectus | 招股书 |
| inquiry_letter | 问询函 |
| regulation | 法规规则 |
| unknown | 未知 |

### 16.5 业务规则

- OCR 必须保留页码、文本块、bbox、置信度和表格结构。
- 分类低于阈值时进入人工确认。
- OCR 失败不应导致任务完全不可查看，应记录页级失败。
- 人工纠正分类后应写入 Bad Case 候选。

### 16.6 风险点

- 扫描件模糊、旋转、倾斜。
- 表格错列导致数量、单价、金额串位。
- 发票、付款回单、记账凭证部分字段相似导致分类混淆。
- 公章、签字和手写内容识别不稳定。

### 16.7 验收标准

- 支持 PDF、图片和扫描件 OCR。
- 文档页可在前端高亮证据。
- 分类结果包含 doc_type、confidence、reason 和备选类型。
- 低置信度分类进入 Review Center。

---

## 17. 字段抽取模块

### 17.1 模块职责

字段抽取模块根据文档类型 Schema 从 OCR 文本和表格中抽取结构化字段、明细行和来源证据，并进行标准化。

### 17.2 输入

- document_id。
- doc_type。
- OCR raw_text、blocks、tables。
- 文档类型字段 Schema。

### 17.3 输出

- extracted_fields。
- line_items。
- source evidence。
- warnings。

### 17.4 通用抽取 Schema

```json
{
  "document_id": "uuid",
  "doc_type": "purchase_contract",
  "business_key": "CONTRACT-2026-001",
  "fields": [
    {
      "field_name": "supplier_name",
      "field_label": "供应商名称",
      "field_type": "string",
      "value": "上海某某材料有限公司",
      "normalized_value": "上海某某材料有限公司",
      "confidence": 0.94,
      "required": true,
      "source": {
        "page": 1,
        "bbox": [120, 210, 430, 236],
        "text": "乙方：上海某某材料有限公司"
      },
      "warnings": []
    }
  ],
  "line_items": [
    {
      "item_name": "铝型材",
      "specification": "6061-T6",
      "quantity": 1000,
      "unit": "kg",
      "unit_price": 18.5,
      "amount_excluding_tax": 18500,
      "tax_rate": 0.13,
      "tax_amount": 2405,
      "amount_including_tax": 20905,
      "source": {
        "page": 2,
        "bbox": [80, 120, 710, 190],
        "text": "铝型材 6061-T6 1000kg 18.50..."
      }
    }
  ]
}
```

### 17.5 字段标准化规则

- 日期统一输出为 `YYYY-MM-DD`。
- 金额统一输出为数值，币种单独存储。
- 税率统一输出为小数，例如 13% 输出 `0.13`。
- 名称字段保留原文和标准化名称。
- 多品种明细必须使用 `line_items` 数组。
- 不确定字段输出 `null` 并给出 warning，不允许补全。

### 17.6 风险点

- OCR 表格错列导致抽取错误。
- 金额和税额字段混淆。
- 多行明细被合并。
- LLM 根据上下文猜测缺失字段。

### 17.7 验收标准

- 每个字段包含 field_name、value、confidence 和 source。
- 必填字段缺失时输出 warning。
- line_items 支持多品种、多单位和税率。
- 抽取结果能被 Rule Engine 直接读取。

---

## 18. Rule Engine规则引擎

### 18.1 模块职责

Rule Engine 是审核判断核心，负责读取标准化字段、业务归集关系、规则参数和配置表，输出可解释、可追踪、可复核的审核结果。

### 18.2 输入

- extracted_fields。
- line_items。
- document_relations。
- audit_rules。
- 规则参数、容忍差额、税率配置、别名表、品种映射表。

### 18.3 输出

- audit_results。
- status：pass / fail / warning / not_applicable / need_review。
- severity。
- expected_value、actual_value。
- evidence。
- review routing reason。

### 18.4 规则设计原则

- 确定性优先：能用规则判断的事项不交给 LLM 判断。
- 证据优先：每个 fail / warning / need_review 都必须有证据。
- 人机协同：高风险和低置信度事项进入 Review Center。
- 可配置：容忍差额、税率、日期例外、别名表、品种映射可配置。
- 可版本化：规则启用状态、参数和版本要可追踪。
- 可评测：每条规则应有单元测试和规则评测样例。

### 18.5 规则示例

```yaml
rule_code: PROC_TIME_001
name: 采购穿行时间顺序校验
scenario: procurement
category: time
severity: high
required_fields:
  - request.approval_date
  - contract.signing_date
  - receipt.receipt_date
  - invoice.invoice_date
  - voucher.voucher_date
  - payment.payment_date
logic:
  - request.approval_date <= contract.signing_date
  - contract.signing_date <= receipt.receipt_date
  - receipt.receipt_date <= invoice.invoice_date
  - invoice.invoice_date <= voucher.voucher_date
  - voucher.voucher_date <= payment.payment_date
exceptions:
  - prepayment_allowed_if: contract.payment_terms contains "预付款"
```

### 18.6 核心规则类型

| 类型 | 规则 |
| --- | --- |
| 时间规则 | 申请、合同、入库、发票、凭证、付款顺序 |
| 数量规则 | 申请、合同、入库、发票数量与累计数量 |
| 金额规则 | 合同、发票、凭证、付款金额和容忍差额 |
| 名称一致性 | 供应商、开票方、收款方和往来单位 |
| 品种一致性 | 品种、规格、单位和明细行匹配 |
| 税率 | 不含税金额、税额、含税金额、税率 |
| 缺字段 | 必填字段、规则依赖字段和低置信度字段 |
| 多品种 | item_key、单位换算、逐行匹配 |
| 含税/不含税 | 统一金额口径后比较 |

### 18.7 风险点

- 将例外场景错误判为 fail。
- 缺字段被误判为 pass。
- 多张发票、多次付款未累计。
- 名称别名和品种映射维护不足。
- 规则版本变化后结果不可复现。

### 18.8 验收标准

- 规则可单元测试。
- 规则结果写入 audit_results。
- 每条异常包含 evidence。
- 规则版本和参数可追踪。
- 规则失败、高风险 warning 和缺字段进入 Review Center。

---

## 19. RAG知识库模块

### 19.1 模块职责

RAG 知识库模块负责管理法规库、案例问询库、招股书库和底稿库，为异常解释、复核参考和报告摘要提供可追溯来源。

### 19.2 RAG 四库

| 知识库 | 内容 | 用途 |
| --- | --- | --- |
| regulation | 公司法、证券法、上市规则、信息披露规则、交易所指引 | 法规条款和监管要求检索 |
| inquiry_case | 公开问询函、审核问询与回复、公开案例摘要 | 相似问题和监管关注点 |
| prospectus | 公开招股书业务、采购销售、客户供应商、风险因素章节 | 同业披露口径参考 |
| workpaper | 当前任务 OCR 文本、字段结果、复核后结构化数据 | 当前任务内部证据检索 |

### 19.3 输入

- 公开法规、问询函、招股书。
- 当前任务底稿 OCR 文本和字段结果。
- 检索 query、知识库范围、metadata filter。

### 19.4 输出

```json
{
  "answer": "根据检索结果，采购真实性审核通常关注合同、入库、发票和付款之间的一致性。",
  "citations": [
    {
      "knowledge_base": "inquiry_case",
      "title": "某公司首轮问询函",
      "section": "采购真实性",
      "chunk_id": "uuid",
      "score": 0.86,
      "quote": "监管问询关注采购合同、入库记录、发票和付款凭证是否匹配。"
    }
  ],
  "limitations": "该回答基于公开资料和模拟底稿检索，不构成审计、法律或投资建议。"
}
```

### 19.5 业务规则

- regulation 按章节、条款切分。
- inquiry_case 按问题编号、回复段落和主题切分。
- prospectus 按章节标题和页码切分。
- workpaper 与公开知识库隔离。
- 回答必须包含 citations。
- 检索不到相关依据时应返回证据不足，不生成无来源结论。

### 19.6 风险点

- 过时法规或案例未更新。
- workpaper 敏感信息混入公开知识库。
- 检索结果与异常不相关。
- 生成回答超出 citation 支持范围。

### 19.7 验收标准

- 四类知识库可分别入库和检索。
- chunk 保存知识库类型、标题、章节、页码和 metadata。
- RAG 输出包含 citation 和 limitations。
- RAG 评测包含 Recall@K、Citation Accuracy 和 Groundedness。

---

## 20. Agent Workflow模块

### 20.1 模块职责

Agent Workflow 模块负责用状态机和工具调用编排审核流程，记录每个步骤的输入、输出、状态、耗时和错误，并根据规则结果和置信度路由人工复核。

### 20.2 定位

FinancialAuditAI 的 Agent 是：

```text
状态机 + 工具调用 + 规则约束 + 人工复核路由
```

Agent 不允许绕过 Rule Engine 直接生成审核结论，不允许把检索不到的依据写成结论，不允许自动确认高风险异常。

### 20.3 状态机

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

失败状态：

- OCR_FAILED。
- CLASSIFICATION_FAILED。
- EXTRACTION_FAILED。
- RULE_AUDIT_FAILED。
- EVIDENCE_RETRIEVAL_FAILED。
- REPORT_FAILED。

### 20.4 工具调用

| 工具 | 输入 | 输出 |
| --- | --- | --- |
| `run_ocr(document_id)` | 文档 ID | 页级 OCR JSON |
| `classify_document(document_id)` | OCR 文本 | doc_type、confidence |
| `extract_fields(document_id, doc_type)` | OCR 文本、Schema | 字段 JSON |
| `link_business_documents(task_id)` | 字段结果 | business_key |
| `run_rule_engine(task_id)` | 字段、规则 | audit_results |
| `retrieve_evidence(query, kb)` | 查询、知识库 | citations |
| `create_review_ticket(result_id)` | 异常结果 | 复核任务 |
| `generate_control_table(task_id)` | 审核结果 | 控制表 |
| `record_bad_case(payload)` | 错误样本 | bad_cases |

### 20.5 Agent 职责

| Agent | 职责 | 不允许做的事 |
| --- | --- | --- |
| Intake Agent | 校验任务、文件格式、场景和上传完整性 | 不判断业务异常 |
| OCR Agent | 调用 OCR、保存页码和坐标、标记低质量页面 | 不修改 OCR 文本含义 |
| Classification Agent | 判断文档类型并给出理由 | 不直接抽取业务字段 |
| Extraction Agent | 按 Schema 抽取字段、保留证据 | 不编造缺失字段 |
| Linkage Agent | 归集同一业务链路 | 不忽略低置信度冲突 |
| Audit Agent | 调用 Rule Engine | 不绕过规则直接输出 pass/fail |
| Evidence Agent | 检索法规、案例、招股书、底稿依据 | 不把检索不到的依据写成结论 |
| Explanation Agent | 解释规则结果和证据 | 不改变规则判定 |
| Review Routing Agent | 根据严重程度、缺字段、低置信度分配人工复核 | 不自动确认高风险异常 |
| Report Agent | 生成控制表和异常清单 | 不隐藏失败规则 |

### 20.6 风险点

- 上游分类错误导致抽取和规则错误。
- Agent 跳过人工复核。
- Agent 重复执行造成结果不一致。
- 工具调用日志包含敏感原文。

### 20.7 验收标准

- agent_runs 和 agent_steps 记录完整。
- 工作流能从上传文件推进到报告生成。
- 失败步骤可查看错误并重试。
- 高风险和低置信度结果路由 Review Center。

---

## 21. Review Center人工复核模块

### 21.1 模块职责

Review Center 是人机协同核心模块，负责集中处理低置信度、缺字段、规则失败、高风险 warning、RAG 依据不足、Agent 失败和用户手动标记的复核项。

### 21.2 触发人工复核的条件

- 文档分类置信度低于阈值。
- 必填字段缺失。
- 字段抽取置信度低。
- OCR 页级置信度低。
- Rule Engine 输出 fail。
- Rule Engine 输出 high severity warning。
- 规则依赖字段缺失导致 need_review。
- RAG 检索不到依据但异常解释需要依据。
- Agent 步骤失败。
- 用户手动标记需要复核。

### 21.3 输入

- extracted_fields。
- audit_results。
- document_pages。
- RAG citations。
- agent_steps。
- 用户复核动作。

### 21.4 输出

- review_comments。
- 字段修正记录。
- audit_results.review_status。
- audit_logs。
- rerun rule request。
- Bad Case 候选。

### 21.5 复核动作

| 动作 | 说明 |
| --- | --- |
| 字段修正 | 修正 extracted_fields，并保留 before / after |
| 异常确认 | 将 audit_results.review_status 改为 confirmed |
| 驳回异常 | 标记 dismissed，并必须写明原因 |
| 要求重新抽取 | 重跑 Extraction Agent |
| 重新运行规则 | 字段修正后重新执行 Rule Engine |
| 添加复核意见 | 写入 review_comments |
| 转 Bad Case | 把错误样本写入 bad_cases |

### 21.6 状态流转

```text
need_review
  -> confirmed
  -> dismissed
  -> fixed
  -> re_extract_requested
  -> bad_case_created
```

### 21.7 业务规则

- 字段修正必须保留原值、修正值、修正人和时间。
- 驳回异常必须填写原因。
- 高风险异常不能自动通过。
- 字段修正后应支持重跑相关规则。
- 复核意见应随报告导出。
- 所有复核动作写入 audit_logs。

### 21.8 风险点

- 人工修正覆盖原始证据。
- 复核意见未进入报告。
- 高风险异常被错误自动关闭。
- 复核动作缺少审计留痕。

### 21.9 验收标准

- 能查看复核队列。
- 能查看字段证据、规则逻辑和 RAG 引用。
- 能修正字段并重跑规则。
- 能确认、驳回异常并写复核意见。
- 能转 Bad Case。

---

## 22. Report Center控制表与报告导出模块

### 22.1 模块职责

Report Center 负责将字段、规则结果、RAG 引用、人工复核意见和证据索引整理为控制表、异常清单、审核摘要和可下载文件。

### 22.2 输入

- extracted_fields。
- audit_results。
- review_comments。
- rag_citations。
- document_relations。
- control_table_rows。

### 22.3 输出

- Excel 控制表。
- CSV 数据表。
- PDF / Markdown 摘要。
- 异常清单。
- 证据索引。
- 报告导出记录。

### 22.4 Excel Sheet 设计

| Sheet | 内容 |
| --- | --- |
| Summary | 任务摘要、文档数量、异常数量、通过率 |
| Procurement Control Table | 采购穿行控制表 |
| Exceptions | 异常清单 |
| Field Corrections | 人工字段修正记录 |
| Evidence Index | 文件、页码、bbox、原文片段 |
| Rule Definitions | 本次使用规则版本 |

### 22.5 采购控制表字段

| 字段 | 说明 |
| --- | --- |
| task_no | 审核任务编号 |
| business_key | 业务归集键 |
| supplier_name | 供应商标准名称 |
| contract_no | 合同编号 |
| request_date | 申请日期 |
| signing_date | 合同日期 |
| receipt_date | 入库日期 |
| invoice_date | 发票日期 |
| voucher_date | 凭证日期 |
| payment_date | 付款日期 |
| item_summary | 品种摘要 |
| contract_qty | 合同数量 |
| receipt_qty | 入库数量 |
| invoice_qty | 发票数量 |
| contract_amount | 合同金额 |
| invoice_amount | 发票金额 |
| payment_amount | 付款金额 |
| time_check | 时间校验 |
| quantity_check | 数量校验 |
| amount_check | 金额校验 |
| name_check | 名称一致性 |
| item_check | 品种一致性 |
| tax_check | 含税/不含税 |
| missing_field_check | 缺字段 |
| overall_status | pass / warning / fail / need_review |
| evidence_refs | 证据页码和片段 |
| reviewer_comment | 复核意见 |

### 22.6 业务规则

- 控制表中每个异常必须追溯到 audit_results。
- 每个关键字段必须追溯到 extracted_fields。
- 人工复核意见必须随报告导出。
- 报告应标注数据来源和用途边界。

### 22.7 验收标准

- 可预览控制表。
- 可导出 xlsx 和 csv。
- 异常清单包含规则、证据和复核状态。
- 证据索引可定位到文件和页码。

---

## 23. Bad Case体系

### 23.1 模块职责

Bad Case 体系用于记录 OCR、分类、抽取、规则、RAG、Agent 和复核流程中的错误，并把错误转化为可复查、可归因、可修复、可回归的工程资产。

### 23.2 Bad Case 类型

| 类型 | 示例 |
| --- | --- |
| ocr_error | 金额识别错、日期漏识别、表格错列 |
| classification_error | 发票被识别成付款回单 |
| extraction_error | 供应商抽成采购方、税额抽成总金额 |
| rule_error | 分批付款被误判为金额不一致 |
| rag_error | 检索到无关法规或案例 |
| agent_error | 状态流转错误、重复运行、跳过复核 |
| review_dispute | 复核人认为提示不清晰或证据不足 |

### 23.3 Bad Case 字段

```json
{
  "case_id": "bc_001",
  "case_type": "rule_error",
  "task_id": "uuid",
  "document_id": "uuid",
  "title": "分批付款被误判为超付",
  "input_payload": {},
  "model_output": {},
  "expected_output": {},
  "root_cause": "Rule Engine 未按 business_key 累计付款",
  "fix_plan": "修改金额规则，按合同维度聚合付款回单",
  "status": "open",
  "severity": "high"
}
```

### 23.4 处理流程

```text
发现错误
  -> 记录 bad_cases
  -> 标注 expected_output
  -> 分析根因
  -> 修改 OCR / Prompt / Schema / Rule / RAG / Workflow
  -> 加入 evaluation dataset
  -> 运行回归评测
  -> verified 后关闭
```

### 23.5 验收标准

- 能创建、筛选、更新 Bad Case。
- 每个 Bad Case 有输入、输出、期望、根因和修复方案。
- Bad Case 能加入回归评测。
- 修复后能记录验证结果。

---

## 24. Evaluation Center评测体系

### 24.1 模块职责

Evaluation Center 是独立质量模块，负责管理测试集、执行评测、记录指标、展示失败样例，并支持 Bad Case 回归。

### 24.2 分类评测

| 指标 | 说明 |
| --- | --- |
| Accuracy | 文档类型识别准确率 |
| Macro F1 | 多类别均衡指标 |
| Low-confidence Rate | 低置信度进入复核比例 |

### 24.3 OCR 评测

| 指标 | 说明 |
| --- | --- |
| CER / WER | 字符或词错误率 |
| Table Structure Accuracy | 表格结构准确率 |
| Numeric Accuracy | 金额、日期、发票号等关键值准确率 |
| BBox Quality | 证据定位质量 |

### 24.4 字段抽取评测

| 指标 | 说明 |
| --- | --- |
| Field Precision | 抽取字段中正确比例 |
| Field Recall | 应抽字段中被抽出比例 |
| Field F1 | 综合指标 |
| Exact Match | 字段值完全匹配 |
| Numeric Tolerance Accuracy | 金额容忍范围准确率 |
| Source Accuracy | 页码和证据片段正确率 |

### 24.5 Rule Engine 评测

| 指标 | 说明 |
| --- | --- |
| Rule Accuracy | 规则输出与标注一致比例 |
| False Positive Rate | 误报率 |
| False Negative Rate | 漏报率 |
| Rule Coverage | 已覆盖规则数 / 目标规则数 |
| Explainability Rate | 异常是否包含证据和原因 |

### 24.6 RAG 评测

| 指标 | 说明 |
| --- | --- |
| Recall@K | 正确依据是否出现在前 K 条 |
| Citation Accuracy | 引用是否真实相关 |
| Groundedness | 回答是否被引用支持 |
| No-answer Accuracy | 检索不到时是否提示证据不足 |

### 24.7 Agent Workflow 评测

| 指标 | 说明 |
| --- | --- |
| Workflow Success Rate | 工作流成功率 |
| Step Failure Rate | 步骤失败率 |
| Human Review Routing Accuracy | 人工复核路由准确率 |
| State Transition Validity | 状态流转合法率 |
| Retry Recovery Rate | 重试恢复率 |

### 24.8 端到端采购穿行评测

| 指标 | 说明 |
| --- | --- |
| E2E Success Rate | 从上传到报告生成完整跑通比例 |
| Control Table Accuracy | 控制表字段准确率 |
| Exception Detection F1 | 异常识别 F1 |
| Evidence Completeness | 证据完整率 |
| Review Resolution Rate | 复核完成率 |

### 24.9 Bad Case 回归评测

| 指标 | 说明 |
| --- | --- |
| Regression Pass Rate | 历史 Bad Case 通过率 |
| Reopened Case Count | 修复后复发数量 |
| Fix Impact | 修复对其他样例的影响 |

### 24.10 测试集来源

- 公开法规、公开问询函、公开招股书。
- 使用公开资料和模拟底稿构建的采购链路样例。
- 手工构造异常样本，例如日期倒挂、金额超付、名称不一致。
- 脱敏或合成样例。

### 24.11 验收标准

- Evaluation Center 能展示评测结果。
- 评测结果记录模型、Prompt、规则版本和数据集名称。
- 失败样例能转 Bad Case。
- Bad Case 能进入回归集。

---

## 25. 开发阶段规划

### 阶段一：采购穿行 MVP

目标：

- 完成任务创建、文件上传、OCR、分类、字段抽取、采购穿行规则和控制表导出。

开发任务：

- 搭建 FastAPI、React、PostgreSQL 和基础目录。
- 实现 audit_tasks、documents、document_pages、extracted_fields、audit_rules、audit_results。
- 实现六类采购文件上传和 OCR。
- 实现文档分类和字段抽取。
- 实现采购穿行核心规则。
- 实现控制表预览和导出。

交付物：

- 可运行前后端。
- 采购穿行六类文件 Schema。
- 基础 Rule Engine。
- 采购控制表。

验收标准：

- 能创建采购穿行任务。
- 能上传六类文件并完成 OCR、分类、抽取。
- 能执行核心采购规则。
- 能导出控制表和异常清单。

### 阶段二：Review Center 与人工复核闭环

目标：

- 建立字段修正、异常确认、驳回异常、复核意见和审计留痕。

开发任务：

- 实现 review_comments 和 audit_logs。
- 实现复核队列。
- 实现字段修正和 before / after 留痕。
- 实现异常确认、驳回和重新运行规则。
- 将复核意见写入报告。

交付物：

- Review Center 页面。
- 复核 API。
- 审计日志。
- 规则重跑机制。

验收标准：

- 低置信度和规则异常能进入复核队列。
- 字段修正后可重跑规则。
- 复核意见可导出。
- 复核动作可审计。

### 阶段三：RAG 四库与证据检索

目标：

- 建立 regulation、inquiry_case、prospectus、workpaper 四类知识库。

开发任务：

- 实现 rag_documents、rag_chunks 和 pgvector。
- 实现知识库文档入库、切块和 embedding。
- 实现 metadata filter、Top-k 检索和引用展示。
- 将异常解释接入 RAG citations。

交付物：

- Knowledge Center。
- RAG 查询 API。
- citations 输出。
- RAG 评测样例。

验收标准：

- 四库可分别检索。
- 回答包含 citation。
- workpaper 与公开知识库隔离。
- 检索不到依据时能说明证据不足。

### 阶段四：Rule Engine 规则库扩展

目标：

- 将规则从硬编码升级为可配置、可版本化、可评测规则库。

开发任务：

- 完善 audit_rules 表和规则版本。
- 支持容忍差额、税率、别名表、品种映射。
- 增加分批到货、多发票、多付款、预付款、红冲等场景规则。
- 建立规则单元测试和规则评测。

交付物：

- Rule Center。
- 规则配置和版本。
- 规则测试集。

验收标准：

- 规则可启用/禁用。
- 规则参数可配置。
- 规则结果可复现。
- 规则评测结果可查看。

### 阶段五：Agent Workflow 受控编排

目标：

- 用状态机和工具调用编排审核流程。

开发任务：

- 实现 agent_runs 和 agent_steps。
- 实现状态机和工具白名单。
- 实现 Intake、OCR、Classification、Extraction、Linkage、Audit、Evidence、Review Routing、Report Agent。
- 实现失败重试和状态可视化。

交付物：

- Agent Workflow 服务。
- Agent 状态时间线。
- 失败重试机制。

验收标准：

- Agent 能从上传推进到报告生成。
- 每一步有状态、输入引用、输出引用和耗时。
- 高风险项进入 Review Center。
- Agent 不绕过 Rule Engine。

### 阶段六：销售穿行、函证、访谈、合同审核扩展

目标：

- 复用底层框架扩展更多金融文档审核场景。

开发任务：

- 新增销售穿行 Schema、规则和控制表。
- 新增函证字段和差异规则。
- 新增访谈字段和交叉验证规则。
- 新增合同条款抽取和审核规则。

交付物：

- 多场景任务类型。
- 扩展场景 Schema。
- 扩展规则。

验收标准：

- 每个扩展场景至少有基础端到端样例。
- 结果能进入 Review Center。
- 报告导出支持场景区分。

### 阶段七：Evaluation Center、Bad Case 与回归评测

目标：

- 建立覆盖 OCR、分类、抽取、规则、RAG、Agent 和端到端流程的评测体系。

开发任务：

- 建立 classification_set、ocr_set、extraction_set、rule_set、rag_set、agent_set、e2e_procurement_set。
- 实现评测脚本和 evaluation_results。
- 实现 Bad Case Center。
- 支持失败样例转 Bad Case。
- 支持回归评测。

交付物：

- Evaluation Center。
- Bad Case Center。
- 评测报告。
- 回归测试集。

验收标准：

- 每个核心模块有 smoke set。
- 评测结果包含指标和失败样例。
- Bad Case 可以回归验证。

### 阶段八：工程化、Docker、README 与演示数据

目标：

- 完成可复现、可交付、可验收的工程形态。

开发任务：

- 补齐 Docker Compose、`.env.example`、`.gitignore`。
- 整理 README、API 文档、数据库文档、规则文档、RAG 文档、Agent 文档、Review 文档和 Evaluation 文档。
- 准备公开资料和模拟底稿样例。
- 编写数据与安全说明。
- 补齐测试命令和评测命令。

交付物：

- Docker Compose。
- README。
- docs 文档集。
- 模拟样例数据。
- 最终验收记录。

验收标准：

- 新环境能按 README 启动。
- 不包含真实密钥和敏感数据。
- API 文档与实际接口一致。
- 文档覆盖项目边界、规则、RAG、Agent、Review、Evaluation 和安全。

---

## 26. README模板

```markdown
# FinancialAuditAI 金融文档智能审核平台

FinancialAuditAI 是基于 OCR、LLM、RAG、Rule Engine、Human Review、Agent Workflow、FastAPI、React 和 PostgreSQL 的金融文档智能审核平台，面向 IPO 底稿审核、券商投行底稿复核、银行科技金融合规审核和金融文档证据抽取场景。

## 项目简介

系统支持采购穿行、销售穿行、函证、访谈、合同审核、证据定位、人工复核、控制表导出、Bad Case 和 Evaluation Center。项目使用公开资料和模拟底稿构建样例，不包含真实敏感客户数据，不构成审计、法律或投资建议。

## 项目边界

- 不是 OCR Demo。
- 不是普通 RAG 问答系统。
- 不替代专业判断。
- 不输出无证据结论。
- 指标只填写真实评测结果。

## 技术栈

- Frontend: React, TypeScript, Ant Design
- Backend: FastAPI, Pydantic, SQLAlchemy
- Database: PostgreSQL, pgvector
- AI: OCR Provider, LLM Provider, Embedding, RAG
- Workflow: Agent Workflow with state machine and tool calls
- Test: pytest
- Deployment: Docker Compose

## 核心功能

- 任务中心
- 文档上传
- OCR 识别
- 文档分类
- 字段抽取
- 证据定位
- 采购穿行 MVP
- 销售穿行扩展
- 函证模块
- 访谈模块
- 合同审核模块
- Rule Engine
- RAG 知识库
- Agent Workflow
- Review Center
- 控制表导出
- Bad Case
- Evaluation Center

## 系统架构

说明 Frontend、FastAPI、Application Services、AI Layer、PostgreSQL、pgvector、File Storage、Evaluation Datasets。

## 本地运行

```bash
docker compose up --build
```

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

## 数据与安全说明

- 使用公开资料和模拟底稿。
- 不提交真实密钥、真实敏感底稿、上传文件、OCR 中间文件和向量索引。
- `.env` 不进入 Git，只提交 `.env.example`。
- 模型输出必须可追溯到证据。
- 人工复核保留最终判断。

## API说明

- Task APIs
- Document APIs
- OCR / Classification / Extraction APIs
- Audit / Rule APIs
- RAG APIs
- Agent Workflow APIs
- Review APIs
- Report APIs
- Bad Case APIs
- Evaluation APIs

## Rule Engine说明

Rule Engine 覆盖时间、数量、金额、名称、品种、缺字段、多品种、含税/不含税规则。规则支持版本、参数、启用状态、证据输出和评测。

## RAG知识库说明

RAG 分为 regulation、inquiry_case、prospectus、workpaper 四库。RAG 只提供依据检索和引用，不替代规则判断和人工复核。

## Agent Workflow说明

Agent Workflow 采用状态机 + 工具调用 + 规则约束 + 人工复核路由。Agent 不绕过 Rule Engine，不自动确认高风险异常。

## Review Center说明

Review Center 支持字段修正、异常确认、驳回异常、复核意见、重新运行规则、审计留痕和转 Bad Case。

## Evaluation说明

Evaluation Center 覆盖分类、OCR、字段抽取、Rule Engine、RAG、Agent Workflow、端到端采购穿行和 Bad Case 回归评测。

## 后续规划

- 扩展销售穿行、函证、访谈和合同审核样例。
- 增强规则库版本管理和规则评测。
- 增强 RAG 四库更新机制。
- 增加异步任务队列和更完整的权限控制。
- 扩展 Evaluation Center 指标看板。
```

---

## 27. 最终验收标准

### 27.1 功能验收

| 模块 | 验收标准 |
| --- | --- |
| 任务中心 | 可创建、查询、更新审核任务 |
| 文档上传 | 支持 PDF、图片和常见文档格式，校验大小和类型 |
| OCR | 输出页码、文本、bbox、表格块和置信度 |
| 文档分类 | 能识别采购六类文件并输出置信度和理由 |
| 字段抽取 | 按 Schema 抽取字段和 line_items，保留来源证据 |
| 采购穿行 | 打通申请、合同、入库、发票、凭证、付款链路 |
| 扩展模块 | 销售、函证、访谈、合同审核有基础 Schema 和规则 |
| 控制表导出 | 可导出控制表、异常清单和证据索引 |

### 27.2 工程验收

- FastAPI 后端可启动。
- React 前端可启动。
- PostgreSQL 迁移可运行。
- API 响应 Schema 稳定。
- 业务逻辑在 Service 层。
- OCR、LLM、Embedding Provider 可替换。
- 长任务有状态记录。
- 错误响应统一。
- 单元测试覆盖规则和关键 API。

### 27.3 数据库验收

- users、roles、user_roles 可支持 RBAC。
- audit_tasks、documents、document_pages、extracted_fields 支持文档处理链路。
- audit_rules、audit_results 支持规则版本和结果记录。
- review_comments、audit_logs 支持人工复核留痕。
- reports、control_table_rows 支持导出。
- rag_documents、rag_chunks 支持四库检索。
- agent_runs、agent_steps 支持工作流追踪。
- bad_cases、evaluation_results 支持质量闭环。
- model_invocations 支持模型调用审计。

### 27.4 Rule Engine验收

- 规则可配置、可版本化、可启用/禁用。
- 支持时间、数量、金额、名称、品种、缺字段、多品种、含税/不含税。
- 每条规则结果包含 status、severity、message、actual_value、expected_value 和 evidence。
- 规则可单元测试。
- 规则评测结果可查看。

### 27.5 RAG验收

- regulation、inquiry_case、prospectus、workpaper 四库分离。
- chunk 包含标题、章节、页码、metadata 和向量。
- 检索结果包含 score 和引用片段。
- 回答包含 citations 和 limitations。
- 无依据问题能说明证据不足。

### 27.6 Agent Workflow验收

- 状态机覆盖 OCR、分类、抽取、规则、检索、复核、报告。
- 每次运行记录 agent_runs 和 agent_steps。
- 工具调用白名单可控。
- 失败步骤可重试。
- 高风险和低置信度事项进入 Review Center。

### 27.7 Review Center验收

- 能查看复核队列。
- 能查看字段证据、规则逻辑和 RAG 引用。
- 能修正字段并保留 before / after。
- 能确认或驳回异常。
- 能写复核意见。
- 能重跑规则。
- 能转 Bad Case。
- 所有动作写入 audit_logs。

### 27.8 Evaluation Center验收

- 支持分类评测。
- 支持 OCR 评测。
- 支持字段抽取评测。
- 支持 Rule Engine 评测。
- 支持 RAG 评测。
- 支持 Agent Workflow 评测。
- 支持端到端采购穿行评测。
- 支持 Bad Case 回归评测。
- 评测结果记录数据集、模型、Prompt、规则版本和指标。

### 27.9 安全与隐私验收

- API Key 不提交。
- `.env` 不提交。
- 上传文件、OCR 中间文件、导出报告和向量索引默认不提交。
- 样例数据使用公开资料、模拟底稿或脱敏数据。
- 日志不输出完整敏感底稿。
- 报告标注用途边界。
- 支持用户权限控制和审计日志。

### 27.10 文档验收

- README 包含项目简介、项目边界、技术栈、核心功能、系统架构、本地运行、数据与安全说明、API、Rule Engine、RAG、Agent Workflow、Review Center、Evaluation 和后续规划。
- docs 包含架构、API、数据库、规则、RAG、Agent、Review、Evaluation 和安全说明。
- 主开发手册保持项目化、工程化、可执行、可验收。
- 展示性材料与主开发规格分离。

---

本手册作为 FinancialAuditAI 金融文档智能审核平台最终版项目开发执行规格，后续开发应围绕“证据可定位、规则可复现、结论可复核、流程可追踪、知识可引用、错误可回归、数据可控制”的目标展开。
