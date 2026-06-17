# 文档智能系统 · 集成契约 v1

> **版本**: 1.0.0  
> **状态**: 草案（团队确认后冻结为 v1，后续变更需走评审并升版本号）  
> **维护**: C 组（数据层与编排）牵头，A / B / D 组共同遵守  

本文档用于在**表结构设计、API、各 Agent 输入输出**对齐前，冻结跨组约定。未列事项由各组在群内补充后更新本文档版本。

---

## 目录

1. [抽取结果 JSON（B → C / D）](#1-抽取结果-jsonb--c--d)
2. [任务状态枚举](#2-任务状态枚举)
3. [统一错误码](#3-统一错误码)
4. [API 错误响应格式](#4-api-错误响应格式)
5. [A 组：执行日志最小字段](#5-a-组执行日志最小字段)
6. [D 组：填表报告结构](#6-d-组填表报告结构)
7. [变更流程](#7-变更流程)

---

## 1. 抽取结果 JSON（B → C / D）

### 1.1 设计原则

- 结构化业务字段与 **JSONB** 并存：便于查询的列（如 `task_id`、`schema_version`）用列存；完整抽取体用 JSONB 存。
- 每个可抽取字段建议包含：**值、置信度、证据**，便于审计与人工复核（`review`）。

### 1.2 顶层结构（约定）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `schema_version` | string | 是 | 本契约版本，如 `1.0.0` |
| `task_id` | string | 是 | 与编排任务一致 |
| `source` | object | 否 | 源文档元信息摘要 |
| `fields` | array | 是 | 抽取字段列表，见下表 |
| `extras` | object | 否 | 扩展信息，不参与核心校验时可放此处 |

`source` 建议字段（可选）：`file_name`、`file_hash`、`mime_type`、`page_count`。

### 1.3 `fields[]` 单项结构

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | string | 是 | 字段名（与模板/映射一致） |
| `value` | string \| number \| boolean \| null \| array \| object | 是 | 抽取值 |
| `confidence` | number | 否 | 0～1，缺失表示未估算 |
| `evidence` | object | 否 | 证据，见 1.4 |

### 1.4 `evidence` 建议结构（至少兼容一种）

```json
{
  "page": 3,
  "paragraph_index": 12,
  "quote": "原文片段（不宜过长）",
  "sheet": "Sheet1",
  "cell": "B7"
}
```

字段按需出现：文本文档侧重 `page` / `paragraph_index` / `quote`；表格侧重 `sheet` / `cell`。

### 1.5 示例（完整）

```json
{
  "schema_version": "1.0.0",
  "task_id": "a1b2c3d4",
  "source": {
    "file_name": "合同.pdf",
    "file_hash": "sha256:...",
    "page_count": 12
  },
  "fields": [
    {
      "key": "甲方名称",
      "value": "某某科技有限公司",
      "confidence": 0.92,
      "evidence": {
        "page": 1,
        "paragraph_index": 2,
        "quote": "甲方：某某科技有限公司"
      }
    },
    {
      "key": "签订日期",
      "value": "2025-03-01",
      "confidence": 0.78,
      "evidence": { "page": 1, "quote": "签订日期：2025年3月1日" }
    }
  ],
  "extras": {}
}
```

### 1.6 与 JSON Schema 的关系

同目录已提供 **`extraction-result.schema.json`**（JSON Schema Draft 2020-12），可供 B 组校验或与 CI 集成；变更时请与 `schema_version` 同步升级。

---

## 2. 任务状态枚举

### 2.1 状态列表

| 值 | 说明 |
|----|------|
| `queued` | 已创建，等待执行 |
| `running` | 执行中 |
| `succeeded` | 成功结束 |
| `failed` | 失败结束（应配合 `error_code`） |
| `review` | 待人工复核（如置信度低或策略命中） |
| `cancelled` | **可选**：用户或系统取消；若产品不需要可不实现 |

数据库存储、API 返回、日志中**必须使用上表英文小写值**，禁止同义混用（如 `SUCCESS` / `成功`）。

### 2.2 建议迁移（逻辑约束）

- `queued` → `running` → `succeeded` | `failed` | `review`
- `review` → `succeeded` | `failed`（复核通过或驳回）
- `queued` → `cancelled`（若启用 `cancelled`）
- `running` → `cancelled`（若支持中断）

具体由编排器实现；DB 层可通过检查约束或应用层校验保证合法迁移。

---

## 3. 统一错误码

以下为**机器可读**代码，与 HTTP 状态码配合使用；`message` 给人看，可中文。

| `code` | 说明 | 典型 HTTP |
|--------|------|-----------|
| `PARSE_FAILED` | 文档解析失败（格式损坏、不支持的格式等） | 400 |
| `FIELD_MISSING` | 抽取或填表缺少约定字段 | 422 |
| `TEMPLATE_MISMATCH` | 模板与数据/映射不一致 | 400 |
| `MAPPING_ERROR` | 字段映射配置错误 | 400 |
| `DB_CONFLICT` | 数据库唯一约束、乐观锁、版本冲突 | 409 |
| `DB_UNAVAILABLE` | 数据库不可用 | 503 |
| `LLM_ERROR` | 大模型调用失败或内容不合规 | 502 / 500 |
| `VALIDATION_ERROR` | 请求体或参数校验失败 | 400 |
| `INTERNAL_ERROR` | 未分类服务器错误 | 500 |

各组新增业务错误时：**先在本表追加一行**，再使用，避免重复语义。

---

## 4. API 错误响应格式

成功响应体各接口自定义；**失败**建议统一为：

```json
{
  "success": false,
  "error": {
    "code": "FIELD_MISSING",
    "message": "缺少必填字段：乙方名称",
    "details": {}
  }
}
```

- `details`：可选，放字段级错误、校验器输出等结构化信息。  
- 成功可统一为：`{ "success": true, "data": { ... } }`（若团队采用 REST 也可仅用 HTTP 状态区分，但错误体建议仍用上述结构）。

---

## 5. A 组：执行日志最小字段

用于审计与（可选）回放；落库可整段 JSONB 或拆列 + 大文本走对象存储。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | string | 是 | 关联任务 |
| `timestamp` | string (ISO 8601) | 是 | UTC 或带偏移 |
| `action` | string | 是 | 如 `plan_generated` / `ops_applied` / `rollback` |
| `summary` | string | 是 | 人类可读摘要 |
| `ops_count` | number | 否 | 操作条数 |
| `rollback_id` | string | 否 | 可回滚时的标识 |
| `detail_ref` | string | 否 | 详细日志在 OSS/本地路径/Storage 的 key |

扩展字段可放 `extras` object。

---

## 6. D 组：填表报告结构

填表任务完成后，除输出文件外，建议产出**结构化报告**，便于 C 组入库与质检。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | string | 是 | 关联任务 |
| `schema_version` | string | 是 | 如 `1.0.0` |
| `template_id` | string | 否 | 模板标识 |
| `output_file` | object | 是 | 见下 |
| `filled_fields` | array | 否 | 已写入字段 key 列表或 `{ key, cell }` |
| `skipped_fields` | array | 否 | 未写入字段及原因简述 |
| `warnings` | array of string | 否 | 警告信息 |
| `errors` | array of string | 否 | 非致命错误 |

`output_file` 建议：

```json
{
  "storage_key": "fills/task_id/output.xlsx",
  "file_name": "结果.xlsx",
  "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
}
```

若无对象存储，可用 `local_path` 替代 `storage_key`，需在团队内统一。

---

## 7. 变更流程

1. 任一契约变更：发起短评审（负责人 + C 组 + 受影响组）。  
2. 破坏性变更：升 `schema_version` 或 `integration-contract` 主版本（如 v1 → v2）。  
3. 本文档与可选 JSON Schema 同步更新，并在仓库打 tag 或记录变更日期。  

---

**文档结束（v1.0.0 草案）**
