# C 组：数据层与任务编排（PostgreSQL / Supabase）

本文档说明本项目中 **C 组职责对应的实现范围、模块划分、库表、接口与协作方式**，供组内同步与答辩引用。

---

## 1. 职责对照

| 职责 | 实现要点 |
|------|----------|
| **JSON 入库** | B 组抽取结果写入 `extraction_results.payload`（JSONB）；通过 `AgentC` 与 `db.repository.extraction` 完成事务内写入。 |
| **任务状态机** | `tasks.status`（`queued` / `running` / `succeeded` / `failed` / `review` / `cancelled`）；编排入口见 `workflow_persistence`；入库成功/失败见抽取与编排逻辑。 |
| **审计日志** | `audit_logs`；关键事件：`task_upserted`、`task_status_*`、`workflow_*`、复核相关事件等。 |
| **检索能力** | `repository.queries`（按 `task_id`、分页列表、最新抽取结果）；API 暴露查询。 |
| **文档元数据** | `document_assets`；`insert_document_asset`；大文件本体建议走对象存储，库内仅存元数据与 `storage_key`。 |
| **抽取结果与版本** | `extraction_results.result_version` 递增；同任务多版本可追溯。 |
| **接口服务** | FastAPI：`src/api/main.py`；错误体对齐 `docs/contracts/integration-contract-v1.md`。 |
| **技术重点** | 结构化列 + JSONB 混合；`extraction_results.payload` 上 GIN（jsonb_path_ops）；关键操作用事务保证一致性。 |

---

## 2. 目录与模块

```
src/db/
├── connection.py          # 连接池、health_check、build_conninfo（支持 DATABASE_URL / Supabase）
├── workflow_persistence.py   # 编排与 DB 对齐：persist_workflow_execute_begin / _end
└── repository/            # 数据访问层（按职责拆分）
    ├── types.py           # TaskRow、ExtractionResultRow、SaveExtractionOutcome 等
    ├── queries.py         # 任务与抽取结果查询、list_tasks
    ├── audit.py           # audit_logs、task_steps（连接内/独立事务）
    ├── mutations.py       # ensure_task、mark_task_*、save_extraction_result
    ├── extraction.py      # resolve_task_id、save_extraction_from_agent_payload(_safe)
    ├── artifacts.py       # fill_reports、agent_execution_logs、document_assets
    ├── timeline.py        # get_task_timeline（步骤 + 审计聚合）
    └── review.py          # set_task_review（mark_review / approve / reject）

src/api/main.py            # HTTP API（FastAPI）

sql/schema_v1.sql          # 建表 DDL（PostgreSQL 14+ / Supabase）
docs/contracts/            # 集成契约与 JSON Schema
tests/                     # pytest + TestClient
```

对外仍统一使用：`from db.repository import ...`（包聚合在 `repository/__init__.py`）。

---

## 3. 数据库表（概要）

| 表名 | 作用 |
|------|------|
| **tasks** | 任务主表；业务键 `task_id`（TEXT，与 JSON/API 一致）；内部主键 `id`（UUID）。 |
| **task_steps** | 步骤追踪（如 `orchestrator_start`、`parse_doc`、`save_result` 等）。 |
| **extraction_results** | B 组抽取全文；`schema_version` + `payload`（JSONB）+ `result_version`。 |
| **audit_logs** | 通用审计；`subject_type`+`subject_id` 关联任务业务 id。 |
| **document_assets** | 文档元数据（路径、hash、storage_key 等）。 |
| **agent_execution_logs** | A 组执行日志。 |
| **fill_reports** | D 组填表报告。 |

建表脚本：`sql/schema_v1.sql`。生产环境建议保留迁移记录（当前以 SQL 文件为基线）。

---

## 4. 与各组的输入输出

| 来源 | 内容 | 落库方式 |
|------|------|----------|
| **B 组** | 抽取 JSON（契约见 `integration-contract-v1.md`） | `AgentC.execute` → `save_extraction_from_agent_payload` |
| **A 组** | 执行日志（action、summary 等） | `insert_agent_log` 或 API `POST .../agent-logs` |
| **D 组** | 填表报告 | `insert_fill_report` 或 API `POST .../fill-report` |
| **编排** | 任务开始/结束 | `WorkflowCoordinator` 调用 `persist_workflow_execute_begin` / `end` |

**`task_id` 约定**：业务层统一使用字符串 `task_id`；编排会在 `TaskSpec.parameters["task_id"]` 中写入，便于与 B/C 对齐。

---

## 5. HTTP API（最小集）

错误体统一为：`{"success": false, "error": {"code", "message", "details"}}`；成功为：`{"success": true, "data": ...}`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 服务与数据库连通性 |
| GET | `/tasks/{task_id}` | 查询任务 |
| GET | `/tasks/{task_id}/extraction` | 最新一条抽取结果 |
| GET | `/tasks/{task_id}/timeline` | 任务 + 步骤 + 审计聚合 |
| POST | `/tasks/{task_id}/review` | 复核：`action`= mark_review / approve / reject |
| POST | `/tasks/{task_id}/document-assets` | 登记文档元数据 |
| POST | `/tasks/{task_id}/fill-report` | D 组报告体（JSON） |
| POST | `/tasks/{task_id}/agent-logs` | A 组日志体（JSON） |

启动（工作目录为 `src`）：

```bash
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

浏览器可打开 `/docs` 查看 Swagger。

---

## 6. 配置要点

环境变量（示例见根目录 `.env.example`）：

- `DB_ENABLED=true`
- `DATABASE_URL` 或 `SUPABASE_DB_URL`（完整 URI）
- 分段配置：`DB_HOST`、`DB_NAME`、`DB_USER`、`DB_PASSWORD` 等
- 云库建议：`DB_SSLMODE=require`

应用配置：`src/config.py` 中 `DatabaseConfig`。

---

## 7. 测试

- 框架：**pytest**；API：**httpx.TestClient**（FastAPI 自带）。
- 配置：`pytest.ini`（`pythonpath = src`）。
- 集成测试：`tests/test_repository_integration.py`（需 `DB_ENABLED=true` 且配置连接串；未配置则跳过）。

运行：

```bash
pytest tests -q
```

---

## 8. 答辩与交付建议

1. **演示一条完整链路**：创建任务（编排或 API）→ B 抽取入库 → `GET .../timeline` 展示步骤与审计。  
2. **附图**：核心表 ER 或「表—职责」对照表（本文第 3 节可扩展）。  
3. **说明边界**：任务状态由「编排」「AgentC 入库」「人工复核 API」等多入口更新时，在文档或口头说明各自触发条件。  
4. **契约**：`docs/contracts/integration-contract-v1.md` 为跨组接口基准，变更需升版本。

---

## 9. 可选后续（非阻塞）

- 迁移工具（Alembic/Flyway）管理 DDL 版本。  
- 公网部署时 API 鉴权、Supabase RLS。  
- CI 中执行 `pytest`（无 DB 时仅跑不依赖真库的用例）。  
- 低置信度策略触发 `review`（需与 B 组约定）。

---

**文档版本**：与仓库当前实现同步；若模块或 API 有变更，请同步更新本节与 `docs/contracts/`。
