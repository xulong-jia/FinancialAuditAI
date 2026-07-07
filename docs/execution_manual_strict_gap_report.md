# FinancialAuditAI 执行手册严格缺口报告

生成日期：2026-07-06

最高标准来源：`/Users/jiaxulong/Documents/FinancialAuditAI/FinancialAuditAI_最终版项目开发执行手册.md`。

结论：**部分满足执行手册，仍有阻塞差距**。

## 本轮已修复

| 项目 | 状态 | 代码证据 | 测试证据 |
| --- | --- | --- | --- |
| OCR Provider 配置路径 | 已补齐 HTTP Provider 基础闭环 | `backend/app/core/config.py`, `backend/app/services/ocr_service.py`, `.env.example` | `backend/tests/test_ocr_api.py::test_http_ocr_provider_preserves_provider_confidence` |
| Azure Document Intelligence OCR Provider | 已补齐 `azure-document-intelligence` / `azure` / `azure-document-intelligence-layout` adapter；使用 Azure Document Intelligence REST API `2024-11-30`、`prebuilt-layout`，将 Azure `analyzeResult.pages` / lines / words / tables 正规化为 `DocumentPage` / `ocr_blocks` / `table_blocks` / confidence / bbox | `backend/app/services/ocr_service.py`, `backend/app/core/config.py`, `.env.example` | `backend/tests/test_ocr_api.py::test_azure_document_intelligence_provider_normalizes_layout`, `backend/tests/test_ocr_api.py::test_azure_document_intelligence_error_redacts_key` |
| Azure OCR readiness | 已补齐 Azure Provider configured/blocked/ready 状态；`RUN_PROVIDER_INTEGRATION=1` 使用 `GET documentModels/{model}` 轻量探测，不上传真实 OCR 文件 | `backend/app/services/provider_readiness_service.py` | `backend/tests/test_health_api.py::test_provider_readiness_azure_ocr_get_model_probe` |
| Azure OCR 真实图片 E2E | 已用公开 receipt 样本完成本地真实 Azure OCR E2E；文件位于 `local_storage/manual_acceptance_files/ocr/azure_ocr_smoke_receipt.jpg`，未提交 Git；验证 `page raw_text`、`ocr_blocks`、bbox、confidence、`table_blocks`、`ocr_engine` 写入 | 本地 `.env` 配置 Azure Document Intelligence；`.env` 未提交，API key 未记录 | 手工验收结果：`page_count=1`、`ocr_blocks_count=73`、`blocks_with_bbox_count=73`、`blocks_with_confidence_count=49`、`table_blocks_count=3`、`average_block_confidence=0.9786`、`ocr_engine=azure-document-intelligence:prebuilt-layout` |
| Evaluation manual OCR dataset | 已支持 `evals/datasets/<dataset>/dataset_manifest.json` 加载 OCR dataset；OCR runner 会复用项目 OCR service，并按 expected 断言 raw_text、page_count、ocr_blocks、bbox、confidence、table_blocks；非生产 manifest 会标记 `non_production_manual_acceptance` | `backend/app/services/evaluation_service.py`, `docs/evaluation.md`, `evals/datasets/manual_acceptance/dataset_manifest.json`, `evals/datasets/manual_acceptance/ocr.json` | `backend/tests/test_quality_api.py::test_manual_acceptance_ocr_manifest_runs_expected_assertions`, `backend/tests/test_quality_api.py::test_manual_acceptance_ocr_file_path_is_restricted` |
| Evaluation manual OCR 真实运行 | 已成功运行 `manual_acceptance` OCR dataset-driven evaluation；`sample_count=1`、`failed_cases=[]`、`ocr_sample_pass_rate=1.0`、text/page/block/bbox/confidence/table requirement accuracy 均为 `1.0`，`blocked_external_dependency_count=0`；结果标记 `dataset_kind=non_production_manual_acceptance`、`source_type=public`、`is_production_evaluation=false` | 本地 `.env` 和 API key 未提交；`local_storage` receipt 图片未提交 | 手工运行：`eval_type=ocr`, `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json`, `model_name=azure-document-intelligence:prebuilt-layout` |
| Evaluation manual classification dataset | 已支持 `evals/datasets/<dataset>/dataset_manifest.json` 加载 `classification.json`；runner 复用现有 text-sample evaluator，按 `sample.input.text` / `sample.input.filename` 推断 doc_type，并与 `sample.expected.doc_type` 对比；synthetic 非生产 manifest 不会标记为 production evaluation | `backend/app/services/evaluation_service.py`, `docs/evaluation.md`, `evals/datasets/manual_acceptance/classification.json` | `backend/tests/test_quality_api.py::test_manual_acceptance_classification_manifest_runs_text_samples` |
| Evaluation manual classification 真实运行 | 已成功运行 `manual_acceptance` classification dataset-driven evaluation；`sample_count=6`、`failed_cases=[]`、`accuracy=1.0`、`macro_f1=1.0`、`low_confidence_rate=0.0`；结果标记 `dataset_kind=non_production_manual_acceptance`、`source_type=synthetic`、`dataset_source=evals/datasets/manual_acceptance/classification.json`、`is_dataset_driven=true`、`is_production_evaluation=false` | 无 secret；该 dataset 为 synthetic 六样本，不是生产级完整 Evaluation | 手工运行：`eval_type=classification`, `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json` |
| Evaluation manual extraction dataset | 已支持 `evals/datasets/<dataset>/dataset_manifest.json` 加载 `extraction.json`；runner 使用 deterministic text extraction，不调用真实 LLM，按 `expected.fields` 校验字段存在、`value`、`value_normalized`、`item_lines`、`source_page`、`source_text`、可选 `source_bbox`；synthetic 非生产 manifest 不会标记为 production evaluation | `backend/app/services/evaluation_service.py`, `docs/evaluation.md`, `evals/datasets/manual_acceptance/extraction.json` | `backend/tests/test_quality_api.py::test_manual_acceptance_extraction_manifest_runs_text_samples` |
| Evaluation manual extraction 真实运行 | 已成功运行 `manual_acceptance` extraction dataset-driven evaluation；`sample_count=1`、`failed_cases=[]`、`extraction_sample_pass_rate=1.0`、field/normalized/item/source_page/source_text accuracy 均为 `1.0`，`source_bbox_coverage=0.0`；结果标记 `dataset_kind=non_production_manual_acceptance`、`source_type=synthetic`、`dataset_source=evals/datasets/manual_acceptance/extraction.json`、`is_dataset_driven=true`、`is_production_evaluation=false` | 无 secret；该 dataset 为 synthetic 单样本，`require_source_bbox=false`，不是生产级完整 Evaluation，也不是完整 uploaded-document DB workflow | 手工运行：`eval_type=extraction`, `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json` |
| Evaluation manual rule dataset | 已支持 `evals/datasets/<dataset>/dataset_manifest.json` 加载 `rule.json`；runner 对 `PROC_AMOUNT_001` 使用 synthetic deterministic 金额一致性检查，按 `rule_id`、`status`、`severity`、`must_include_evidence` 断言；fail 时生成不含 DB evidence id 的证据摘要；synthetic 非生产 manifest 不会标记为 production evaluation | `backend/app/services/evaluation_service.py`, `docs/evaluation.md`, `evals/datasets/manual_acceptance/rule.json` | `backend/tests/test_quality_api.py::test_manual_acceptance_rule_manifest_runs_amount_samples` |
| Evaluation manual rule 真实运行 | 已成功运行 `manual_acceptance` rule dataset-driven evaluation；`sample_count=2`、`failed_cases=[]`、`rule_sample_pass_rate=1.0`、`rule_status_accuracy=1.0`、`rule_severity_accuracy=1.0`、`rule_evidence_coverage=1.0`、`rule_accuracy=1.0`、false positive / false negative rate 均为 `0.0`、`explainability_rate=0.5`；结果标记 `dataset_kind=non_production_manual_acceptance`、`source_type=synthetic`、`dataset_source=evals/datasets/manual_acceptance/rule.json`、`is_dataset_driven=true`、`is_production_evaluation=false` | 无 secret；该 dataset 为 synthetic 两样本，`explainability_rate=0.5` 是预期，因为只有 fail 样本要求 evidence；不是生产级完整 Evaluation，也不是完整 DB task/document/field Rule Engine workflow | 手工运行：`eval_type=rule`, `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json` |
| Evaluation manual RAG dataset | 已支持 `evals/datasets/<dataset>/dataset_manifest.json` 加载 `rag.json`；runner 使用 sample 内联 `input.documents` 做 deterministic lexical retrieval，按 `answer_must_contain`、`must_have_citation`、`expected_citation_document_id`、`no_answer`、`expected_status` 断言；citation `document_id` 只能来自 sample document，不调用真实 Provider | `backend/app/services/evaluation_service.py`, `docs/evaluation.md`, `evals/datasets/manual_acceptance/rag.json` | `backend/tests/test_quality_api.py::test_manual_acceptance_rag_manifest_runs_inline_documents` |
| Evaluation manual RAG 真实运行 | 已成功运行 `manual_acceptance` RAG dataset-driven evaluation；`sample_count=2`、`failed_cases=[]`、`rag_sample_pass_rate=1.0`、`answer_text_accuracy=1.0`、`citation_presence_accuracy=1.0`、`citation_document_accuracy=1.0`、`no_answer_accuracy=1.0`、`recall_at_k=1.0`、`citation_accuracy=1.0`、`groundedness=1.0`；结果标记 `dataset_kind=non_production_manual_acceptance`、`source_type=synthetic`、`dataset_source=evals/datasets/manual_acceptance/rag.json`、`is_dataset_driven=true`、`is_production_evaluation=false` | 无 secret；该 dataset 为 synthetic 两样本，使用 inline-document runner，不调用真实 embedding/rerank/answer Provider；不是生产级完整 Evaluation，也不是完整 persistent vector-store / 四库隔离 / workpaper scope RAG workflow | 手工运行：`eval_type=rag`, `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json` |
| OCR Provider 配置展示 | 已补齐 Admin Center 展示 | `backend/app/api/router.py`, `frontend/src/types/api.ts`, `frontend/src/pages/AdminCenterPage.tsx` | `npm run build` |
| Embedding Provider 独立配置 | 已补齐 endpoint/key/model 配置 | `backend/app/core/config.py`, `backend/app/services/rag_service.py`, `.env.example` | `backend/tests/test_final_gap_closure_api.py::test_real_embedding_provider_requests_configured_vector_dimensions` |
| Embedding 维度兼容 | 已在真实 provider 请求中显式传入 32 维 | `backend/app/services/rag_service.py` | 同上 |
| Agent 失败 Bad Case 闭环 | 已补齐 `record_bad_case` 工具步骤和 task-scoped Bad Case | `backend/app/services/agent_service.py` | `backend/tests/test_agent_workflow_api.py::test_failed_step_retry_records_retry_step` |
| OpenAI-compatible LLM Provider 路径验证 | 已覆盖 classify / extract / rerank / answer / explain 的安全 mock HTTP 路径 | `backend/app/services/llm_provider.py` | `backend/tests/test_llm_provider_paths_api.py` |
| RAG Provider citation JSON 边界 | 已修复 UUID citation 无法序列化到真实 Provider prompt 的问题 | `backend/app/services/llm_provider.py` | `backend/tests/test_llm_provider_paths_api.py::test_rag_rerank_answer_and_rule_explain_use_configured_llm_provider` |
| Viewer RBAC 数据库口径 | 已移除 migration seed/update 中的 viewer `read_all`，并新增 head migration 修正已迁移数据库 | `backend/alembic/versions/0014_rbac_users_roles.py`, `backend/alembic/versions/0019_quality_audit_contract.py`, `backend/alembic/versions/0020_final_gap_role_matrix.py`, `backend/alembic/versions/0024_viewer_role_scope.py` | `cd backend && ./.venv/bin/alembic upgrade head`, `backend/tests/test_auth_rbac_security_api.py::test_default_role_permissions_match_execution_matrix_baseline` |
| Review actor UUID 口径 | 已为字段修正和异常复核补齐服务端注入的用户 UUID FK，并保留字符串名称作为显示兼容字段 | `backend/app/models/extracted_field.py`, `backend/app/models/audit_result.py`, `backend/app/services/review_service.py`, `backend/alembic/versions/0025_review_actor_user_refs.py` | `backend/tests/test_review_api.py::test_field_correction_preserves_source_and_writes_before_after_log`, `backend/tests/test_review_api.py::test_confirm_marks_result_reviewed`, `backend/tests/test_review_api.py::test_review_queue_and_comments_api` |
| 测试配置与真实 Provider 验证隔离 | 普通 pytest 通过 `TESTING=true` 强制 deterministic/local/fallback provider；真实 Provider readiness/integration 改为专门入口 | `backend/app/core/config.py`, `backend/tests/conftest.py`, `backend/app/services/provider_readiness_service.py`, `scripts/provider_readiness.py` | `backend/tests/test_health_api.py::test_pytest_config_forces_deterministic_providers`, `backend/tests/test_health_api.py::test_provider_readiness_is_sanitized_and_non_integrating_by_default` |
| Agent 工具角色职责合同 | 已在每个 `agent_steps.input_payload` 记录 `agent_role` 和 `must_not` 约束 | `backend/app/services/agent_service.py` | `backend/tests/test_agent_workflow_api.py::test_agent_run_creates_steps_and_report_without_bypassing_rule_engine` |
| 前端权限合同测试 | 已新增无新依赖的 `node --test` 权限合同测试 | `frontend/package.json`, `frontend/tests/permission-contract.test.mjs` | `cd frontend && npm test` |
| PDF 报告证据/复核/用途边界输出 | 已改为全列换行输出并覆盖 PDF 内容测试 | `backend/app/services/report_service.py` | `backend/tests/test_report_api.py::test_control_table_report_generates_pdf_with_evidence_review_and_boundary` |
| 规则证据链 `field_id` | 已在 `audit_results.evidence.refs` 和报告 Evidence Index 的 audit_result 行补齐字段 ID | `backend/app/services/rule_engine_service.py`, `backend/app/services/report_service.py` | `backend/tests/test_rule_engine_api.py::test_amount_rule_fails_on_overpayment_and_supports_many_invoices_payments`, `backend/tests/test_report_api.py::test_report_xlsx_exports_exceptions_evidence_and_field_corrections` |
| `model_invocations` 类型口径 | 已对齐执行手册主要口径 | `backend/app/services/classification_service.py`, `backend/app/services/extraction_service.py`, `backend/app/services/rag_service.py` 使用 `classify` / `extract` / `embed` / `rerank` / `answer` | `backend/tests/test_final_gap_closure_api.py::test_model_invocations_are_recorded_for_rag_query` |
| OCR 调用留痕 | 已补齐成功/失败路径 | `backend/app/services/ocr_service.py` 写入 `invocation_type="ocr"`、`latency_ms`、`error`、`cost_estimate` | `backend/tests/test_ocr_api.py::test_pdf_ocr_extracts_pages_in_order`, `backend/tests/test_ocr_api.py::test_ocr_failure_does_not_hide_task_or_document` |
| LLM Provider 调用元数据 | 已补齐真实返回路径 | `backend/app/services/llm_provider.py` 从 OpenAI-compatible 响应读取 `usage`，记录真实 `latency_ms`，不伪造 token/cost | `backend/tests/test_classification_api.py`, `backend/tests/test_extraction_api.py` |
| RAG 调用留痕 | 已补齐 `embed` / `rerank` / `answer` 耗时和 schema 信息 | `backend/app/services/rag_service.py` | `backend/tests/test_final_gap_closure_api.py::test_model_invocations_are_recorded_for_rag_query` |
| 异常解释 explain 路径 | 已补齐可配置 Provider 与 fallback 留痕 | `backend/app/services/llm_provider.py`, `backend/app/services/rule_engine_service.py` | `backend/tests/test_final_gap_closure_api.py::test_task_run_reports_rag_evidence_retrieval_for_review_items` |

