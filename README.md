# Amazon Keyword Classifier

一个适合部署到 Streamlit Cloud 的亚马逊关键词词库分类工具。第一版目标是：

上传表格 → 自动识别关键词列 → 按产品线规则分类 → 预览结果 → 导出整理后的 Excel。

## 功能

- 支持 `.xlsx` 和 `.csv`
- 支持常见中文/英文列名识别
- 支持手动选择关键词列
- 支持产品线：`M19`、`M2`、`G3/G4`、`通用工具类`
- 支持分析模式：`ABA选词`、`广告搜索词`、`综合分析`
- 产品规则存放在 `config/product_rules.yaml`
- 内置品牌词、配件词、不相关词和产品线适配规则
- 可导出 Excel，多 sheet 拆分分类结果
- 支持 Streamlit secrets 密码保护

## 文件结构

```text
amazon-keyword-classifier/
  app.py
  requirements.txt
  README.md
  config/
    product_rules.yaml
  src/
    __init__.py
    loader.py
    classifier.py
    scorer.py
    exporter.py
    utils.py
  sample_data/
    sample_keywords.csv
```

## 本地运行

建议使用 Python 3.10+。

```bash
cd amazon-keyword-classifier
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

macOS/Linux：

```bash
cd amazon-keyword-classifier
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

如果没有配置 Streamlit secrets，应用会进入本地调试模式并自动放行。

## Streamlit Cloud 部署

1. 将整个 `amazon-keyword-classifier` 项目上传到 GitHub 仓库。
2. 在 Streamlit Cloud 新建 App。
3. Main file path 填写：

```text
app.py
```

4. 在 Streamlit Cloud 的 Secrets 中添加密码：

```toml
APP_PASSWORD = "your-password-here"
```

5. 部署后访问页面，输入密码即可使用。

## 如何修改产品规则

打开：

```text
config/product_rules.yaml
```

每个产品线包含：

- `colors`：适配颜色
- `sizes`：尺寸/规格词
- `core_terms`：核心主推词
- `unsuitable_terms`：不适合该产品线的词

示例：

```yaml
M19:
  colors: [black, green, brown, purple, beige]
  sizes: [20 inch, 26 inch, 30 inch, medium, large, checked]
  core_terms: [trunk luggage, trunk suitcase]
  unsuitable_terms: [pink, front pocket, laptop compartment]
```

## 如何添加品牌词

在 `config/product_rules.yaml` 里修改：

```yaml
global_terms:
  brand_terms: [samsonite, rimowa, away]
```

命中品牌词的关键词会被标记为 `品牌词/竞品词`，不会直接进入普通主推词。

## 如何添加否词规则

可以在两个地方添加：

1. 全局配件/不相关词：

```yaml
global_terms:
  accessory_terms: [luggage cover, replacement wheel]
```

2. 某个产品线的不适合词：

```yaml
product_lines:
  M19:
    unsuitable_terms: [pink, front pocket, laptop compartment]
```

## 上传表格并下载结果

1. 打开网页。
2. 上传 `.xlsx` 或 `.csv`。
3. 选择产品线。
4. 选择分析模式。
5. 如果工具没有自动识别关键词列，请手动选择。
6. 点击 `开始分析`。
7. 在页面预览分类结果。
8. 点击 `下载 Excel`。

导出的 Excel 包含：

- 全部关键词
- 核心主推词
- 低价测试词
- Listing埋词
- 词组否定建议
- 精准否定建议
- 品牌词_竞品词
- 待人工确认
- 规则命中说明

说明：Excel 工作表名称不允许使用 `/`，所以导出 sheet 使用 `品牌词_竞品词`，分类结果字段仍显示为 `品牌词/竞品词`。

## 样例数据

可用以下文件测试：

```text
sample_data/sample_keywords.csv
```

建议分别选择 `M19`、`M2`、`G3/G4` 做对比测试。例如 `pink trunk luggage` 对 M19 会被识别为不适合颜色，而 `pink carry on luggage` 对 M2 不会被误判为不相关。
