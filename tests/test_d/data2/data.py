src = r"tests/data/1.xlsx"
prompt = """完成填表工作，要求提取表格中对应数据。
模板文件中对应有三个表，并且每一个表上文均有对该表的描述。
表一：
	监测时间：2025-11-25 09:00:00.0
	城市：德州市
表二：
	监测时间：2025-11-25 09:00:00.0
	城市：潍坊市
表三：
	监测时间：2025-11-25 09:00:00.0
	城市：临沂市"""
template = r"tests/test_d/data2/template.docx"
output_json = r"tests/test_d/data2/filtered_rows_data2.json"
output_template = r"tests/test_d/data2/filled_template_data2.docx"
allow_rule_fallback = True