## 当前验证记录

| 命令 | 结果 |
| --- | --- |
| `python3 -m json.tool docs/project_status.json > /tmp/project_status_validated.json` | PASS |
| `python3 scripts/danger_check.py` | PASS |
| `docker compose config` | PASS |
| `docker compose up -d postgres` | PASS |
| `docker compose ps` | PASS, PostgreSQL healthy |
| `cd backend && ./.venv/bin/alembic upgrade head` | PASS |
| `cd backend && ./.venv/bin/python -m pytest -q` | PASS, 173 passed, 5 warnings |
| `cd frontend && npm test` | PASS, 4 tests |
| `cd frontend && npm run build` | PASS, Vite chunk-size warning only |
| `git diff --check` | PASS |

## 剩余 Critical / High / Medium 缺口

### Critical

| 编号 | 模块 | 缺口 |
| --- | --- | --- |
| C-01 | 外部真实验收数据 | 代码已支持数据集驱动 Evaluation，但仓库不能包含真实客户/生产标注数据；真实数据集验收仍属于 `blocked_external_dependency`。 |
| C-02 | 外部 Provider 验收 | OCR/LLM/RAG Provider 均不能在仓库内提交真实 API key；真实端点、密钥和真实脱敏样本未提供前，外部 Provider 端到端验收属于 `blocked_external_dependency`。 |

