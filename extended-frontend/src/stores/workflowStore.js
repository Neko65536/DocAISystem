import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import workflowApi from '../api/workflow'

export const useWorkflowStore = defineStore('workflow', () => {
  // ==================== 状态 ====================

  const currentWorkflowId = ref(null)
  const searchQuery = ref('')
  const workflowName = ref('新建工作流')

  // 选中的文档（来自文档库或本地上传）
  const selectedDocs = ref([])
  const localFiles = ref([])       // 本地上传的文件（File 对象）

  // 当前选中的节点 ID
  const selectedNodeId = ref(null)

  // 每个节点的配置值（key: nodeId, value: { paramKey: paramValue }）
  const nodeConfigs = ref({})

  // 画布节点列表
  const canvasNodes = ref([])
  const canvasEdges = ref([])

  // ==================== 动态数据（从 API 加载） ====================

  const workflows = ref({})
  const templates = ref([])
  const availableModels = ref([])
  const availableLanguages = ref([])
  const outputFormats = ref([])
  const defaultRunConfig = {
    concurrentLimit: 4,
    continueOnError: false,
    notifyOnError: true,
  }
  const CANVAS_SIZE = 4800
  const DEFAULT_NODE_X = 2250
  const DEFAULT_NODE_Y = 2200
  const runConfigState = ref({ ...defaultRunConfig })
  const unsupportedFieldHints = ref({})

  // ==================== 节点 Schema（无硬编码值，所有选项由 API 决定） ====================

  const nodeSchemas = ref({
    'schema-pdf-input': {
      icon: '📕', iconClass: 'input',
      title: 'PDF 输入', subtitle: '输入节点',
      fields: [
        { key: 'inputSource', label: '文档来源', type: 'select-source',
          options: [{ value: 'library', label: '从文档库选择' }, { value: 'local', label: '本地上传' }] },
        { key: 'spaceId', label: '选择文档库', type: 'library-selector' },
        { key: 'skipExisting', label: '跳过已处理文档', type: 'toggle' }
      ]
    },
    'schema-md-input': {
      icon: '📝', iconClass: 'input',
      title: 'MD 输入', subtitle: '输入节点',
      fields: [
        { key: 'inputSource', label: '文档来源', type: 'select-source',
          options: [{ value: 'library', label: '从文档库选择' }, { value: 'local', label: '本地上传' }] },
        { key: 'spaceId', label: '选择文档库', type: 'library-selector' }
      ]
    },
    'schema-txt-input': {
      icon: '📄', iconClass: 'input',
      title: 'TXT 输入', subtitle: '输入节点',
      fields: [
        { key: 'inputSource', label: '文档来源', type: 'select-source',
          options: [{ value: 'library', label: '从文档库选择' }, { value: 'local', label: '本地上传' }] },
        { key: 'spaceId', label: '选择文档库', type: 'library-selector' }
      ]
    },
    'schema-docx-input': {
      icon: '📘', iconClass: 'input',
      title: 'DOCX 输入', subtitle: '输入节点',
      fields: [
        { key: 'inputSource', label: '文档来源', type: 'select-source',
          options: [{ value: 'library', label: '从文档库选择' }, { value: 'local', label: '本地上传' }] },
        { key: 'spaceId', label: '选择文档库', type: 'library-selector' }
      ]
    },
    'schema-xlsx-input': {
      icon: '📊', iconClass: 'input',
      title: 'XLSX 输入', subtitle: '输入节点',
      fields: [
        { key: 'inputSource', label: '文档来源', type: 'select-source',
          options: [{ value: 'library', label: '从文档库选择' }, { value: 'local', label: '本地上传' }] },
        { key: 'spaceId', label: '选择文档库', type: 'library-selector' },
        { key: 'sheetIndex', label: '工作表索引', type: 'input' },
        { key: 'hasHeader', label: '首行为表头', type: 'toggle' }
      ]
    },
    'schema-translate': {
      icon: '🌍', iconClass: 'ai',
      title: 'AI 翻译', subtitle: '翻译节点',
      fields: [
        { key: 'targetLanguage', label: '目标语言', type: 'language-selector' },
        { key: 'prompt', label: '翻译提示词', type: 'textarea' }
      ]
    },
    'schema-extract-summary': {
      icon: '📋', iconClass: 'ai',
      title: '内容提取', subtitle: '提取节点',
      fields: [
        { key: 'extractType', label: '提取类型', type: 'select',
          options: [{ value: 'summary', label: '生成摘要' }, { value: 'keypoints', label: '提取要点' }, { value: 'both', label: '摘要+要点' }] },
        { key: 'summaryLength', label: '摘要长度', type: 'select',
          options: [{ value: 'short', label: '简短' }, { value: 'medium', label: '适中' }, { value: 'detailed', label: '详细' }] },
        { key: 'prompt', label: '自定义提示词', type: 'textarea' }
      ]
    },
    'schema-extract-data': {
      icon: '📊', iconClass: 'ai',
      title: '数据抽取', subtitle: '抽取节点',
      fields: [
        { key: 'dataFormat', label: '输出格式', type: 'select',
          options: [{ value: 'json', label: 'JSON' }, { value: 'csv', label: 'CSV' }, { value: 'table', label: '表格' }] },
        { key: 'extractFields', label: '要提取的字段', type: 'textarea', placeholder: '例: 名称,日期,金额（逗号分隔）' },
        { key: 'prompt', label: '提取规则描述', type: 'textarea' }
      ]
    },
    'schema-analyze-content': {
      icon: '🔍', iconClass: 'ai',
      title: '内容分析', subtitle: '分析节点',
      fields: [
        { key: 'analysisType', label: '分析类型', type: 'select',
          options: [{ value: 'keywords', label: '关键词提取' }, { value: 'entities', label: '实体识别' }, { value: 'all', label: '全面分析' }] },
        { key: 'entityTypes', label: '实体类型', type: 'select-multiple',
          options: [{ value: 'person', label: '人名' }, { value: 'location', label: '地名' }, { value: 'org', label: '机构' }, { value: 'date', label: '日期' }] },
        { key: 'topK', label: '关键词数量', type: 'input', placeholder: '默认10' },
        { key: 'prompt', label: '自定义分析要求', type: 'textarea' }
      ]
    },
    'schema-enhance-text': {
      icon: '✨', iconClass: 'ai',
      title: '文本增强', subtitle: '增强节点',
      fields: [
        { key: 'enhanceType', label: '增强类型', type: 'select',
          options: [{ value: 'grammar', label: '语法检查' }, { value: 'polish', label: '文本润色' }, { value: 'rephrase', label: '改写' }, { value: 'all', label: '全面优化' }] },
        { key: 'style', label: '文本风格', type: 'select',
          options: [{ value: 'concise', label: '简洁' }, { value: 'formal', label: '学术' }, { value: 'casual', label: '口语' }, { value: 'professional', label: '专业' }] },
        { key: 'prompt', label: '自定义要求', type: 'textarea' }
      ]
    },
    'schema-convert-format': {
      icon: '🔄', iconClass: 'ai',
      title: '格式转换', subtitle: '转换节点',
      fields: [
        { key: '_hint_cf', type: 'static', text: '选择目标格式及转换选项；配置将保存在节点 config 供执行端解析。' },
        { key: 'targetFormat', label: '目标格式', type: 'select',
          options: [
            { value: 'markdown', label: 'Markdown' },
            { value: 'html', label: 'HTML' },
            { value: 'plaintext', label: '纯文本' },
            { value: 'pdf', label: 'PDF' },
            { value: 'docx', label: 'Word (DOCX)' },
            { value: 'json', label: 'JSON' }
          ] },
        { key: 'conversionOptions', label: '转换选项', type: 'select-multiple',
          options: [
            { value: 'keep_layout', label: '尽量保留版面' },
            { value: 'extract_tables', label: '优先提取表格' },
            { value: 'embed_images', label: '保留内嵌图片' },
            { value: 'code_as_text', label: '代码块转纯文本' },
            { value: 'sanitize_html', label: 'HTML 安全清洗' }
          ] },
        { key: 'preserveFormatting', label: '保留原格式标记', type: 'toggle' },
        { key: 'preserveStructure', label: '保留文档结构', type: 'toggle' },
        { key: 'prompt', label: '自定义转换规则', type: 'textarea' }
      ]
    },
    'schema-split-document': {
      icon: '✂️', iconClass: 'ai',
      title: '文档分割', subtitle: '分割节点',
      fields: [
        { key: 'splitMethod', label: '分割方式', type: 'select',
          options: [{ value: 'section', label: '按章节' }, { value: 'paragraph', label: '按段落' }, { value: 'size', label: '按大小' }, { value: 'page', label: '按页数' }] },
        { key: 'splitSize', label: '分割参数', type: 'input', placeholder: '如大小:字符数或页数' },
        { key: 'preserveContext', label: '保留上下文', type: 'toggle' },
        { key: 'prompt', label: '自定义分割规则', type: 'textarea' }
      ]
    },
    'schema-keyword-highlight': {
      icon: '🖍️', iconClass: 'ai',
      title: '关键词高亮', subtitle: '增强节点',
      fields: [
        { key: 'topK', label: '关键词数量', type: 'input', placeholder: '默认 10' },
        { key: 'marker', label: '高亮标记符', type: 'input', placeholder: '默认 **' },
        { key: 'prompt', label: '自定义规则', type: 'textarea' }
      ]
    },
    'schema-sensitive-masking': {
      icon: '🔒', iconClass: 'ai',
      title: '敏感信息脱敏', subtitle: '安全节点',
      fields: [
        { key: 'maskToken', label: '掩码符号', type: 'input', placeholder: '默认 *' },
        { key: 'prompt', label: '自定义脱敏规则', type: 'textarea' }
      ]
    },
    'schema-term-normalize': {
      icon: '📚', iconClass: 'ai',
      title: '术语统一替换', subtitle: '规范节点',
      fields: [
        { key: 'termDictionary', label: '术语词典', type: 'textarea', placeholder: '示例：A=>标准术语A; B=>标准术语B' },
        { key: 'prompt', label: '自定义规则', type: 'textarea' }
      ]
    },
    'schema-outline-generate': {
      icon: '🧭', iconClass: 'ai',
      title: '结构化提纲生成', subtitle: '分析节点',
      fields: [
        { key: 'maxDepth', label: '最大层级', type: 'input', placeholder: '默认 3' },
        { key: 'prompt', label: '自定义规则', type: 'textarea' }
      ]
    },
    'schema-sentiment-enhanced': {
      icon: '📈', iconClass: 'ai',
      title: '情感倾向分析', subtitle: '分析节点',
      fields: [
        { key: 'prompt', label: '自定义分析规则', type: 'textarea' }
      ]
    },
    'schema-timeline-extract': {
      icon: '🕒', iconClass: 'ai',
      title: '时间线抽取', subtitle: '抽取节点',
      fields: [
        { key: 'prompt', label: '自定义抽取规则', type: 'textarea' }
      ]
    },
    'schema-save': {
      icon: '💾', iconClass: 'output',
      title: '保存文件', subtitle: '输出节点',
      fields: [
        { key: 'savePath', label: '保存路径', type: 'input' },
        { key: 'outputFormat', label: '输出格式', type: 'format-selector' }
      ]
    },
    'schema-library-output': {
      icon: '📁', iconClass: 'output',
      title: '输出文件', subtitle: '输出节点',
      fields: [
        { key: 'outputMode', label: '输出模式', type: 'output-mode-select' },
        { key: 'targetSpaceId', label: '目标文档库', type: 'library-selector', conditionField: 'outputMode', conditionValue: 'library' },
        { key: 'namingRule', label: '文件命名规则', type: 'input', conditionField: 'outputMode', conditionValue: 'library' },
        { key: 'outputFormat', label: '输出格式', type: 'format-selector' },
        { key: 'notifyOnComplete', label: '完成通知', type: 'toggle' }
      ]
    },
    // —— 以下为《工作流编排-待办与用例》「节点配置」对齐的专项 schema ——
    'schema-entity-extraction': {
      icon: '🏷️', iconClass: 'ai',
      title: '实体提取', subtitle: '实体与结构化字段',
      fields: [
        { key: '_hint_entity', type: 'static', text: '从上游文档中抽取结构化实体；字段名与类型将随工作流保存到 config。' },
        { key: 'entityFieldList', label: '提取字段列表', type: 'textarea', placeholder: '每行一个字段，或逗号分隔，例：姓名\n日期\n金额' },
        { key: 'customEntityTypes', label: '自定义实体类型', type: 'textarea', placeholder: '可选：描述需识别的自定义类型，如「合同条款」「项目阶段」' },
        { key: 'aliasMap', label: '字段别名映射', type: 'textarea', placeholder: '可选：买方=甲方; 卖方=乙方（分号或换行分隔）' },
        { key: 'prompt', label: '补充抽取规则', type: 'textarea', placeholder: '对模型或规则的额外说明' }
      ]
    },
    'schema-data-process': {
      icon: '📐', iconClass: 'ai',
      title: '数据处理', subtitle: '表格类操作',
      fields: [
        { key: '_hint_dp', type: 'static', text: '针对表格数据：先选择处理类型，再填写对应参数（与《节点处理》数据处理章节一致）。' },
        { key: 'processKind', label: '处理类型', type: 'select',
          options: [
            { value: 'sort', label: '排序' },
            { value: 'filter', label: '筛选' },
            { value: 'aggregate', label: '汇总' },
            { value: 'dedupe', label: '去重' },
            { value: 'fill_null', label: '填充空值' },
            { value: 'computed_column', label: '新增计算列' },
            { value: 'merge_columns', label: '合并列' },
            { value: 'split_column', label: '拆分列' }
          ] },
        { key: 'sortColumn', label: '排序列（列名）', type: 'input', placeholder: '例如：金额 或 D', dependsOn: { field: 'processKind', value: 'sort' } },
        { key: 'sortOrder', label: '升降序', type: 'select',
          options: [{ value: 'asc', label: '升序' }, { value: 'desc', label: '降序' }],
          dependsOn: { field: 'processKind', value: 'sort' } },
        { key: 'filterExpr', label: '筛选条件', type: 'textarea', placeholder: '例：列「状态」= 已完成；或简短表达式说明', dependsOn: { field: 'processKind', value: 'filter' } },
        { key: 'aggregateColumn', label: '汇总列', type: 'input', placeholder: '要汇总的列名', dependsOn: { field: 'processKind', value: 'aggregate' } },
        { key: 'aggregateOp', label: '汇总方式', type: 'select',
          options: [
            { value: 'sum', label: '求和' },
            { value: 'count', label: '计数' },
            { value: 'avg', label: '平均值' },
            { value: 'min', label: '最小' },
            { value: 'max', label: '最大' }
          ],
          dependsOn: { field: 'processKind', value: 'aggregate' } },
        { key: 'groupByColumns', label: '分组列（可选）', type: 'input', placeholder: '逗号分隔，留空表示全文一条汇总', dependsOn: { field: 'processKind', value: 'aggregate' } },
        { key: 'dedupeColumns', label: '去重依据列', type: 'input', placeholder: '逗号分隔列名，留空表示整行去重', dependsOn: { field: 'processKind', value: 'dedupe' } },
        { key: 'fillColumns', label: '填充列', type: 'input', placeholder: '要填充的列，逗号分隔', dependsOn: { field: 'processKind', value: 'fill_null' } },
        { key: 'fillValue', label: '填充值', type: 'input', placeholder: '例如：0 或 N/A', dependsOn: { field: 'processKind', value: 'fill_null' } },
        { key: 'computedFormula', label: '计算表达式', type: 'textarea', placeholder: '例：=[金额]*[数量] 或列运算说明', dependsOn: { field: 'processKind', value: 'computed_column' } },
        { key: 'computedColumnName', label: '新列名', type: 'input', placeholder: '结果写入的列标题', dependsOn: { field: 'processKind', value: 'computed_column' } },
        { key: 'mergeSourceColumns', label: '待合并列', type: 'input', placeholder: '逗号分隔', dependsOn: { field: 'processKind', value: 'merge_columns' } },
        { key: 'mergeSeparator', label: '连接符', type: 'input', placeholder: '默认空格', dependsOn: { field: 'processKind', value: 'merge_columns' } },
        { key: 'mergeTargetColumn', label: '目标列名', type: 'input', dependsOn: { field: 'processKind', value: 'merge_columns' } },
        { key: 'splitSourceColumn', label: '待拆分列', type: 'input', dependsOn: { field: 'processKind', value: 'split_column' } },
        { key: 'splitDelimiter', label: '分隔符', type: 'input', placeholder: '如：,、;、|', dependsOn: { field: 'processKind', value: 'split_column' } },
        { key: 'splitIntoColumns', label: '拆成列名', type: 'input', placeholder: '逗号分隔多列标题', dependsOn: { field: 'processKind', value: 'split_column' } },
        { key: 'prompt', label: '补充说明', type: 'textarea' }
      ]
    },
    'schema-data-clean': {
      icon: '🧼', iconClass: 'ai',
      title: '数据清洗', subtitle: '规则与规范化',
      fields: [
        { key: '_hint_dc', type: 'static', text: '可多选下方规则；实际清洗与预览在执行阶段由服务端/执行引擎应用（可先保存配置再联调）。' },
        { key: 'cleanRules', label: '清洗规则', type: 'select-multiple',
          options: [
            { value: 'trim_spaces', label: '去除首尾空格' },
            { value: 'normalize_date', label: '统一日期格式' },
            { value: 'normalize_number', label: '统一数字格式' },
            { value: 'handle_outliers', label: '处理异常值' },
            { value: 'expand_merged_cells', label: '合并单元格展开' },
            { value: 'fix_format_errors', label: '修正格式错误' }
          ] },
        { key: 'dateFormatPattern', label: '目标日期格式', type: 'input', placeholder: '例：YYYY-MM-DD（勾选「统一日期格式」后可填）',
          dependsOn: { field: 'cleanRules', arrayIncludes: 'normalize_date' } },
        { key: 'numberDecimalPlaces', label: '小数位数', type: 'input', placeholder: '可选，如：2',
          dependsOn: { field: 'cleanRules', arrayIncludes: 'normalize_number' } },
        { key: 'prompt', label: '补充规则说明', type: 'textarea' },
        { key: '_preview_note', type: 'static', text: '「预览清洗结果」需执行流水线支持后由后端推送或轮询刷新；此处仅保存规则配置。' }
      ]
    },
    'schema-table-extract': {
      icon: '📑', iconClass: 'ai',
      title: '表格提取', subtitle: '从文档中抽取表格',
      fields: [
        { key: 'tableStrategy', label: '提取策略', type: 'select',
          options: [
            { value: 'first', label: '第一个表格' },
            { value: 'all', label: '全部表格' },
            { value: 'by_index', label: '按序号' }
          ] },
        { key: 'tableIndex', label: '表格序号（从 1 开始）', type: 'input', placeholder: '当策略为「按序号」',
          dependsOn: { field: 'tableStrategy', value: 'by_index' } },
        { key: 'hasHeader', label: '首行为表头', type: 'toggle' },
        { key: 'prompt', label: '补充说明', type: 'textarea' }
      ]
    },
    'schema-data-rollup': {
      icon: '📈', iconClass: 'ai',
      title: '数据汇总', subtitle: '统计汇总',
      fields: [
        { key: 'rollupDims', label: '分类维度（列）', type: 'textarea', placeholder: '逗号或换行分隔' },
        { key: 'rollupMetrics', label: '指标与聚合', type: 'textarea', placeholder: '例：销售额:sum; 数量:count' },
        { key: 'prompt', label: '补充说明', type: 'textarea' }
      ]
    },
    'schema-save-excel': {
      icon: '📗', iconClass: 'output',
      title: '保存 Excel', subtitle: '输出节点',
      fields: [
        { key: 'savePath', label: '相对路径或文件名前缀', type: 'input', placeholder: '可选' },
        { key: 'sheetName', label: '工作表名称', type: 'input', placeholder: '默认 Sheet1' },
        { key: 'prompt', label: '备注', type: 'textarea' }
      ]
    },
    'schema-save-text': {
      icon: '📝', iconClass: 'output',
      title: '保存文本', subtitle: '输出节点',
      fields: [
        { key: 'outputEncoding', label: '编码', type: 'select',
          options: [{ value: 'utf-8', label: 'UTF-8' }, { value: 'gbk', label: 'GBK' }] },
        { key: 'lineEnding', label: '换行符', type: 'select',
          options: [{ value: 'lf', label: 'LF (Unix)' }, { value: 'crlf', label: 'CRLF (Windows)' }] },
        { key: 'savePath', label: '文件名或前缀', type: 'input' },
        { key: 'prompt', label: '备注', type: 'textarea' }
      ]
    }
  })

  // ==================== 工具箱（无硬编码值） ====================

  const toolboxItems = ref([
    {
      section: '输入',
      items: [
        {
          icon: '📕', name: 'PDF 输入', type: 'input', title: 'PDF 输入', body: '导入 PDF 文件',
          schemaKey: 'schema-pdf-input',
          schema: null // 动态从 nodeSchemas 获取
        },
        {
          icon: '📝', name: 'MD 输入', type: 'input', title: 'MD 输入', body: '导入 Markdown 文件',
          schemaKey: 'schema-md-input',
          schema: null
        },
        {
          icon: '📄', name: 'TXT 输入', type: 'input', title: 'TXT 输入', body: '导入 TXT 文本文件',
          schemaKey: 'schema-txt-input',
          schema: null
        },
        {
          icon: '📘', name: 'DOCX 输入', type: 'input', title: 'DOCX 输入', body: '导入 Word 文档',
          schemaKey: 'schema-docx-input',
          schema: null
        },
        {
          icon: '📊', name: 'XLSX 输入', type: 'input', title: 'XLSX 输入', body: '导入 Excel 表格数据',
          schemaKey: 'schema-xlsx-input',
          schema: null
        }
      ]
    },
    {
      section: '处理',
      items: [
        {
          icon: '🌍', name: 'AI 翻译', type: 'ai', title: 'AI 翻译', body: '使用大模型进行智能翻译处理',
          schemaKey: 'schema-translate',
          schema: null
        },
        {
          icon: '📋', name: '内容提取', type: 'ai', title: '内容提取', body: '生成摘要和提取关键要点',
          schemaKey: 'schema-extract-summary',
          schema: null
        },
        {
          icon: '📊', name: '数据抽取', type: 'ai', title: '数据抽取', body: '从文档中提取结构化数据',
          schemaKey: 'schema-extract-data',
          schema: null
        },
        {
          icon: '🏷️', name: '实体提取', type: 'ai', title: '实体提取', body: '按字段与自定义实体类型抽取结构化信息',
          schemaKey: 'schema-entity-extraction',
          schema: null
        },
        {
          icon: '📐', name: '数据处理', type: 'ai', title: '数据处理', body: '表格排序、筛选、汇总、去重与列变换',
          schemaKey: 'schema-data-process',
          schema: null
        },
        {
          icon: '🧼', name: '数据清洗', type: 'ai', title: '数据清洗', body: '去空格、格式统一与脏数据规范化',
          schemaKey: 'schema-data-clean',
          schema: null
        },
        {
          icon: '📑', name: '表格提取', type: 'ai', title: '表格提取', body: '从 PDF/Word 等文档中提取表格结构',
          schemaKey: 'schema-table-extract',
          schema: null
        },
        {
          icon: '📈', name: '数据汇总', type: 'ai', title: '数据汇总', body: '按维度统计汇总指标',
          schemaKey: 'schema-data-rollup',
          schema: null
        },
        {
          icon: '🔍', name: '内容分析', type: 'ai', title: '内容分析', body: '关键词提取和实体识别',
          schemaKey: 'schema-analyze-content',
          schema: null
        },
        {
          icon: '✨', name: '文本增强', type: 'ai', title: '文本增强', body: '语法检查、润色和改写',
          schemaKey: 'schema-enhance-text',
          schema: null
        },
        {
          icon: '🔄', name: '格式转换', type: 'ai', title: '格式转换', body: '在多种格式间智能转换',
          schemaKey: 'schema-convert-format',
          schema: null
        },
        {
          icon: '✂️', name: '文档分割', type: 'ai', title: '文档分割', body: '智能分割文档为多个部分',
          schemaKey: 'schema-split-document',
          schema: null
        },
        {
          icon: '🖍️', name: '关键词高亮', type: 'ai', title: '关键词高亮', body: '提取关键词并在结果中标注高亮',
          schemaKey: 'schema-keyword-highlight',
          schema: null
        },
        {
          icon: '🔒', name: '敏感信息脱敏', type: 'ai', title: '敏感信息脱敏', body: '手机号/身份证/邮箱等自动掩码',
          schemaKey: 'schema-sensitive-masking',
          schema: null
        },
        {
          icon: '📚', name: '术语统一替换', type: 'ai', title: '术语统一替换', body: '按词典规范化术语表达',
          schemaKey: 'schema-term-normalize',
          schema: null
        },
        {
          icon: '🧭', name: '结构化提纲生成', type: 'ai', title: '结构化提纲生成', body: '按层级输出目录提纲',
          schemaKey: 'schema-outline-generate',
          schema: null
        },
        {
          icon: '📈', name: '情感倾向分析', type: 'ai', title: '情感倾向分析', body: '输出打分、标签和依据',
          schemaKey: 'schema-sentiment-enhanced',
          schema: null
        },
        {
          icon: '🕒', name: '时间线抽取', type: 'ai', title: '时间线抽取', body: '提取事件并按时间排序',
          schemaKey: 'schema-timeline-extract',
          schema: null
        }
      ]
    },
    {
      section: '输出',
      items: [
        {
          icon: '💾', name: '保存文件', type: 'output', title: '保存文件', body: '保存处理结果到本地文件',
          schemaKey: 'schema-save',
          schema: null
        },
        {
          icon: '📁', name: '输出文件', type: 'output', title: '输出文件', body: '保存结果到文档库或直接下载',
          schemaKey: 'schema-library-output',
          schema: null
        },
        {
          icon: '📗', name: '保存 Excel', type: 'output', title: '保存 Excel', body: '将表格结果保存为 Excel 文件',
          schemaKey: 'schema-save-excel',
          schema: null
        },
        {
          icon: '📝', name: '保存文本', type: 'output', title: '保存文本', body: '将文本结果保存为 txt / md',
          schemaKey: 'schema-save-text',
          schema: null
        }
      ]
    }
  ])

  // ==================== 执行状态 ====================

  const executionStates = ref({})

  function _createEmptyExecutionState() {
    return {
      isExecuting: false,
      executionProgress: 0,
      executionLogs: [],
      outputFiles: [],
      nodeProgress: [],
      currentNodeId: '',
      currentNodeName: '',
      executionId: ''
    }
  }

  function _getExecutionState(workflowId = currentWorkflowId.value) {
    const key = workflowId || '__default__'
    if (!executionStates.value[key]) {
      executionStates.value[key] = _createEmptyExecutionState()
    }
    return executionStates.value[key]
  }

  function getWorkflowExecutionState(workflowId) {
    return executionStates.value[workflowId] || null
  }

  // ==================== 计算属性 ====================

  const currentWorkflow = computed(() =>
    currentWorkflowId.value ? workflows.value[currentWorkflowId.value] : null
  )

  function _normalizeRunConfig(config = {}) {
    const source = config.run || config || {}
    const limit = Number(source.concurrentLimit)
    return {
      concurrentLimit: Number.isFinite(limit) ? Math.min(Math.max(Math.round(limit), 1), 10) : defaultRunConfig.concurrentLimit,
      continueOnError: Boolean(source.continueOnError),
      notifyOnError: source.notifyOnError !== false,
    }
  }

  const currentRunConfig = computed(() => runConfigState.value)

  const customWorkflows = computed(() =>
    Object.values(workflows.value).filter(w => w.type === 'custom')
  )

  const templateWorkflows = computed(() =>
    Object.values(workflows.value).filter(w => w.type === 'template')
  )

  const selectedNode = computed(() =>
    canvasNodes.value.find(n => n.id === selectedNodeId.value)
  )

  const currentExecutionState = computed(() => _getExecutionState(currentWorkflowId.value))
  const isExecuting = computed(() => currentExecutionState.value.isExecuting)
  const executionProgress = computed(() => currentExecutionState.value.executionProgress)
  const executionLogs = computed(() => currentExecutionState.value.executionLogs)
  const outputFiles = computed(() => currentExecutionState.value.outputFiles)
  const nodeProgress = computed(() => currentExecutionState.value.nodeProgress)
  const currentNodeId = computed(() => currentExecutionState.value.currentNodeId)
  const currentNodeName = computed(() => currentExecutionState.value.currentNodeName)
  const executionId = computed(() => currentExecutionState.value.executionId)

  // 文档总数（库选 + 本地）
  const totalDocCount = computed(() =>
    selectedDocs.value.length + localFiles.value.length
  )

  const generatedWorkflowIcons = [
    '🧠', '🧩', '🪄', '🧭', '🧪', '🧮', '📌', '📎',
    '📘', '📗', '📙', '🧾', '📊', '📈', '🔎', '🔐',
    '🌐', '💡', '⚙️', '🚀', '🗂️', '📚', '📝', '💾'
  ]

  const genericWorkflowIcons = new Set(['', '🔧', '⚙️', '🛠️', '📄', '📃', '📁', '📋'])

  function _hashText(text) {
    const value = String(text || '')
    let hash = 2166136261
    for (let i = 0; i < value.length; i++) {
      hash ^= value.charCodeAt(i)
      hash = Math.imul(hash, 16777619)
    }
    return hash >>> 0
  }

  function _resolveWorkflowIcon(workflow = {}) {
    const rawIcon = String(workflow.icon || '').trim()
    const titleText = [
      workflow.name,
      workflow.id,
      ...(workflow.nodes || []).flatMap(n => [n.title, n.name, n.schemaKey, n.type])
    ].join('|').toLowerCase()

    if (titleText.includes('translate') || titleText.includes('翻译')) return '🌍'
    if (titleText.includes('excel') || titleText.includes('xlsx') || titleText.includes('表格')) return '📊'
    if (titleText.includes('pdf')) return '📕'
    if (titleText.includes('word') || titleText.includes('docx')) return '📘'
    if (titleText.includes('txt') || titleText.includes('文本')) return '📝'
    if (titleText.includes('entity') || titleText.includes('实体')) return '🏷️'
    if (titleText.includes('clean') || titleText.includes('清洗')) return '🧼'
    if (titleText.includes('extract') || titleText.includes('提取') || titleText.includes('抽取')) return '🔎'
    if (titleText.includes('summary') || titleText.includes('摘要')) return '📋'
    if (titleText.includes('analy') || titleText.includes('分析')) return '🧠'
    if (titleText.includes('save') || titleText.includes('output') || titleText.includes('保存') || titleText.includes('输出')) return '💾'

    if (!genericWorkflowIcons.has(rawIcon)) return rawIcon
    return generatedWorkflowIcons[_hashText(`${workflow.id || ''}|${workflow.name || ''}`) % generatedWorkflowIcons.length]
  }

  // ==================== API 加载 ====================

  async function loadWorkflows() {
    try {
      const res = await workflowApi.getWorkflows()
      const list = res?.workflows || []
      workflows.value = {}
      list.forEach(w => {
        const workflowIcon = _resolveWorkflowIcon(w)
        workflows.value[w.id] = {
          id: w.id,
          name: w.name,
          icon: workflowIcon,
          time: _formatTime(w.updated_at || w.created_at),
          type: w.type || 'custom',
          nodes: w.nodes || [],           // 完整节点列表（含 configValues、schemaKey）
          edges: w.edges || w.config?.edges || [],
          config: w.config || {},
          created_at: w.created_at || '',
          updated_at: w.updated_at || '',
        }
      })
    } catch (e) {
      console.error('loadWorkflows error:', e)
    }
  }

  async function loadTemplates() {
    try {
      const res = await workflowApi.getTemplates()
      const list = res?.templates || []
      templates.value = list.map(t => {
        const template = {
          id: t.id,
          name: t.name,
          icon: t.icon || '',
          description: t.description || '',
          type: 'template',
          time: '系统预设',
          nodes: t.nodes || [],
          edges: t.edges || t.config?.edges || [],
          config: t.config || {}
        }
        return {
          ...template,
          icon: _resolveWorkflowIcon(template)
        }
      })
      // 合并到 workflows
      templates.value.forEach(t => {
        workflows.value[t.id] = t
      })
    } catch (e) {
      console.error('loadTemplates error:', e)
    }
  }

  async function loadModels() {
    try {
      const res = await workflowApi.getModels()
      availableModels.value = Array.isArray(res) ? res : (res?.models || [])
    } catch (e) {
      console.error('loadModels error:', e)
    }
  }

  async function loadLanguages() {
    try {
      const res = await workflowApi.getLanguages()
      availableLanguages.value = (Array.isArray(res) ? res : []).map(item => ({
        code: item.code,
        label: item.name || item.code
      }))
    } catch (e) {
      console.error('loadLanguages error:', e)
    }
  }

  async function loadOutputFormats() {
    try {
      const res = await workflowApi.getOutputFormats()
      outputFormats.value = (Array.isArray(res) ? res : []).map(item => ({
        code: item.code,
        label: item.name || item.code
      }))
    } catch (e) {
      console.error('loadOutputFormats error:', e)
    }
  }

  // ==================== 工作流操作 ====================

  let workflowSelectVersion = 0
  let workflowLocalEditVersion = 0
  let autoSaveTimer = null
  let autoSaveInFlight = false
  let autoSaveQueued = false
  const AUTO_SAVE_DELAY = 700

  function _canAutoSave() {
    const wf = workflows.value[currentWorkflowId.value]
    return Boolean(wf && wf.type !== 'template')
  }

  function scheduleAutoSave(delay = AUTO_SAVE_DELAY) {
    if (!_canAutoSave()) return
    workflowLocalEditVersion += 1
    if (autoSaveTimer) clearTimeout(autoSaveTimer)
    autoSaveTimer = setTimeout(() => {
      autoSaveTimer = null
      _runAutoSave()
    }, delay)
  }

  async function _runAutoSave() {
    if (!_canAutoSave()) return
    if (autoSaveInFlight) {
      autoSaveQueued = true
      return
    }
    autoSaveInFlight = true
    try {
      await saveCurrentWorkflow()
    } finally {
      autoSaveInFlight = false
      if (autoSaveQueued) {
        autoSaveQueued = false
        scheduleAutoSave(200)
      }
    }
  }

  function _flushPendingAutoSave() {
    if (!autoSaveTimer) return
    clearTimeout(autoSaveTimer)
    autoSaveTimer = null
    _runAutoSave()
  }

  function _mapWorkflowNodes(nodes = []) {
    return (nodes || []).map((n, i) => ({
      ...n,
      x: n.x ?? (30 + i * 260),
      y: n.y ?? 160,
      configValues: {
        ..._defaultConfigForSchemaKey(n.schemaKey),
        ...(n.configValues || {})
      },
      schema: n.schema || nodeSchemas.value[n.schemaKey] || null,
    }))
  }

  function _normalizeWorkflowEdges(nodes = canvasNodes.value, edges = canvasEdges.value) {
    const nodeIds = new Set((nodes || []).map(n => n.id).filter(Boolean))
    const seen = new Set()
    return (edges || [])
      .map(edge => ({
        id: edge.id || `e_${edge.source}_${edge.target}`,
        source: edge.source,
        target: edge.target
      }))
      .filter(edge => {
        if (!edge.source || !edge.target || edge.source === edge.target) return false
        if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) return false
        const key = `${edge.source}->${edge.target}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
  }

  function _linearEdgesForNodes(nodes = canvasNodes.value) {
    return (nodes || []).slice(0, -1).map((node, idx) => {
      const next = nodes[idx + 1]
      return {
        id: `e_${node.id}_${next.id}`,
        source: node.id,
        target: next.id
      }
    })
  }

  function _mapWorkflowEdges(wf = {}, nodes = []) {
    const storedEdges = wf.edges || wf.config?.edges || []
    if (Array.isArray(storedEdges) && storedEdges.length > 0) {
      return _normalizeWorkflowEdges(nodes, storedEdges)
    }
    return _linearEdgesForNodes(nodes)
  }

  function selectWorkflow(workflowId) {
    _flushPendingAutoSave()
    const selectVersion = ++workflowSelectVersion
    const localEditVersionAtSelect = workflowLocalEditVersion
    currentWorkflowId.value = workflowId
    const wf = workflows.value[workflowId]

    if (!wf) {
      workflowName.value = '未命名'
      canvasNodes.value = []
      canvasEdges.value = []
      runConfigState.value = { ...defaultRunConfig }
      selectedNodeId.value = null
      return
    }

    workflowName.value = wf.name || '未命名'
    selectedNodeId.value = null
    runConfigState.value = _normalizeRunConfig(wf.config || {})
    canvasNodes.value = _mapWorkflowNodes(wf.nodes || [])
    canvasEdges.value = _mapWorkflowEdges(wf, canvasNodes.value)

    // 模板工作流（type=template）：nodes已随loadTemplates完整加载，无需调API
    if (wf.type === 'template') {
      return
    }

    // 用户自定义工作流：从数据库获取完整节点
    workflowApi.getWorkflow(workflowId).then(res => {
      if (currentWorkflowId.value !== workflowId || selectVersion !== workflowSelectVersion) return
      if (workflowLocalEditVersion !== localEditVersionAtSelect) return
      const wfData = res || {}
      const nextNodes = wfData.nodes || []
      const nextMappedNodes = _mapWorkflowNodes(nextNodes)
      workflows.value[workflowId] = {
        ...wf,
        ...wfData,
        nodes: nextNodes,
        edges: wfData.edges || wfData.config?.edges || [],
        config: wfData.config || wf.config || {}
      }
      workflowName.value = wfData.name || wf.name || '未命名'
      runConfigState.value = _normalizeRunConfig(workflows.value[workflowId].config || {})
      canvasNodes.value = nextMappedNodes
      canvasEdges.value = _mapWorkflowEdges(workflows.value[workflowId], nextMappedNodes)
      selectedNodeId.value = null
    }).catch(() => {
      if (currentWorkflowId.value !== workflowId || selectVersion !== workflowSelectVersion) return
      workflowName.value = wf.name || '未命名'
      runConfigState.value = _normalizeRunConfig(wf.config || {})
      canvasNodes.value = _mapWorkflowNodes(wf.nodes || [])
      canvasEdges.value = _mapWorkflowEdges(wf, canvasNodes.value)
    })
  }

  async function createNewWorkflow() {
    const id = 'wf_' + Date.now()
    const name = '新建工作流'
    const icon = _resolveWorkflowIcon({ id, name, type: 'custom', nodes: [] })
    workflows.value[id] = {
      id,
      name,
      icon,
      time: '刚刚',
      type: 'custom',
      nodes: [],
      edges: [],
      config: { run: { ...defaultRunConfig } },
    }
    currentWorkflowId.value = id
    workflowName.value = name
    canvasNodes.value = []
    canvasEdges.value = []
    runConfigState.value = { ...defaultRunConfig }
    selectedNodeId.value = null
    // 立即保存到后端
    try {
      await workflowApi.saveWorkflow({
        id,
        name,
        icon,
        type: 'custom',
        nodes: [],
        edges: [],
        config: { run: { ...defaultRunConfig } },
      })
    } catch (e) {
      console.error('createNewWorkflow save error:', e)
    }
  }

  async function saveCurrentWorkflow() {
    if (!currentWorkflowId.value) return
    const wf = workflows.value[currentWorkflowId.value]
    if (!wf) return
    // 节点要保存完整配置：id, type, title, icon, body, schemaKey, configValues
    wf.nodes = canvasNodes.value.map(({ schema, ...rest }) => rest)
    wf.edges = _normalizeWorkflowEdges(canvasNodes.value, canvasEdges.value)
    wf.config = { ...(wf.config || {}), run: _normalizeRunConfig(runConfigState.value || wf.config || {}), edges: wf.edges }
    wf.icon = _resolveWorkflowIcon(wf)
    try {
      await workflowApi.saveWorkflow({
        id: wf.id,
        name: wf.name,
        icon: wf.icon,
        type: 'custom',
        nodes: wf.nodes,
        edges: wf.edges,
        config: wf.config || {},
      })
      wf.time = '刚刚'
    } catch (e) {
      console.error('saveCurrentWorkflow error:', e)
    }
  }

  async function deleteWorkflow(workflowId) {
    try {
      await workflowApi.deleteWorkflow(workflowId)
    } catch (e) {
      console.error('deleteWorkflow error:', e)
      throw e
    }
    delete workflows.value[workflowId]
    delete executionStates.value[workflowId]
    if (currentWorkflowId.value === workflowId) {
      const keys = Object.keys(workflows.value)
      currentWorkflowId.value = keys.length > 0 ? keys[0] : null
      if (currentWorkflowId.value) {
        selectWorkflow(currentWorkflowId.value)
      } else {
        createNewWorkflow()
      }
    }
  }

  // ==================== 节点操作 ====================

  function selectNode(nodeId) {
    selectedNodeId.value = nodeId
  }

  function updateNodePosition(nodeId, x, y) {
    const node = canvasNodes.value.find(n => n.id === nodeId)
    if (node) {
      node.x = x
      node.y = y
      scheduleAutoSave()
    }
  }

  function addEdge(sourceId, targetId) {
    if (!sourceId || !targetId || sourceId === targetId) return false
    const nodeIds = new Set(canvasNodes.value.map(n => n.id))
    if (!nodeIds.has(sourceId) || !nodeIds.has(targetId)) return false
    const exists = canvasEdges.value.some(edge => edge.source === sourceId && edge.target === targetId)
    if (exists) return false
    if (_wouldCreateCycle(sourceId, targetId)) return false
    canvasEdges.value.push({
      id: `e_${sourceId}_${targetId}_${Date.now()}`,
      source: sourceId,
      target: targetId
    })
    scheduleAutoSave()
    return true
  }

  function _wouldCreateCycle(sourceId, targetId) {
    const outgoing = new Map()
    canvasEdges.value.forEach(edge => {
      if (!outgoing.has(edge.source)) outgoing.set(edge.source, [])
      outgoing.get(edge.source).push(edge.target)
    })
    if (!outgoing.has(sourceId)) outgoing.set(sourceId, [])
    outgoing.get(sourceId).push(targetId)
    const stack = [targetId]
    const seen = new Set()
    while (stack.length) {
      const current = stack.pop()
      if (current === sourceId) return true
      if (seen.has(current)) continue
      seen.add(current)
      ;(outgoing.get(current) || []).forEach(next => stack.push(next))
    }
    return false
  }

  function deleteEdge(edgeId) {
    const before = canvasEdges.value.length
    canvasEdges.value = canvasEdges.value.filter(edge => edge.id !== edgeId)
    if (canvasEdges.value.length !== before) scheduleAutoSave()
  }

  function deleteEdgesForNode(nodeId) {
    canvasEdges.value = canvasEdges.value.filter(edge => edge.source !== nodeId && edge.target !== nodeId)
  }

  /** 执行顺序前移一格（在 pipeline 中先执行一步） */
  function moveNodeEarlier(nodeId) {
    const idx = canvasNodes.value.findIndex(n => n.id === nodeId)
    if (idx <= 0) return
    const list = canvasNodes.value
    const item = list[idx]
    list.splice(idx, 1)
    list.splice(idx - 1, 0, item)
    scheduleAutoSave()
  }

  /** 执行顺序后移一格（在 pipeline 中后执行一步） */
  function moveNodeLater(nodeId) {
    const idx = canvasNodes.value.findIndex(n => n.id === nodeId)
    if (idx < 0 || idx >= canvasNodes.value.length - 1) return
    const list = canvasNodes.value
    const item = list[idx]
    list.splice(idx, 1)
    list.splice(idx + 1, 0, item)
    scheduleAutoSave()
  }

  function updateNodeConfig(nodeId, key, value) {
    const node = canvasNodes.value.find(n => n.id === nodeId)
    if (node) {
      if (!node.configValues) node.configValues = {}
      node.configValues[key] = value

      // 特殊处理：inputSource 变化时清空对应数据
      if (key === 'inputSource') {
        if (value === 'library') {
          node.configValues.localFiles = []
          localFiles.value = []
        } else {
          node.configValues.spaceId = null
          selectedDocs.value = []
        }
      }
      scheduleAutoSave()
    }
  }

  function addNode(toolboxItem) {
    const schema = nodeSchemas.value[toolboxItem.schemaKey] || null
    const id = 'n_' + Date.now()
    const lastNode = canvasNodes.value[canvasNodes.value.length - 1]
    const x = lastNode ? lastNode.x + 260 : DEFAULT_NODE_X
    const y = lastNode ? lastNode.y : DEFAULT_NODE_Y
    const configValues = _defaultConfigForSchemaKey(toolboxItem.schemaKey)
    const newNode = {
      id,
      type: toolboxItem.type,
      icon: toolboxItem.icon,
      title: toolboxItem.title,
      body: toolboxItem.body,
      x,
      y,
      configValues,
      schemaKey: toolboxItem.schemaKey,
      schema
    }
    canvasNodes.value.push(newNode)
    if (lastNode) addEdge(lastNode.id, id)
    selectedNodeId.value = id
    scheduleAutoSave()
    return id
  }

  /** 在画布指定坐标放置节点（拖拽落点）；坐标相对于 canvas-inner 左上角 */
  function addNodeAt(toolboxItem, x, y) {
    const schema = nodeSchemas.value[toolboxItem.schemaKey] || null
    const id = 'n_' + Date.now()
    const INNER = CANVAS_SIZE
    const NODE_PLACEHOLDER_W = 216
    const NODE_PLACEHOLDER_H = 100
    const cx = Math.round(Math.min(Math.max(8, x), INNER - NODE_PLACEHOLDER_W - 8))
    const cy = Math.round(Math.min(Math.max(8, y), INNER - NODE_PLACEHOLDER_H - 8))
    const configValues = _defaultConfigForSchemaKey(toolboxItem.schemaKey)
    const newNode = {
      id,
      type: toolboxItem.type,
      icon: toolboxItem.icon,
      title: toolboxItem.title,
      body: toolboxItem.body,
      x: cx,
      y: cy,
      configValues,
      schemaKey: toolboxItem.schemaKey,
      schema
    }
    // 按画布水平位置插入，使连线顺序与从左到右的摆放基本一致
    const dropCenterX = cx + NODE_PLACEHOLDER_W / 2
    let insertAt = canvasNodes.value.length
    for (let i = 0; i < canvasNodes.value.length; i++) {
      const n = canvasNodes.value[i]
      const center = n.x + NODE_PLACEHOLDER_W / 2
      if (dropCenterX < center) {
        insertAt = i
        break
      }
    }
    const previousNode = canvasNodes.value[insertAt - 1]
    const nextNode = canvasNodes.value[insertAt]
    const oldDirectEdge = previousNode && nextNode
      ? canvasEdges.value.find(edge => edge.source === previousNode.id && edge.target === nextNode.id)
      : null
    canvasNodes.value.splice(insertAt, 0, newNode)
    if (oldDirectEdge) deleteEdge(oldDirectEdge.id)
    if (previousNode) addEdge(previousNode.id, id)
    if (nextNode) addEdge(id, nextNode.id)
    selectedNodeId.value = id
    scheduleAutoSave()
    return id
  }

  /** 新节点拖入画布时的默认配置，避免「处理类型」等依赖字段全空导致面板无内容 */
  function _defaultConfigForSchemaKey(schemaKey) {
    switch (schemaKey) {
      case 'schema-xlsx-input':
        return {
          inputSource: 'library',
          spaceId: null,
          sheetIndex: 1,
          hasHeader: true
        }
      case 'schema-extract-summary':
        return {
          extractType: 'summary',
          summaryLength: 'medium',
          prompt: ''
        }
      case 'schema-extract-data':
        return {
          dataFormat: 'json',
          extractFields: '',
          prompt: ''
        }
      case 'schema-analyze-content':
        return {
          analysisType: 'keywords',
          entityTypes: ['person', 'location', 'org', 'date'],
          topK: 10,
          prompt: ''
        }
      case 'schema-enhance-text':
        return {
          enhanceType: 'grammar',
          style: 'concise',
          prompt: ''
        }
      case 'schema-split-document':
        return {
          splitMethod: 'paragraph',
          splitSize: '',
          preserveContext: false,
          prompt: ''
        }
      case 'schema-data-process':
        return {
          processKind: 'dedupe',
          sortOrder: 'asc',
          aggregateOp: 'sum',
          groupByColumns: '',
          dedupeColumns: '',
          fillValue: '0',
          mergeSeparator: ' ',
          splitDelimiter: ',',
          prompt: ''
        }
      case 'schema-data-clean':
        return {
          cleanRules: ['trim_spaces'],
          dateFormatPattern: 'YYYY-MM-DD',
          numberDecimalPlaces: '2',
          prompt: ''
        }
      case 'schema-table-extract':
        return {
          tableStrategy: 'first',
          tableIndex: 1,
          hasHeader: true,
          prompt: ''
        }
      case 'schema-data-rollup':
        return {
          rollupDims: '',
          rollupMetrics: '',
          prompt: '请根据文档内容自动识别可汇总的维度和指标，输出汇总表。'
        }
      case 'schema-entity-extraction':
        return {
          entityFieldList: '名称\n日期\n金额\n机构',
          customEntityTypes: '',
          aliasMap: '',
          prompt: '请从文档中自动识别关键实体，并输出结构化JSON。'
        }
      case 'schema-save':
        return {
          savePath: '',
          outputFormat: 'md'
        }
      case 'schema-library-output':
        return {
          outputMode: 'download',
          targetSpaceId: null,
          namingRule: '{original_name}_out',
          outputFormat: 'md',
          notifyOnComplete: true
        }
      case 'schema-save-excel':
        return {
          savePath: '',
          outputFormat: 'xlsx',
          sheetName: 'Sheet1',
          prompt: ''
        }
      case 'schema-save-text':
        return {
          outputFormat: 'txt',
          outputEncoding: 'utf-8',
          lineEnding: 'lf',
          savePath: '',
          prompt: ''
        }
      case 'schema-convert-format':
        return { targetFormat: 'markdown', conversionOptions: [] }
      default:
        return {}
    }
  }

  function deleteNode(nodeId) {
    const idx = canvasNodes.value.findIndex(n => n.id === nodeId)
    if (idx === -1) return
    deleteEdgesForNode(nodeId)
    canvasNodes.value.splice(idx, 1)
    if (selectedNodeId.value === nodeId) {
      selectedNodeId.value = canvasNodes.value.length > 0
        ? canvasNodes.value[Math.min(idx, canvasNodes.value.length - 1)].id
        : null
    }
    scheduleAutoSave()
  }

  function clearCanvas() {
    canvasNodes.value = []
    canvasEdges.value = []
    selectedNodeId.value = null
    scheduleAutoSave()
  }

  // ==================== 文档操作（从文档库） ====================

  function setSelectedDocs(docs) {
    if (Array.isArray(docs) && docs.length > 0) {
      localFiles.value = []
      const inputNode = _activeInputNode()
      if (inputNode) {
        if (!inputNode.configValues) inputNode.configValues = {}
        inputNode.configValues.inputSource = 'library'
      }
      scheduleAutoSave()
    }
    selectedDocs.value = docs
  }

  function addSelectedDoc(doc) {
    if (!selectedDocs.value.find(d => d.id === doc.id)) {
      localFiles.value = []
      const inputNode = _activeInputNode()
      if (inputNode) {
        if (!inputNode.configValues) inputNode.configValues = {}
        inputNode.configValues.inputSource = 'library'
      }
      selectedDocs.value.push(doc)
      scheduleAutoSave()
    }
  }

  function removeSelectedDoc(docId) {
    selectedDocs.value = selectedDocs.value.filter(d => d.id !== docId)
  }

  function clearSelectedDocs() {
    selectedDocs.value = []
  }

  // ==================== 本地文件操作 ====================

  function addLocalFiles(files) {
    if (!Array.isArray(files) || files.length === 0) return
    selectedDocs.value = []
    const inputNode = _activeInputNode()
    if (inputNode) {
      if (!inputNode.configValues) inputNode.configValues = {}
      inputNode.configValues.inputSource = 'local'
      inputNode.configValues.spaceId = null
    }
    files.forEach(file => {
      if (!localFiles.value.find(f => f.name === file.name && f.size === file.size)) {
        localFiles.value.push({
          id: 'local_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
          name: file.name,
          size: file.size,
          file: file,
          type: file.type
        })
      }
    })
    scheduleAutoSave()
  }

  function removeLocalFile(fileId) {
    localFiles.value = localFiles.value.filter(f => f.id !== fileId)
  }

  function clearLocalFiles() {
    localFiles.value = []
  }

  function _activeInputNode() {
    return canvasNodes.value.find(n => n.id === selectedNodeId.value && n.type === 'input')
      || canvasNodes.value.find(n => n.type === 'input')
      || null
  }

  // ==================== 工作流执行 ====================

  function _sanitizeConfigValue(value) {
    if (Array.isArray(value)) {
      return value
        .map(v => _sanitizeConfigValue(v))
        .filter(v => v !== null && v !== undefined)
    }

    if (value && typeof value === 'object') {
      if (Object.prototype.hasOwnProperty.call(value, 'value')) {
        return value.value
      }
      return value
    }

    if (value === '[object Object]') {
      return null
    }

    return value
  }

  function _sanitizeNodeConfigValues(configValues) {
    const src = configValues || {}
    const out = {}
    Object.keys(src).forEach(k => {
      out[k] = _sanitizeConfigValue(src[k])
    })
    return out
  }

  function _normalizeNodeConfigForExecution(schemaKey, configValues) {
    const out = {
      ..._defaultConfigForSchemaKey(schemaKey),
      ..._sanitizeNodeConfigValues(configValues)
    }
    if (
      schemaKey === 'schema-data-process' &&
      out.processKind === 'sort' &&
      !String(out.sortColumn || '').trim() &&
      !String(out.prompt || '').trim()
    ) {
      return { ...out, processKind: 'dedupe' }
    }
    return out
  }

  async function executeWorkflow() {
    const workflowId = currentWorkflowId.value || '__default__'
    const state = _getExecutionState(workflowId)
    if (state.isExecuting) return

    const nodesSnapshot = canvasNodes.value.map(n => ({
      id: n.id,
      type: n.type,
      title: n.title,
      schemaKey: n.schemaKey,
      configValues: n.configValues
    }))
    const edgesSnapshot = _normalizeWorkflowEdges(canvasNodes.value, canvasEdges.value)
    const inputNodeSnapshot = nodesSnapshot.find(n => n.type === 'input')
    const activeInputSource = inputNodeSnapshot?.configValues?.inputSource || 'library'
    const docsSnapshot = activeInputSource === 'library'
      ? selectedDocs.value.map(d => ({ ...d }))
      : []
    const localFilesSnapshot = activeInputSource === 'local'
      ? localFiles.value.map(f => ({ ...f }))
      : []

    state.executionProgress = 0
    state.executionLogs = []
    state.outputFiles = []
    state.nodeProgress = nodesSnapshot.map((n, idx) => ({
      id: n.id,
      title: n.title,
      type: n.type,
      schemaKey: n.schemaKey,
      index: idx + 1,
      status: 'pending',
      progress: 0,
      message: ''
    }))
    state.currentNodeId = ''
    state.currentNodeName = ''
    state.executionId = ''
    state.isExecuting = true
    if (state.nodeProgress.length > 0) {
      state.nodeProgress[0] = {
        ...state.nodeProgress[0],
        status: 'running',
        progress: 10,
        message: '正在创建执行任务'
      }
      state.currentNodeId = state.nodeProgress[0].id
      state.currentNodeName = state.nodeProgress[0].title
    }
    state.executionLogs.push({ type: 'info', message: '正在创建执行任务...' })

    try {
      // 将本地文件转为 base64 发送（逐字节避免栈溢出）
      const localFilePayloads = await Promise.all(
        localFilesSnapshot.map(async f => {
          if (f.file && f.file.arrayBuffer) {
            const buffer = await f.file.arrayBuffer()
            const bytes = new Uint8Array(buffer)
            let binary = ''
            for (let i = 0; i < bytes.length; i++) {
              binary += String.fromCharCode(bytes[i])
            }
            const base64 = btoa(binary)
            return { name: f.name, size: f.size, content: base64 }
          }
          return { name: f.name, size: f.size }
        })
      )

      // 收集执行参数
      const params = {
        workflowId,
        nodes: nodesSnapshot.map(n => ({
          id: n.id,
          type: n.type,
          title: n.title,
          schemaKey: n.schemaKey,
          configValues: _normalizeNodeConfigForExecution(n.schemaKey, n.configValues)
        })),
        edges: edgesSnapshot,
        config: {
          ...(currentWorkflow.value?.config || {}),
          run: _normalizeRunConfig(currentWorkflow.value?.config || {})
        },
        docs: docsSnapshot.map(d => d.id),
        localFiles: localFilePayloads
      }

      const res = await workflowApi.execute(params)
      state.executionId = res?.execution_id || ''
      if (!state.executionId) {
        throw new Error('后端未返回执行ID')
      }

      // 轮询执行状态
      await pollExecution(workflowId, state.executionId)
    } catch (e) {
      state.executionLogs.push({ type: 'error', message: e.message })
    } finally {
      state.isExecuting = false
    }
  }

  async function pollExecution(workflowId, executionId) {
    const maxPolls = 120
    let polls = 0
    let lastLogCount = 0
    const state = _getExecutionState(workflowId)
    while (polls < maxPolls) {
      try {
        const res = await workflowApi.getExecutionStatus(executionId)
        const status = res?.status
        state.nodeProgress = Array.isArray(res?.node_progress) ? res.node_progress : state.nodeProgress
        state.currentNodeId = res?.current_node_id || ''
        state.currentNodeName = res?.current_node_name || ''
        const failedNode = state.nodeProgress.find(item => item?.status === 'failed')
        if (status === 'completed') {
          state.executionProgress = 100
          state.currentNodeId = ''
          state.currentNodeName = ''
          state.nodeProgress = state.nodeProgress.map(item => (
            item?.status === 'failed'
              ? item
              : { ...item, status: 'completed', progress: 100 }
          ))
          // 追加 output_files
          if (res.output_files && res.output_files.length > 0) {
            res.output_files.forEach(f => {
              state.executionLogs.push({ type: 'done', message: `📥 ${f.name}` })
            })
            state.outputFiles = res.output_files
          }
          state.executionLogs.push({ type: 'done', message: `全部完成，共 ${res.output_files?.length || 0} 个输出文件` })
          break
        } else if (status === 'failed') {
          state.executionLogs.push({ type: 'error', message: res?.error || '执行失败' })
          break
        } else if (failedNode) {
          state.executionLogs.push({ type: 'error', message: failedNode.message || '节点执行失败，工作流已停止' })
          break
        } else {
          state.executionProgress = Number.isFinite(Number(res.progress))
            ? Number(res.progress)
            : Math.round((res.current_file_index / Math.max(res.total_files, 1)) * 100)
          // 只追加新日志（服务器返回完整历史）
          if (res.logs && res.logs.length > lastLogCount) {
            const newLogs = res.logs.slice(lastLogCount)
            newLogs.forEach(log => state.executionLogs.push(log))
            lastLogCount = res.logs.length
          }
        }
      } catch (e) {
        state.executionLogs.push({ type: 'error', message: e.message })
        break
      }
      await new Promise(r => setTimeout(r, 2000))
      polls++
    }
    if (polls >= maxPolls) {
      state.executionLogs.push({ type: 'error', message: '执行超时' })
    }
  }

  // ==================== 辅助方法 ====================

  function setSearchQuery(query) {
    searchQuery.value = query
  }

  function updateWorkflowName(name) {
    workflowName.value = name
    const wf = workflows.value[currentWorkflowId.value]
    if (wf) {
      wf.name = name
      scheduleAutoSave()
    }
  }

  // 根据 schemaKey 获取 schema（用于配置面板动态渲染）
  function updateRunConfig(key, value) {
    const wf = workflows.value[currentWorkflowId.value]
    const run = _normalizeRunConfig(wf?.config || runConfigState.value || defaultRunConfig)
    if (key === 'concurrentLimit') {
      const limit = Number(value)
      run.concurrentLimit = Number.isFinite(limit) ? Math.min(Math.max(Math.round(limit), 1), 10) : defaultRunConfig.concurrentLimit
    } else if (key === 'continueOnError') {
      run.continueOnError = Boolean(value)
    } else if (key === 'notifyOnError') {
      run.notifyOnError = Boolean(value)
    } else {
      run[key] = value
    }
    runConfigState.value = { ...run }
    if (wf) {
      wf.config = { ...(wf.config || {}), run: { ...run } }
    }
    scheduleAutoSave()
  }

  function getSchemaByKey(schemaKey) {
    return nodeSchemas.value[schemaKey] || null
  }

  // 加载翻译模板（预置文档翻译专用模板）
  function loadTranslationTemplate() {
    const templateId = 'tpl_translation'
    workflows.value[templateId] = {
      id: templateId,
      name: '文档翻译流',
      icon: '🌍',
      time: '系统预设',
      type: 'template',
      nodes: [
        {
          id: 'n_pdf',
          type: 'input',
          icon: '📕',
          title: 'PDF 输入',
          body: '导入 PDF 文件',
          configValues: {
            inputSource: 'library',
            spaceId: null,
            skipExisting: false
          },
          schemaKey: 'schema-pdf-input',
          schema: nodeSchemas.value['schema-pdf-input']
        },
        {
          id: 'n_translate',
          type: 'ai',
          icon: '🌍',
          title: 'AI 翻译',
          body: '使用大模型进行智能翻译处理',
          configValues: {
            targetLanguage: 'en',
            prompt: '请将此文档翻译为指定语言，保持原文格式和专业术语的准确性。'
          },
          schemaKey: 'schema-translate',
          schema: nodeSchemas.value['schema-translate']
        },
        {
          id: 'n_output',
          type: 'output',
          icon: '📁',
          title: '输出文件',
          body: '保存结果到文档库或直接下载',
          configValues: {
            outputMode: 'download',
            targetSpaceId: null,
            namingRule: '{original_name}_translated',
            outputFormat: 'pdf',
            notifyOnComplete: true
          },
          schemaKey: 'schema-library-output',
          schema: nodeSchemas.value['schema-library-output']
        }
      ],
      edges: [
        { id: 'e_n_pdf_n_translate', source: 'n_pdf', target: 'n_translate' },
        { id: 'e_n_translate_n_output', source: 'n_translate', target: 'n_output' }
      ],
      config: {}
    }
    currentWorkflowId.value = templateId
    workflowName.value = '文档翻译流'
    canvasNodes.value = [
      {
        ...workflows.value[templateId].nodes[0], x: 30, y: 160
      },
      {
        ...workflows.value[templateId].nodes[1], x: 290, y: 160
      },
      {
        ...workflows.value[templateId].nodes[2], x: 550, y: 160
      }
    ]
    canvasEdges.value = _mapWorkflowEdges(workflows.value[templateId], canvasNodes.value)
    selectedNodeId.value = null
  }

  function _formatTime(dateStr) {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now - date
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)
    if (minutes < 1) return '刚刚'
    if (minutes < 60) return `${minutes}分钟前`
    if (hours < 24) return `${hours}小时前`
    if (days === 1) return '昨天'
    if (days < 7) return `${days}天前`
    return date.toLocaleDateString('zh-CN')
  }

  // ==================== 导出 ====================

  return {
    // 状态
    currentWorkflowId,
    searchQuery,
    workflowName,
    selectedDocs,
    localFiles,
    selectedNodeId,
    selectedNode,
    nodeConfigs,
    nodeSchemas,
    workflows,
    templates,
    toolboxItems,
    canvasNodes,
    canvasEdges,
    availableModels,
    availableLanguages,
    outputFormats,
    unsupportedFieldHints,
    isExecuting,
    executionProgress,
    executionLogs,
    outputFiles,
    nodeProgress,
    currentNodeId,
    currentNodeName,
    executionId,
    getWorkflowExecutionState,
    currentRunConfig,
    // 计算属性
    currentWorkflow,
    customWorkflows,
    templateWorkflows,
    totalDocCount,
    // API 加载
    loadWorkflows,
    loadTemplates,
    loadModels,
    loadLanguages,
    loadOutputFormats,
    // 工作流操作
    selectWorkflow,
    createNewWorkflow,
    saveCurrentWorkflow,
    deleteWorkflow,
    setSearchQuery,
    updateWorkflowName,
    updateRunConfig,
    loadTranslationTemplate,
    // 节点操作
    selectNode,
    updateNodePosition,
    addEdge,
    deleteEdge,
    moveNodeEarlier,
    moveNodeLater,
    updateNodeConfig,
    addNode,
    addNodeAt,
    deleteNode,
    clearCanvas,
    getSchemaByKey,
    // 文档操作
    setSelectedDocs,
    addSelectedDoc,
    removeSelectedDoc,
    clearSelectedDocs,
    // 本地文件
    addLocalFiles,
    removeLocalFile,
    clearLocalFiles,
    // 执行
    executeWorkflow
  }
})
