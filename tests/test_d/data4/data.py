src = r"tests/data/1.xlsx"
prompt = """请完成模板填表任务。说明如下：
1) 这次只需要填写同一个表，不需要拆成多个目标表；
2) 条件较复杂，请同时满足：
   - 监测时间必须是 2025-11-25 09:00:00.0；
   - 城市在“德州市、潍坊市、临沂市”三者之中；
3) 其余城市或时间的数据不要写入。
请根据上述单表条件筛选并填写。"""
template = r"tests/test_d/data2/template.docx"
output_json = r"tests/test_d/data4/filtered_rows_data4.json"
output_template = r"tests/test_d/data4/filled_template_data4.docx"
allow_rule_fallback = True