### High

| 编号 | 模块 | 缺口 |
| --- | --- | --- |
| - | - | 当前无新增 High 代码缺口；外部真实数据/Provider 验收见 Critical `blocked_external_dependency`，质量和测试差距见 Medium。 |

### Medium

| 编号 | 模块 | 缺口 |
| --- | --- | --- |
| M-01 | Evaluation | 数据集驱动入口已存在；manual acceptance OCR dataset runner 已支持真实 OCR 样本断言，classification text-sample dataset runner 已支持 synthetic doc_type 断言，extraction text-sample dataset runner 已支持 synthetic invoice 字段断言，rule dataset runner 已支持 `PROC_AMOUNT_001` synthetic deterministic 断言，RAG dataset runner 已支持 synthetic inline-document citation/no-answer 断言；classification/extraction/rule 完整 DB workflow、RAG persistent vector-store/workpaper scope、Agent / E2E / regression 尚未完成同等 dataset 化，真实 RAG groundedness、真实 Agent E2E 评测仍依赖外部标注集和真实 Provider 配置。 |
| M-02 | Report | xlsx/csv/markdown/pdf 均存在；PDF 已输出 Summary、异常、证据索引、复核意见和用途边界；audit_result 证据行已含 `field_id`。Azure OCR 真实图片已验证 bbox/confidence/table_blocks 写入，但字段抽取 `source_bbox` 传递和报告 evidence index 联动尚未用该真实样本验证。 |
| M-03 | Review | 字段修正和异常复核已补服务端用户 UUID FK；历史 `actor_name` / `reviewed_by` / `corrected_by` 字符串字段仅保留为显示兼容口径。 |
| M-04 | Frontend tests | 已有权限合同自动化测试；仍无浏览器级 E2E/交互测试。 |

