src = r"tests/data/1.xlsx"
prompt = """请将同一份数据按三个目标场景分别填入模板中的三个表：
目标A：监测时间为2025-11-25 09:00:00.0，城市是德州市；
目标B：监测时间为2025-11-25 09:00:00.0，城市是潍坊市；
目标C：监测时间为2025-11-25 09:00:00.0，城市是临沂市。"""
template = r"tests/test_d/data2/template.docx"
output_json = r"tests/test_d/data3/filtered_rows_data3.json"
output_template = r"tests/test_d/data3/filled_template_data3.docx"
allow_rule_fallback = True
