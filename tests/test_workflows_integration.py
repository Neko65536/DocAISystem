"""工作流编排 API 集成测试。"""
from __future__ import annotations

import base64
import time
from typing import Dict, Any

import pytest


def _poll_execution(api_client, execution_id: str, timeout_s: float = 30.0) -> Dict[str, Any]:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        r = api_client.get(f"/api/workflows/executions/{execution_id}")
        assert r.status_code == 200
        body = r.json()
        last = body
        if body.get("status") in {"completed", "failed"}:
            return body
        time.sleep(0.2)
    assert last is not None
    return last


def _build_local_file_payload(name: str, text: str) -> Dict[str, Any]:
    encoded = base64.b64encode(text.encode("utf-8")).decode("utf-8")
    return {"name": name, "size": len(text.encode("utf-8")), "content": encoded}


def test_workflow_templates_detail_and_not_found(api_client):
    ok_pdf = api_client.get("/api/workflows/templates/translate-pdf")
    assert ok_pdf.status_code == 200
    assert ok_pdf.json()["id"] == "translate-pdf"

    ok_docx = api_client.get("/api/workflows/templates/translate-docx")
    assert ok_docx.status_code == 200
    assert ok_docx.json()["id"] == "translate-docx"

    missing = api_client.get("/api/workflows/templates/not-exist")
    assert missing.status_code == 404


def test_workflow_execute_success_and_status_query(api_client):
    payload = {
        "workflowId": "it_success_case",
        "nodes": [
            {"id": "n1", "type": "input", "title": "TXT 输入", "schemaKey": "schema-txt-input", "configValues": {}},
            {"id": "n2", "type": "ai", "title": "内容提取", "schemaKey": "schema-extract-summary", "configValues": {"extractType": "summary"}},
            {
                "id": "n3",
                "type": "output",
                "title": "输出文件",
                "schemaKey": "schema-library-output",
                "configValues": {"outputMode": "download", "outputFormat": "md", "namingRule": "{original_name}_it"},
            },
        ],
        "docs": [],
        "localFiles": [_build_local_file_payload("it_success.txt", "workflow integration test text")],
    }
    start = api_client.post("/api/workflows/execute", json=payload)
    assert start.status_code == 200
    execution_id = start.json()["execution_id"]

    final_state = _poll_execution(api_client, execution_id)
    assert final_state["status"] == "completed"
    assert isinstance(final_state.get("output_files"), list)
    assert len(final_state["output_files"]) >= 1
    assert final_state.get("error_code") in (None, "")
    assert final_state.get("total_nodes") == 3
    assert final_state.get("node_progress")
    assert [n.get("status") for n in final_state["node_progress"]] == ["completed", "completed", "completed"]
    assert final_state.get("current_node_name") == "输出文件"


def test_workflow_failure_then_recovery(api_client):
    bad_payload = {
        "workflowId": "it_failure_case",
        "nodes": [{"id": "n1", "type": "input", "title": "TXT 输入", "schemaKey": "schema-txt-input", "configValues": {}}],
        "docs": [],
        "localFiles": [],
    }
    bad_start = api_client.post("/api/workflows/execute", json=bad_payload)
    assert bad_start.status_code == 200
    bad_state = _poll_execution(api_client, bad_start.json()["execution_id"])
    assert bad_state["status"] == "failed"
    assert bad_state.get("error_code") == "VALIDATION_ERROR"

    ok_payload = {
        "workflowId": "it_recovery_case",
        "nodes": [
            {"id": "n1", "type": "input", "title": "TXT 输入", "schemaKey": "schema-txt-input", "configValues": {}},
            {"id": "n2", "type": "ai", "title": "内容提取", "schemaKey": "schema-extract-summary", "configValues": {"extractType": "summary"}},
            {
                "id": "n3",
                "type": "output",
                "title": "输出文件",
                "schemaKey": "schema-library-output",
                "configValues": {"outputMode": "download", "outputFormat": "md", "namingRule": "{original_name}_ok"},
            },
        ],
        "docs": [],
        "localFiles": [_build_local_file_payload("it_recovery.txt", "recovery text")],
    }
    ok_start = api_client.post("/api/workflows/execute", json=ok_payload)
    assert ok_start.status_code == 200
    ok_state = _poll_execution(api_client, ok_start.json()["execution_id"])
    assert ok_state["status"] == "completed"


def test_workflow_output_format_txt_is_effective(api_client):
    payload = {
        "workflowId": "it_txt_format_case",
        "nodes": [
            {"id": "n1", "type": "input", "title": "TXT 输入", "schemaKey": "schema-txt-input", "configValues": {}},
            {"id": "n2", "type": "ai", "title": "内容提取", "schemaKey": "schema-extract-summary", "configValues": {"extractType": "summary"}},
            {
                "id": "n3",
                "type": "output",
                "title": "输出文件",
                "schemaKey": "schema-library-output",
                "configValues": {"outputMode": "download", "outputFormat": "txt", "namingRule": "{original_name}_txt"},
            },
        ],
        "docs": [],
        "localFiles": [_build_local_file_payload("it_txt.txt", "text output format verify")],
    }
    start = api_client.post("/api/workflows/execute", json=payload)
    assert start.status_code == 200
    final_state = _poll_execution(api_client, start.json()["execution_id"])
    assert final_state["status"] == "completed"
    out = final_state["output_files"][0]
    assert str(out.get("name", "")).endswith(".txt")


@pytest.mark.parametrize(
    "schema_key,title,config_values",
    [
        ("schema-keyword-highlight", "关键词高亮", {"topK": "6", "marker": "**"}),
        ("schema-sensitive-masking", "敏感信息脱敏", {"maskToken": "*"}),
        (
            "schema-term-normalize",
            "术语统一替换",
            {"termDictionary": "AI=>人工智能;LLM=>大语言模型"},
        ),
        ("schema-outline-generate", "结构化提纲生成", {"maxDepth": "3"}),
        ("schema-sentiment-enhanced", "情感倾向分析", {}),
        ("schema-timeline-extract", "时间线抽取", {}),
    ],
)
def test_workflow_new_processing_nodes_can_execute(api_client, schema_key: str, title: str, config_values: Dict[str, Any]):
    payload = {
        "workflowId": f"it_{schema_key}",
        "nodes": [
            {"id": "n1", "type": "input", "title": "TXT 输入", "schemaKey": "schema-txt-input", "configValues": {}},
            {"id": "n2", "type": "ai", "title": title, "schemaKey": schema_key, "configValues": config_values},
            {
                "id": "n3",
                "type": "output",
                "title": "输出文件",
                "schemaKey": "schema-library-output",
                "configValues": {
                    "outputMode": "download",
                    "outputFormat": "md",
                    "namingRule": f"{{original_name}}_{schema_key}",
                },
            },
        ],
        "docs": [],
        "localFiles": [_build_local_file_payload(f"it_{schema_key}.txt", f"integration text for {schema_key}")],
    }
    start = api_client.post("/api/workflows/execute", json=payload)
    assert start.status_code == 200
    final_state = _poll_execution(api_client, start.json()["execution_id"], timeout_s=40.0)
    assert final_state["status"] == "completed"
    assert final_state.get("error_code") in (None, "")
    assert isinstance(final_state.get("output_files"), list)
    assert len(final_state["output_files"]) >= 1

