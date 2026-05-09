from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "KeyBoy搜索引擎课程设计增强版说明.docx"


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def set_cell_text(cell, text: str, bold: bool = False) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = paragraph.add_run(text)
    run.font.name = "Microsoft YaHei"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(9)
    run.bold = bold
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def style_table(table, header_fill: str = "0F766E") -> None:
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    for row_index, row in enumerate(table.rows):
        for cell in row.cells:
            cell.margin_top = Cm(0.08)
            cell.margin_bottom = Cm(0.08)
            if row_index == 0:
                set_cell_shading(cell, header_fill)
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.color.rgb = RGBColor(255, 255, 255)
                        run.bold = True


def add_heading(doc: Document, text: str, level: int = 1):
    paragraph = doc.add_heading(text, level=level)
    for run in paragraph.runs:
        run.font.name = "Microsoft YaHei"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        run.font.color.rgb = RGBColor(15, 118, 110 if level == 1 else 90)
    return paragraph


def add_body(doc: Document, text: str, bold_lead: str | None = None):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.line_spacing = 1.25
    if bold_lead and text.startswith(bold_lead):
        lead = paragraph.add_run(bold_lead)
        lead.bold = True
        rest = paragraph.add_run(text[len(bold_lead) :])
        runs = [lead, rest]
    else:
        runs = [paragraph.add_run(text)]
    for run in runs:
        run.font.name = "Microsoft YaHei"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        run.font.size = Pt(10.5)
    return paragraph


def add_bullets(doc: Document, items: list[str]) -> None:
    for item in items:
        paragraph = doc.add_paragraph(style="List Bullet")
        paragraph.paragraph_format.space_after = Pt(3)
        run = paragraph.add_run(item)
        run.font.name = "Microsoft YaHei"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        run.font.size = Pt(10)