## fallback / synthetic / demo 状态

| 类型 | 当前状态 | 是否仍影响完全满足 |
| --- | --- | --- |
| deterministic classification fallback | 默认未配置 Provider 时仍存在；OpenAI-compatible provider path 已测 | 是，直到真实/本地 Provider 配置完成 |
| regex extraction fallback | 默认未配置 Provider 时仍存在；OpenAI-compatible provider path 已测 | 是，直到真实/本地 Provider 配置完成 |
| PyMuPDF OCR confidence unavailable | 默认本地路径仍存在 warning；Azure Document Intelligence / HTTP OCR Provider 可保留真实 confidence、bbox、table_blocks | 默认路径仍影响完全满足；Azure 真实调用依赖本地 `.env` 和 Azure key |
| deterministic/local RAG embedding/rerank/answer | 默认未配置 Provider 时仍存在；embedding/rerank/answer provider path 已测 | 是，直到真实/本地 Provider 完成验收 |
| explain deterministic fallback | 默认未配置 Provider 时仍 fallback；OpenAI-compatible explain provider path 已测 | 是，直到真实/本地 Provider 完成验收 |
| agent failure bad case | 失败步骤已自动进入 `agent` Bad Case，重试会保留独立记录 | 不再作为 Bad Case 闭环缺口 |
| built-in sample Evaluation | 保留为 smoke，不作为最终评测证据 | 仍影响真实验收 |
| demo seed samples | 仍保留 | 不可作为完全满足证据 |
| external real/desensitized Evaluation dataset | 已支持 JSON 读取路径 | 需要用户提供真实/脱敏标注数据才能最终验收 |
| manual acceptance OCR dataset | 已支持 manifest + `ocr.json`；真实 OCR 结果由 OCR provider 产生，不伪造；当前 manifest `is_production_evaluation=false` | 只覆盖 OCR，不代表 Evaluation Center 完全满足 |
| manual acceptance classification dataset | 已支持 manifest + `classification.json` 并已跑通；当前样本为 synthetic text sample，使用现有 text-sample evaluator 对比 `expected.doc_type` | 只覆盖分类文本样本，不代表完整 document workflow 或生产级 Evaluation |
| manual acceptance extraction dataset | 已支持 manifest + `extraction.json`；当前样本为 synthetic text sample，使用 deterministic extraction 对比字段和 source traceability，不调用真实 LLM | 只覆盖抽取文本样本，不代表完整 uploaded-document DB workflow 或生产级 Evaluation |
| manual acceptance rule dataset | 已支持 manifest + `rule.json`；当前样本为 synthetic deterministic `PROC_AMOUNT_001` amount check，不调用完整 DB Rule Engine workflow | 只覆盖规则文本字段样本，不代表完整 task/document/field Rule Engine workflow 或生产级 Evaluation |
| manual acceptance RAG dataset | 已支持 manifest + `rag.json`；当前样本为 synthetic inline-document retrieval，使用 deterministic lexical matching 断言 citation/no-answer，不调用真实 embedding/rerank/answer Provider | 只覆盖内联文档 RAG 样本，不代表完整 persistent vector-store、四库隔离、workpaper scope 或生产级 Evaluation |

