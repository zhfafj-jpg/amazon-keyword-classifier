# Amazon ABA Keyword Analyzer

这是一个面向长期关键词资产维护的“亚马逊 ABA 关键词库沉淀工具”。第一版不做数据库，也不合并历史词库；它会在每次 ABA 分析后，同时导出：

- 本次 ABA 搜索词分析结果
- 一个标准格式的 `可沉淀关键词库` sheet

后续版本可以基于这个标准 sheet，支持上传历史关键词库并自动合并去重。

## 工具定位

本工具只分析亚马逊 ABA 搜索词表，不处理广告搜索词表、广告投放表、ACOS 表或综合广告动作分析。

当前流程：

产品线/适用产品信息 → 产品信息输入 → 自动识别并确认产品画像 → 上传 ABA 表 → 中文翻译 → 词意图识别 → 多维评分 → S/A/B/C/D 分级 → 导出 Excel 关键词库。

## 文件结构

```text
amazon-aba-keyword-analyzer/
  app.py
  requirements.txt
  README.md
  config/
    default_rules.yaml
  src/
    loader.py
    analyzer.py
    translator.py
    scorer.py
    exporter.py
    utils.py
  sample_data/
    sample_aba_raw.csv
    sample_product_info.txt
```

## 本地运行

```bash
cd amazon-aba-keyword-analyzer
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

macOS/Linux：

```bash
cd amazon-aba-keyword-analyzer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

如果没有设置 Streamlit Secrets，页面会进入本地调试模式并自动放行。

## 如何使用

1. 填写 `产品线`，例如 `M2`、`G3/G4`、`M19`、`通用工具类`。
2. 填写 `适用产品`，可以是产品名称、SKU、ASIN 或产品线内部名称。
3. 来源默认是 `ABA搜索词表`，如需区分批次可改成 `ABA 2026-W25` 等。
4. 在“粘贴产品标题、五点或产品说明”里粘贴产品标题、五点、长描述、卖点、颜色、尺寸、材质、适用场景和不适合人群。
5. 可选填写产品核心词、颜色、尺寸、不相关词、竞品/品牌词。
6. 在“自动识别到的产品画像”区域确认产品类型、是否前仓、是否 trunk、是否 carry on、是否 checked、核心词、颜色词、尺寸词、配件词和品牌词。
7. 上传亚马逊原始 ABA 搜索词表，支持 `.csv` 和 `.xlsx`。
8. 工具会扫描前 50 行，自动跳过报告日期、报告范围、搜索词筛选、Marketplace 等元信息行，并识别真实表头。
9. 搜索词列会默认自动使用，页面只显示识别结果和样例。手动选择功能在“高级设置：手动修正搜索词列”里。
10. 点击“开始分析并生成关键词库”。
11. 预览前 50 行结果并下载 Excel。

## 可沉淀关键词库 Sheet

导出的 Excel 会额外包含一个 `可沉淀关键词库` sheet，用来长期维护关键词资产。字段固定为：

```text
关键词
中文翻译
产品线
适用产品
分类结果
推广优先级
建议动作
搜索频率排名
点击占比
转化份额
转化优势
相关性评分
是否品牌词
是否配件词
是否否词候选
来源
首次发现日期
最近更新日期
备注
```

第一版中，`首次发现日期` 和 `最近更新日期` 都使用本次分析日期。后续版本接入历史关键词库后，可以在合并去重时保留首次发现日期，并更新最近更新日期。

## 导出 Excel Sheet

导出的 Excel 包含：

- 全部ABA词
- S级核心主推词
- A级重点词
- B级低价测试词
- C级Listing埋词
- D级不相关否词
- 品牌竞品词
- 待人工确认
- 可沉淀关键词库
- 否词候选库
- 规则说明

## 新增评分字段

- 词意图类型：核心类目词、精准长尾词、尺寸词、颜色词、功能词、场景词、泛类目词、品牌/竞品词、配件词、套装词、不同品类词、明显不相关词、待人工确认。
- 产品相关性评分：判断搜索词和当前产品画像是否匹配。
- 需求评分：根据 Search Frequency Rank 计算，排名越靠前分数越高。
- 点击转化效率评分：根据点击占比、转化份额和转化优势计算；数据缺失时显示为空或数据不足。
- 风险评分：品牌词、配件词、套装词、不同品类词、不相关词会提高风险。
- 综合优先级评分：产品相关性权重最高，其次需求和点击转化效率，风险作为扣分项。
- 为什么这样分类：给出一句可读解释，例如命中配件词、命中套装词但当前产品不是套装、产品为 carry on 且搜索词高度匹配等。
- 是否进入关键词库：S/A/C 默认进入，B 视风险判断，D 进入否词候选库，品牌词进入品牌竞品词库。
- 词库类型：核心词库、测试词库、Listing埋词库、品牌竞品词库、否词候选库、待确认库。

## 如何理解分级

- S级核心主推词：相关性高，ABA 排名较好，转化份额不低于点击占比，适合 Exact / Phrase 主推。
- A级重点词：相关性较高，有一定搜索量，转化表现不差，适合重点广告组测试。
- B级低价测试词：相关性中等，点击较强但成交偏弱，或搜索量有价值但意图偏泛，适合低价测试。
- C级Listing埋词：产品相关，偏功能、材质、场景、属性，不适合主预算但适合标题、五点、A+、Search Terms。
- D级不相关/否词：相关性低，或命中配件词、不相关词、不同品类词，建议不投放或作为否词候选。
- 品牌/竞品词：命中品牌词库，单独做品牌词测试或竞品分析，不进入普通核心主推词。
- 待人工确认：数据不足或程序无法明确判断。

## ABA 指标说明

- 点击占比：该搜索词下点击被某些商品拿走的比例，可理解为点击集中度。
- 转化份额：该搜索词下购买转化被某些商品拿走的比例。
- 转化优势：`转化份额 - 点击占比`。大于 0 通常说明成交效率强，小于 0 说明点击强但成交偏弱。
- 需求评分：根据 Search Frequency Rank 判断，排名越靠前需求越高。

## Streamlit Cloud 部署

1. 将整个 `amazon-aba-keyword-analyzer` 目录上传到 GitHub。
2. 在 Streamlit Cloud 新建 App。
3. Main file path 填写：

```text
app.py
```

4. 在 App 的 Secrets 中添加：

```toml
APP_PASSWORD = "your-password-here"
```

5. 保存并重新部署。

## 修改规则词库

打开：

```text
config/default_rules.yaml
```

可以修改：

- `brand_terms`：品牌/竞品词库
- `accessory_terms`：配件词库
- `different_category_terms`：不同品类/明显不相关词
- `functional_terms`：功能词
- `scene_terms`：场景词
- `translation_terms`：内置中文翻译词典

修改后重新运行 Streamlit 即可生效。

## 测试数据

- `sample_data/sample_product_info.txt`：示例产品信息
- `sample_data/sample_aba_raw.csv`：模拟亚马逊 ABA 原始导出格式，前几行包含报告日期、报告范围、搜索词筛选等元信息，后面才是真实表头和搜索词数据
