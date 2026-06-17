src = r"tests/data/1.xlsx"
prompt = ""
template = r"tests/test_d/data1/template.docx"
output_json = r"tests/test_d/data1/filtered_rows_data1.json"
output_template = r"tests/test_d/data1/filled_template_data1.docx"
allow_rule_fallback = True

table_targets = [
	{
		"name": "表一",
		"instruction": "	监测时间：2025-11-25 09:00:00.0  城市：德州市",
		"template_sheet_name": "表一",
		"template_header_row": 1,
		"template_start_row": 2,
        "template_table_index": 0,
	},
	{
		"name": "表二",
		"instruction": "	监测时间：2025-11-25 09:00:00.0  城市：潍坊市",
		"template_sheet_name": "表二",
		"template_header_row": 1,
		"template_start_row": 2,
        "template_table_index": 1,
	},
	{
		"name": "表三",
		"instruction": "	监测时间：2025-11-25 09:00:00.0  城市：临沂市",
		"template_sheet_name": "表三",
		"template_header_row": 1,
		"template_start_row": 2,
        "template_table_index": 2,
	},
]