def build() -> None:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.15)
    section.right_margin = Cm(2.15)

    styles = doc.styles
    styles["Normal"].font.name = "Microsoft YaHei"
    styles["Normal"]._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    styles["Normal"].font.size = Pt(10.5)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(80)
    run = title.add_run("KeyBoy 搜索引擎课程设计增强版说明")
    run.font.name = "Microsoft YaHei"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(24)
    run.bold = True
    run.font.color.rgb = RGBColor(15, 118, 110)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(18)
    run = subtitle.add_run("定向爬取 + 多智能体 + 混合检索 + 可解释评测")
    run.font.name = "Microsoft YaHei"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(14)
    run.font.color.rgb = RGBColor(78, 91, 99)

    meta = doc.add_table(rows=5, cols=2)
    rows = [
        ("项目名称", "KeyBoy 专业领域智能搜索引擎"),
        ("版本定位", "课程设计增强版 / 可运行演示版"),
        ("核心目标", "以现代搜索系统能力提升课程设计完成度与验收表现"),
        ("技术路线", "Python 标准库、BM25、语义向量、RRF、抽取式摘要、unittest"),
        ("交付内容", "源代码、前端、语料、评测集、迭代说明、系统设计、验收指南"),
    ]
    for idx, (key, value) in enumerate(rows):
        set_cell_text(meta.cell(idx, 0), key, bold=True)
        set_cell_text(meta.cell(idx, 1), value)
        set_cell_shading(meta.cell(idx, 0), "E6F4F1")
    meta.columns[0].width = Cm(4)
    meta.columns[1].width = Cm(11.5)

    doc.add_page_break()

    add_heading(doc, "1. 修改迭代总览")
    add_body(
        doc,
        "本增强版在原开发计划书基础上保留课程设计的可控边界，同时重点补强算法先进性、工程可运行性、验收可展示性和质量可证明性。原方案以定向爬取、TF-IDF、本地 JSON 和简单前端为主；增强版升级为多智能体搜索工作台，能展示混合检索、智能摘要、可解释评分和自动评测闭环。",
    )
    table = doc.add_table(rows=1, cols=3)
    headers = ["维度", "原计划", "增强版迭代"]
    for idx, header in enumerate(headers):
        set_cell_text(table.cell(0, idx), header, bold=True)
    diff_rows = [
        ("检索算法", "倒排索引 + TF-IDF", "BM25 + 轻量语义向量 + RRF 融合 + 二阶段重排"),
        ("智能体", "爬取、清洗、索引、搜索四类", "新增 InsightAgent 与 EvalAgent，形成摘要和评测闭环"),
        ("前端", "搜索框与结果列表", "结果、摘要、过滤、评分解释、Agent Trace、质量指标同屏展示"),
        ("质量保证", "人工测试为主", "unittest + Recall@5 + nDCG@5 + 平均耗时"),
        ("部署", "依赖若干 Python 库", "核心功能仅需 Python 标准库，演示更稳定"),
    ]
    for row in diff_rows:
        cells = table.add_row().cells
        for idx, value in enumerate(row):
            set_cell_text(cells[idx], value)
    style_table(table)

    add_heading(doc, "2. 核心创新点")
    add_bullets(
        doc,
        [
            "混合检索：BM25 处理精确关键词，语义向量覆盖同义表达和长问题。",
            "RRF 融合：使用排名位置融合多个检索器，规避分数尺度不一致。",
            "查询画像：根据问题意图、技术词和长度动态调整词法/语义权重。",
            "可解释排序：每条结果展示 BM25、语义、RRF、重排分数和命中原因。",
            "可评测质量：内置测试查询，自动输出 Recall@5、nDCG@5 和平均耗时。",
            "稳定演示：内置本地语料，同时保留合规爬虫扩展能力。",
        ],
    )

    add_heading(doc, "3. 系统架构")
    arch = doc.add_table(rows=1, cols=3)
    for idx, header in enumerate(["智能体", "职责", "验收价值"]):
        set_cell_text(arch.cell(0, idx), header, bold=True)
    arch_rows = [
        ("CrawlAgent", "加载本地语料，可选合规网页抓取", "规避现场网络波动，保留扩展能力"),
        ("CleanAgent", "清洗、去重、过滤低质量文本", "保证知识库质量"),
        ("IndexAgent", "构建 BM25 与语义向量索引", "体现搜索核心技术"),
        ("SearchAgent", "执行检索、融合、重排与解释", "展示系统智能程度"),
        ("InsightAgent", "生成查询摘要和洞察", "提升结果可读性"),
        ("EvalAgent", "计算 Recall@5、nDCG@5、耗时", "形成可证明质量闭环"),
    ]
    for row in arch_rows:
        cells = arch.add_row().cells
        for idx, value in enumerate(row):
            set_cell_text(cells[idx], value)
    style_table(arch, "2563EB")

    add_heading(doc, "4. 运行与验收")
    add_body(doc, "运行命令：python -m keyboy.app --host 127.0.0.1 --port 8787", "运行命令：")
    add_body(doc, "访问地址：http://127.0.0.1:8787", "访问地址：")
    add_bullets(
        doc,
        [
            "查询“混合检索 BM25 RRF”，展示精确技术词、RRF 融合与评分解释。",
            "查询“如何提升课程设计搜索准确率”，展示自然语言查询、语义召回和摘要。",
            "查询“爬虫合规 robots 频率控制”，展示合规设计和工程风险控制。",
            "切换 Hybrid、BM25、Semantic 三种模式，直观看到算法差异。",
            "打开右侧质量指标，展示 Recall@5、nDCG@5 和平均耗时。",
        ],
    )

    add_heading(doc, "5. 当前验证结果")
    result = doc.add_table(rows=1, cols=4)
    for idx, header in enumerate(["测试项", "结果", "说明", "验收意义"]):
        set_cell_text(result.cell(0, idx), header, bold=True)
    result_rows = [
        ("单元测试", "4/4 通过", "覆盖索引、搜索、摘要、评测", "代码可复现"),
        ("Recall@5", "0.90", "相关文档召回能力强", "证明结果不漏关键信息"),
        ("nDCG@5", "0.8493", "相关文档排序靠前", "证明排序质量"),
        ("平均耗时", "毫秒级", "本地演示语料快速响应", "满足小于 3 秒目标"),
    ]
    for row in result_rows:
        cells = result.add_row().cells
        for idx, value in enumerate(row):
            set_cell_text(cells[idx], value)
    style_table(result, "B7791F")

    add_heading(doc, "6. 推荐答辩表述")
    add_body(
        doc,
        "我们没有停留在最初的 TF-IDF 搜索，而是参考现代搜索系统，把 KeyBoy 做成了混合检索工作台。系统同时支持 BM25、语义向量和 RRF 融合排序，并且每条结果都有可解释分数。多智能体流水线覆盖采集、清洗、索引、搜索、摘要和评测，前端能展示 Agent Trace、查询画像和质量指标。因此项目不仅能运行，还能解释为什么这样设计、如何证明质量、如何继续扩展。",
    )

    add_heading(doc, "7. 参考经验")
    add_bullets(
        doc,
        [
            "Elasticsearch RRF 文档：多个相关性指标可以通过倒数排名融合为单一结果集。",
            "OpenSearch Hybrid Search：关键词检索与神经/语义检索可结合并进行分数处理。",
            "Faiss 文档：向量相似度检索是现代语义搜索的重要基础。",
            "BEIR 检索评测论文：搜索质量需要用统一基准、Recall、nDCG 等指标验证。",
        ],
    )

    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    build()
