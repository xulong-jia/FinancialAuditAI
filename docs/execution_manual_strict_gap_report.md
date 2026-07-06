# FinancialAuditAI 执行手册严格缺口报告

生成日期：2026-07-06

最高标准来源：`/Users/jiaxulong/Documents/FinancialAuditAI/FinancialAuditAI_最终版项目开发执行手册.md`。

结论：**部分满足执行手册，仍有阻塞差距**。

## 本轮已修复

| 项目 | 状态 | 代码证据 | 测试证据 |
| --- | --- | --- | --- |
| OCR Provider 配置路径 | 已补齐 HTTP Provider 基础闭环 | `backend/app/core/config.py`, `backend/app/services/ocr_service.py`, `.env.example` | `backend/tests/test_ocr_api.py::test_http_ocr_provider_preserves_provider_confidence` |
| OCR Provider 配置展示 | 已补齐 Admin Center 展示 | `backend/app/api/router.py`, `frontend/src/types/api.ts`, `frontend/src/pages/AdminCenterPage.tsx` | `npm run build` |
| Embedding Provider 独立配置 | 已补齐 endpoint/key/model 配置 | `backend/app/core/config.py`, `backend/app/services/rag_service.py`, `.env.example` | `backend/tests/test_final_gap_closure_api.py::test_real_embedding_provider_requests_configured_vector_dimensions` |
| Embedding 维度兼容 | 已在真实 provider 请求中显式传入 32 维 | `backend/app/services/rag_service.py` | 同上 |
| Agent 失败 Bad Case 闭环 | 已补齐 `record_bad_case` 工具步骤和 task-scoped Bad Case | `backend/app/services/agent_service.py` | `backend/tests/test_agent_workflow_api.py::test_failed_step_retry_records_retry_step` |
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
| `cd backend && ./.venv/bin/python -m pytest -q` | PASS, 156 passed, 5 warnings |
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
| H-01 | LLM Provider | 分类、抽取、RAG answer、rerank、explain 已有 OpenAI-compatible 配置路径；默认仍会降级到 deterministic / regex fallback，未完成带真实/本地 Provider 的端到端验收。 |
| H-02 | RAG | 四库、workpaper scope、citation、no-answer、embedding 维度配置存在；默认 embedding/rerank/answer 仍是 deterministic/local fallback，真实 Provider 端到端验收未完成。 |
| H-03 | Agent Workflow | 状态机、步骤、重试、Review 路由和失败 Bad Case 闭环存在；与执行手册完整 Agent 角色职责口径仍未完全逐项证明。 |

### Medium

| 编号 | 模块 | 缺口 |
| --- | --- | --- |
| M-01 | Evaluation | 数据集驱动入口已存在，但真实 OCR、真实 RAG groundedness、真实 Agent E2E 评测仍依赖外部标注集和真实 Provider 配置。 |
| M-02 | Report | xlsx/csv/markdown/pdf 均存在；PDF 仍是简化文本版，报告质量受上游 evidence/bbox/confidence 影响。 |
| M-03 | Review | 主流程满足；历史 `actor_name` / `reviewed_by` / `corrected_by` 字符串字段仍为兼容口径。 |
| M-04 | Frontend tests | 前端构建通过，但仍无自动化 UI 测试。 |

## fallback / synthetic / demo 状态

| 类型 | 当前状态 | 是否仍影响完全满足 |
| --- | --- | --- |
| deterministic classification fallback | 仍存在，`model_invocations.status="fallback"` | 是 |
| regex extraction fallback | 仍存在，`model_invocations.status="fallback"` | 是 |
| PyMuPDF OCR confidence unavailable | 默认本地路径仍存在 warning；HTTP OCR Provider 可保留真实 confidence | 默认路径仍影响完全满足 |
| deterministic/local RAG embedding/rerank/answer | 仍存在，真实 embedding 请求已支持独立配置和 32 维参数 | 是，直到真实/本地 Provider 完成验收 |
| explain deterministic fallback | 真实/本地 Provider 未配置时仍 fallback，但已记录 `explain` 调用 | 是 |
| agent failure bad case | 失败步骤已自动进入 `agent` Bad Case，重试会保留独立记录 | 不再作为 Bad Case 闭环缺口 |
| built-in sample Evaluation | 保留为 smoke，不作为最终评测证据 | 仍影响真实验收 |
| demo seed samples | 仍保留 | 不可作为完全满足证据 |
| external real/desensitized Evaluation dataset | 已支持 JSON 读取路径 | 需要用户提供真实/脱敏标注数据才能最终验收 |

## 下一轮最高优先级

1. Agent Workflow 角色职责、状态口径和工具输出继续逐项证明。
2. LLM/RAG Provider 真实端到端验收在安全配置下完成。
3. 前端自动化测试和最终 UI 权限验证。