## Provider 测试隔离与 readiness

- 普通 `pytest` 启动时强制 `ENVIRONMENT=test` / `TESTING=true`，并固定使用 `deterministic-fallback`、`deterministic-local`、`pymupdf-local`，不读取本地 `.env` 中真实 Provider key 作为单元测试配置。
- 本地 `.env` 可以保存真实 Provider 配置，但 `.env` 不提交；普通单元测试不会因为 `.env` 中存在真实 `LLM_PROVIDER` / `LLM_API_KEY` 而触发外部调用。
- Provider readiness 使用专门入口：`python3 scripts/provider_readiness.py` 或 `GET /api/v1/provider-readiness`。
- OpenAI-compatible readiness 支持 `LLM_API_MODE=auto` / `responses` / `chat_completions`；`auto` 对 `gpt-5*` readiness 使用 Responses API，其余默认兼容旧 `/chat/completions` provider。
- 真实网络 integration 只能显式设置 `RUN_PROVIDER_INTEGRATION=1` 后触发；无 key 或 endpoint 时状态为 `blocked_external_dependency`，不能声明 fully satisfied。
- readiness 输出只包含 provider/model 和 `api_url_status` / `api_key_status`，不得输出 API key。
- 2026-07-06 本地 OpenAI-compatible readiness 已通过真实验证：普通 readiness 显示 LLM / embedding / RAG answer / RAG rerank 为 configured；`RUN_PROVIDER_INTEGRATION=1` 显示 LLM / embedding / RAG answer / RAG rerank 为 ready。`.env` 未提交，API key 未记录。普通 pytest 仍隔离真实 Provider；当前结果为 173 passed / 5 warnings。
- Azure Document Intelligence OCR adapter 已实现；真实 readiness 依赖本地 `.env` 中 `OCR_PROVIDER=azure-document-intelligence`、`OCR_API_URL`、`OCR_API_KEY`、`OCR_MODEL=prebuilt-layout`，并通过显式 `RUN_PROVIDER_INTEGRATION=1` 触发轻量 model probe。OCR confidence、bbox、table_blocks 必须来自 Azure 原始响应，不得伪造；无 Azure key/endpoint 时仍属于 `blocked_external_dependency`。
- Azure OCR readiness 已通过；Azure OCR 真实图片 E2E 已通过：Provider 为 `azure-document-intelligence`，model 为 `prebuilt-layout`，API version 为 `2024-11-30`。公开 receipt 样本位于 `local_storage/manual_acceptance_files/ocr/azure_ocr_smoke_receipt.jpg`，未提交 Git；raw_text 前 300 字符确认包含商户名、地址、电话、订单号、明细、subtotal、tax、total、日期时间。`.env` 未提交，API key 未记录，未记录完整 Azure 原始响应。
- Azure 真实图片 E2E 仍未覆盖 PDF 多页、复杂表格、字段抽取 `source_bbox` 传递、报告 evidence index 联动；这些不能由 fallback/synthetic 结果替代。
- Evaluation Center 已开始支持 manual acceptance OCR dataset、classification text-sample dataset、extraction text-sample dataset、rule deterministic dataset 和 RAG inline-document dataset，路径为 `evals/datasets/manual_acceptance/dataset_manifest.json`、`ocr.json`、`classification.json`、`extraction.json`、`rule.json`、`rag.json`。当前只实现 OCR dataset runner、classification text-sample runner、extraction synthetic text-sample runner、`PROC_AMOUNT_001` synthetic rule runner 和 synthetic inline-document RAG runner；RAG persistent vector-store/workpaper scope、Agent / E2E / regression 仍待同等 dataset 化，不能据此声称 Evaluation Center 完全满足执行手册。
- Manual OCR dataset-driven evaluation 已真实跑通，但它是 public single-sample non-production manual acceptance；limitations 明确记录 `Dataset kind is non_production_manual_acceptance` 和 `Sample count is 1`，不能作为生产级完整 Evaluation 结论。
- Manual classification dataset-driven evaluation 已跑通，但它是 synthetic six-sample non-production manual acceptance；limitations 明确记录 `Dataset kind is non_production_manual_acceptance` 和 `Sample count is 6`，不能作为生产级完整 Evaluation 结论。
- Manual extraction dataset-driven evaluation 已跑通，但它是 synthetic single-sample non-production manual acceptance；`source_bbox_coverage=0.0` 是预期结果，因为该 text-only sample 设置 `require_source_bbox=false`。它不能作为生产级完整 Evaluation 或完整 uploaded-document DB workflow 结论。
- Manual rule dataset-driven evaluation 已跑通，但它是 synthetic two-sample non-production manual acceptance；`explainability_rate=0.5` 是预期结果，因为只有 fail 样本要求 evidence。它不能作为生产级完整 Evaluation 或完整 DB task/document/field Rule Engine workflow 结论。
- Manual RAG dataset-driven evaluation 已跑通，但它是 synthetic two-sample non-production manual acceptance；真实 embedding / RAG answer / RAG rerank Provider readiness 已单独通过，本 runner 不调用真实 Provider。它不能作为生产级完整 Evaluation 或完整 persistent vector-store / 四库隔离 / workpaper scope RAG workflow 结论。
- Azure Document Intelligence 可使用 F0 免费层进行学习和小规模验证，但免费层页数和速率有限，不能替代最终真实样本验收。

## 下一轮最高优先级

1. 浏览器级 E2E/交互测试能力。
2. LLM/RAG Provider 真实端到端验收在安全配置下完成。
