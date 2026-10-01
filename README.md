# 自测生成系统（test-builder）— 智能刷题系统生成工具

全程AI制作，功能还没有完善。

自测生成系统（test-builder）是一个 **零第三方依赖** 的 Python 工具（Tool）。它接收任意格式的原始题库
（纯文本 / Markdown / CSV / Excel），自动完成「解析 → 归一化 → 校验 → 去重 → 标准 JSON →
嵌入 HTML 模板」的全流程，最终产出一个 **可直接双击打开** 的 HTML 刷题系统。

生成结果在功能、界面、交互体验上与参考项目
`毛概自测系统/毛概选择题自测v1.2_20250624_182738.html` **完全一致**（模板逐字节复用，
仅替换题库数据与标题/章节/公告等展示字段）。

---

## 1. 核心特性

| 能力 | 说明 |
| --- | --- |
| 多格式解析 | `.json` `.txt` `.text` `.md` `.markdown` `.csv` `.tsv` `.xlsx` `.xls` |
| 图形界面 | tkinter 图形界面：多选文件 / 文件夹一键导入，自动校验并一键生成 |
| 免环境 exe | `build_exe.py` 打包成单文件 exe，内置解释器与模板，用户无需安装 Python |
| 深度学习语义解析 | 通过 OpenAI 兼容的 Chat Completions 接口调用 Transformer 大模型，处理脏数据/长尾排版 |
| 规则解析兜底 | LLM 不可用时自动降级为本地正则解析，任何环境都能出结果 |
| 混合召回 | 规则 + LLM 双通道，按题干归一化 key 去重合并 |
| 标准 JSON 转换 | 严格遵循参考项目字段规范，自动归一化选项字母、答案、题型、章节 |
| 自动化 HTML 嵌入 | 占位符模板注入，无人工干预 |
| 题库去重 / 校验 | 自动去重、字段完整性校验、`option[0]` 与判分约定一致性保障 |
| 扩展性 | 题型自动识别：单选 `single` / 多选 `multi` / 判断 `judge` |

---

## 2. 目录结构

```
test-builder/
├─ app.py                     # 统一入口：无参数启动 GUI，带参数走 CLI（打包入口）
├─ run.py                     # 便捷入口（等价于 python -m agent）
├─ build_exe.py               # PyInstaller 打包脚本 -> dist/test-builder.exe
├─ README.md                  # 本文件
├─ agent/
│  ├─ __init__.py             # 版本号
│  ├─ __main__.py             # python -m agent 入口
│  ├─ gui.py                  # tkinter 图形界面
│  ├─ cli.py                  # 命令行：build / parse / validate
│  ├─ schema.py               # 标准数据结构与校验
│  ├─ normalize.py            # 归一化算法（选项/答案/题型/章节）
│  ├─ pipeline.py             # 主流程编排 + 构建报告 + 导入校验
│  ├─ builder.py              # HTML 模板注入（兼容 PyInstaller _MEIPASS）
│  ├─ templates/
│  │  └─ quiz_template.html   # 从参考项目提取的占位符化模板
│  └─ parsers/
│     ├─ base.py              # 解析器基类 + 支持的后缀
│     ├─ text_parser.py       # 纯文本解析
│     ├─ markdown_parser.py   # Markdown / Markdown 表格解析
│     ├─ table_parser.py      # CSV / TSV / 通用表格解析
│     ├─ xlsx_reader.py       # 零依赖 Excel 读取（zipfile + XML）
│     ├─ json_parser.py       # JSON 题库解析
│     ├─ dl_parser.py         # 深度学习(LLM)语义解析 + 混合解析
│     └─ __init__.py          # 解析器分发
├─ samples/                   # 演示题库（json / txt / md / csv / xlsx）
├─ output/                    # 生成的 HTML 刷题系统
└─ dist/                      # 打包产物 test-builder.exe
```

---

## 3. 环境要求

- Python **3.8+**（仅使用标准库，**无需 pip install 任何依赖**）
- 可选：一个 OpenAI 兼容的大模型 API Key（用于开启深度学习解析通道）

---

## 4. 快速开始

```powershell
# 1) 进入项目目录
cd \test-builder

# 2) 一条命令把 samples/ 下所有题库合成一个刷题系统
python run.py build -i samples -o output/demo.html --title "毛泽东思想与中国特色社会主义理论体系概论 自测系统"

# 3) 打开生成的 HTML
start output\demo.html
```

输出示例：

```
自测生成系统 v1.0.0
输入 3 个文件，LLM 通道：关闭（规则模式）
------------------------------------------------
共 24 道题
题型分布：single=10, multi=7, judge=7
章节分布：第1章=6, 第2章=6, 第3章=2, 第5章=7, 第6章=1, 第7章=1, 第9章=1
解析通道：table, hybrid, hybrid
输出文件：output\demo.html
警告 2 条：
  - [sample_table.md] LLM 通道未配置 API Key，仅使用规则解析（降级模式）。
  - [sample_text.txt] LLM 通道未配置 API Key，仅使用规则解析（降级模式）。
```

---

## 5. 命令行用法

### 5.1 `build` — 生成 HTML 刷题系统

```
python run.py build [选项]
```

| 选项 | 说明 |
| --- | --- |
| `-c, --config PATH` | 读取 JSON 配置文件（相对路径以配置文件所在目录为基准） |
| `-i, --input PATH [PATH ...]` | 题库文件或目录，可传多个；目录会递归收集受支持的后缀 |
| `-o, --output PATH` | 输出 HTML 路径（默认 `output/quiz.html`） |
| `--title TEXT` | 页面标题（覆盖配置文件） |
| `--subtitle TEXT` | 副标题 / 页脚署名 |
| `--announcement TEXT [TEXT ...]` | 公告内容，每一项渲染为一段 |
| `--update-url URL` | "获取最新版" 按钮的跳转地址 |
| `--template PATH` | 使用自定义 HTML 模板 |
| `--no-llm` | 强制关闭 LLM，仅用规则解析 |
| `--keep-duplicates` | 保留重复题目（默认自动去重） |
| `--strict` | 遇到无法解析的题目直接报错（默认跳过并警告） |

示例：

```powershell
python run.py build -i samples/sample_text.txt samples/sample_table.csv -o output/mine.html ^
  --title "我的刷题系统" --subtitle "自测@我" ^
  --announcement "本系统由 自测生成系统 自动生成" "题目数据仅供练习参考" ^
  --update-url "https://example.com/latest"
```

### 5.2 `parse` — 只输出标准 JSON

不生成 HTML，仅把原始题库解析为标准 JSON 并打印到标准输出，便于人工检查或二次开发：

```powershell
python run.py parse -i samples
```

```powershell
# 保存到文件
python run.py parse -i samples > output/questions.json
```

### 5.3 `validate` — 仅做导入校验

解析题库并逐题做结构校验（题干、选项、答案、题型），**不生成 HTML**，用于导入前自检。
退出码 `0` 表示全部文件通过，`1` 表示存在校验失败的文件：

```powershell
python run.py validate -i samples
```

```
自测生成系统 v1.0.0 · 题库导入校验
------------------------------------------------------------
[通过] samples\sample_json.json
        解析通道 json | 解析 6 题 | 有效 6 题 | 异常 0 题 | 6 题全部有效
[通过] samples\sample_excel.xlsx
        解析通道 excel | 解析 3 题 | 有效 3 题 | 异常 0 题 | 3 题全部有效
------------------------------------------------------------
文件 5 个（通过 5） | 有效题目 33 题 | 异常题目 0 题
```

---

## 6. 配置文件

`build` 支持用 JSON 配置文件集中管理参数（命令行参数优先级更高）。

```json
{
  "title": "毛泽东思想与中国特色社会主义理论体系概论 自测系统",
  "subtitle": "自测系统@千纸鹤",
  "announcement": [
    "本系统由 自测生成系统 自动生成",
    "支持 txt / Markdown / CSV / Excel 多种题库格式",
    "题目数据仅供练习参考"
  ],
  "update_url": "https://pan.baidu.com/",
  "chapters": {
    "1": "毛泽东思想及其历史地位",
    "2": "新民主主义革命理论"
  },
  "input": ["samples"],
  "output": "output/demo_quiz.html",
  "llm": {
    "enabled": true,
    "base_url": "https://api.openai.com/v1",
    "api_key_env": "QUIZ_LLM_API_KEY",
    "model": "gpt-4o-mini",
    "mode": "hybrid"
  }
}
```

```powershell
python run.py build -c config.json
```

说明：
- `chapters` 不填时，会根据题目数据自动生成章节下拉选项（`第N章`）。
- `input` / `output` 的相对路径以 **配置文件所在目录** 为基准解析。
- `api_key` 可直接写，也可用 `api_key_env` 指定读取的环境变量名（默认 `QUIZ_LLM_API_KEY`）。

---

## 7. 支持的原始题库格式

### 7.1 纯文本（`.txt` / `.text`）

题号、选项前缀、答案标记都可松散书写，解析器会自动识别：

```
第一章 毛泽东思想及其历史地位

1. 毛泽东思想形成和发展的时代背景是()
A.中国沦为半殖民地半封建社会
B.帝国主义战争和无产阶级革命
C.第一次世界大战的爆发
D.中国工人阶级的成长壮大
答案：B

3、毛泽东思想活的灵魂包括（） A.实事求是 B.群众路线 C.独立自主 D.统一战线 答案：ABC

4. 毛泽东思想是……集体智慧的结晶。这一论断是否正确？
A.正确
B.错误
答案：A
```

支持的写法：
- 题号：`1.` `1、` `(1)` `【1】` `第1题` `一、`
- 选项前缀：`A.` `A、` `A）` `（A）` `【A】` `A：`
- 答案标记：`答案：A` `正确答案：ABC` `参考答案：A` `【答案】A` `答案：正确` `答案：对/错/√/×`
- 章节标题：`第一章 xxx` / `第1章 xxx` 自动作为后续题目的 `chapter`

### 7.2 Markdown（`.md` / `.markdown`）

既支持 Markdown 表格（见 7.3），也支持与纯文本相同的列表式写法。

### 7.3 表格（`.csv` / `.tsv` / `.xlsx` / `.xls`）

首行为表头，列名可用中英文别名：

| 题干 | 选项A | 选项B | 选项C | 选项D | 答案 | 题型 | 章节 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 社会主义改造的三大改造对象包括（） | 个体农业 | 个体手工业 | 资本主义工商业 | 官僚资本主义 | ABC | multi | 3 |
| 实事求是是党的思想路线的核心。 | 正确 | 错误 |  |  | A | judge | 1 |

列名别名：
- 题干：`题干` `题目` `问题` `question` `stem`
- 选项：`选项A` `A` `optionA` …（也支持 `选项1` 或一整列 `选项`，用分隔符拆开）
- 答案：`答案` `正确答案` `answer`
- 题型：`题型` `类型` `type`（可选，缺省自动推断）
- 章节：`章节` `章` `chapter`（可选）

> Excel 读取使用标准库 `zipfile` + `xml.etree` 直接解析 `.xlsx`，无需安装 `openpyxl`。

### 7.4 JSON（`.json`）

支持三种顶层结构：

```json
// ① 题目数组
[
  {"chapter": 2, "type": "single", "question": "……()", "options": ["农民阶级", "无产阶级"], "answer": "B"}
]
```

```json
// ② 带 questions 字段的对象（可附带 title / announcement 等元信息）
{
  "title": "我的题库",
  "questions": [
    {"question": "……()", "options": {"A": "选项一", "B": "选项二"}, "answer": "A"}
  ]
}
```

```json
// ③ 单个题目对象
{"question": "……()", "options": ["正确", "错误"], "answer": "A"}
```

字段别名（中英文均可，大小写不敏感）：
- 题干：`question` `stem` `title` `content` `题干` `题目` `问题` `试题`
- 选项：`options` `choices` `选项`；取值支持 **数组**、**对象** `{"A": "...", "B": "..."}`、**合并字符串** `"A.甲 B.乙"`
- 答案：`answer` `key` `correct` `答案` `正确答案`（单选/判断为 `"B"`，多选可为 `"ABC"` 或 `["A","B","C"]`）
- 题型：`type` `qtype` `题型`（缺省自动推断）
- 章节：`chapter` `section` `章节`（缺省为 1）

> JSON 语法错误会给出**具体行号与列号**，便于快速定位。

---

## 8. 标准 JSON 数据结构

`parse` 子命令与 HTML 内嵌的数据块都使用统一结构（与参考项目完全一致）：

```json
[
  {
    "id": 1,
    "chapter": 2,
    "type": "single",
    "question": "新民主主义革命的总路线中，革命的领导力量是()",
    "options": ["A.农民阶级", "B.无产阶级", "C.资产阶级", "D.小资产阶级"],
    "answer": "B"
  },
  {
    "id": 3,
    "chapter": 3,
    "type": "multi",
    "question": "社会主义改造的三大改造对象包括（）",
    "options": ["A.个体农业", "B.个体手工业", "C.资本主义工商业", "D.官僚资本主义"],
    "answer": ["A", "B", "C"]
  },
  {
    "id": 5,
    "chapter": 5,
    "type": "judge",
    "question": "我国社会主义初级阶段的基本国情没有变。",
    "options": ["A.正确", "B.错误"],
    "answer": "A"
  }
]
```

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `id` | int | 从 1 连续递增，由构建器自动回填 |
| `chapter` | int | 章节号（整数） |
| `type` | string | `single` / `multi` / `judge` |
| `question` | string | 题干，不含题号与答案标记 |
| `options` | string[] | **`options[i][0]` 必须等于对应选项字母 `A/B/C...`** |
| `answer` | string \| string[] | `single`/`judge` 为单个字母；`multi` 为字母数组 |

> **关键约定**：参考项目的判分逻辑依赖 `option[0]` 与选项字母一致
> （`selectedOption.startsWith(question.answer)`、`options[idx][0]`）。
> 自测生成系统的归一化模块会无条件保证该约定成立。

---

## 9. 深度学习解析通道（可选）

`dl_parser.py` 中的"深度学习"能力来自 **预训练的 Transformer 大语言模型**：
通过 OpenAI 兼容的 `/chat/completions` 接口，让模型把非结构化原始题库直接
"翻译"成标准题目 JSON，从而正确处理排版混乱、中英混排、答案与题干粘连等长尾情况。

> 说明：本模块不包含"从零训练模型"的代码（那需要标注数据与 GPU），而是调用现成的
> Transformer 模型 —— 这也是工业界落地的主流做法。规则通道始终作为兜底，保证离线可用。

配置方式（任选其一）：

```powershell
# 方式一：环境变量
set QUIZ_LLM_API_KEY=sk-xxxx
set QUIZ_LLM_BASE_URL=https://api.openai.com/v1
set QUIZ_LLM_MODEL=gpt-4o-mini
set QUIZ_LLM_MODE=hybrid
python run.py build -i samples -o output/demo_quiz.html
```

```powershell
# 方式二：命令行 --no-llm 强制关闭；不加则自动尝试 LLM，失败降级
python run.py build -i samples -o output/demo_quiz.html --no-llm
```

解析模式 `mode`：
- `hybrid`（默认）：规则 + LLM 双通道，去重合并
- `llm`：仅 LLM（失败会降级并告警）
- `rule`：仅规则（等价于 `--no-llm`）

---

## 10. Python API 调用

```python
from pathlib import Path
from agent.pipeline import BuildOptions, run
from agent.parsers import LLMConfig
from agent.schema import QuizMeta

options = BuildOptions.create(
    inputs=[Path("samples")],
    output=Path("output/demo_quiz.html"),
    meta=QuizMeta(
        title="毛泽东思想和中国特色社会主义理论体系概论 自测系统",
        subtitle="自测系统@千纸鹤",
        announcement=["本系统由 自测生成系统 自动生成"],
        update_url="https://pan.baidu.com/",
    ),
    llm=LLMConfig.from_env(mode="rule"),  # 仅规则模式
)

report = run(options)
print(report.summary())
```

---

## 11. 生成的刷题系统功能

生成的 HTML 完整保留参考项目的全部交互能力：

- **题目展示**：题干、当前题号 / 总题数、章节、题型标签（`[单选题]/[多选题]/[判断题]`）
- **选项选择**：单选 / 判断用 radio，多选用 checkbox，选中高亮
- **答案判断**：单选/判断即时判分；多选需点击"提交答案"
- **对错反馈**：`✓ 回答正确！` / `✗ 回答错误！正确答案是：X`
- **得分统计**：已完成题数、正确率、进度条实时更新
- **题目导航**：题号九宫格，已答对 = 绿、答错 = 红，点击可跳转
- **章节筛选**：下拉切换章节，自动定位到该章第一题
- **进度持久化**：答案与成绩写入 `localStorage`，刷新不丢失
- **重新开始**：一键清空作答与成绩
- **系统公告**：加载时弹出公告弹窗，可关闭；顶部"公告"按钮可再次打开
- **获取最新版**：按钮跳转到 `update_url`

---

## 12. 验证结果

以 `samples/` 三份演示题库（txt 10 题 + md 8 题 + csv 6 题）构建，结果为 **24 题**
（single=10 / multi=7 / judge=7）：

| 验证项 | 结果 |
| --- | --- |
| 三格式解析数量 | txt=10、md=8、csv=6 ✅ |
| 数据结构校验 | `option[0]` 与字母一致、答案在选项范围内、multi 为数组 ✅ |
| 内嵌 JS 语法 | Node `new vm.Script(...)` 通过 ✅ |
| 与参考项目差异 | 仅 6 处预期替换（标题/章节/公告/数据块注释/跳转链接），CSS/HTML/JS 逻辑逐字节一致 ✅ |
| 浏览器实测 | 单选/多选/判断判分、错误反馈、得分统计、进度条、章节筛选、导航跳转、重新开始、公告弹窗全部正常，控制台无报错 ✅ |

---

## 13. 常见问题

**Q：题目没有被解析出来？**
A：先用 `python run.py parse -i 你的文件` 查看中间结果；确认题型/答案列名或答案标记符合第 7 节的写法。

**Q：某些题目被跳过？**
A：默认跳过"缺少答案/题干为空"的题目并在结尾给出警告；加 `--strict` 可让其直接报错定位问题。

**Q：想改界面样式或交互？**
A：编辑 `agent/templates/quiz_template.html`，或用 `--template` 指定自定义模板。模板占位符：
`{{TITLE}}` `{{SUBTITLE}}` `{{CHAPTER_OPTIONS}}` `{{ANNOUNCEMENT}}` `{{UPDATE_URL}}` `{{QUESTIONS_JSON}}`。

**Q：生成的 HTML 能离线用吗？**
A：可以，直接双击打开即可，所有 CSS/JS/数据均内联在单个文件中，无需网络与服务器。

---

## 14. 图形界面（GUI）

启动方式：

```powershell
python app.py          # 无参数 -> 图形界面
```

界面分三步，全部操作均有中文提示与错误弹窗：

1. **第一步：导入题库** —— 点击「添加文件」（可多选）或「添加文件夹」（递归导入整个目录）。
   支持 JSON / CSV / TSV / Excel / Markdown / 纯文本。导入后自动解析并**逐题校验**，
   列表中显示每个文件的「校验状态」和「有效题目」数。
2. **第二步：填写信息** —— 标题、副标题、更新地址、公告内容与输出路径。
3. **第三步：一键生成 HTML** —— 点击「一键生成 HTML」，完成后可「打开文件」或「打开所在文件夹」。

其它：
- 顶部「操作指引」按钮可查看完整使用说明与常见问题。
- 「重新校验」可对当前列表重跑导入校验。
- 校验未通过的文件不会参与生成；生成时会在日志区输出题型 / 章节分布与警告明细。

### 错误提示机制

| 场景 | 提示方式 |
| --- | --- |
| 未导入题库就点生成 | 弹窗警告「请先在第一步导入至少一个题库文件」 |
| 无校验通过的文件 | 弹窗错误「当前没有校验通过的题库文件，请检查导入结果或点击「重新校验」」 |
| 输出目录不存在 | 自动创建；失败时弹出「输出路径不可用」并给出具体原因 |
| JSON 语法错误 | 日志与弹窗给出**具体行号与列号** |
| Excel 读取失败 / 文件不存在 | 日志与弹窗给出文件路径与原因 |
| 未配置 `QUIZ_LLM_API_KEY` | 自动降级为规则解析并在日志中提示 |
| 单题异常 | 跳过该题、其余题目照常生成，日志列出跳过原因 |

---

## 15. 打包为 exe（无需用户安装 Python）

打包脚本 `build_exe.py` 会调用 PyInstaller 生成**单文件、免运行时**的 `dist/test-builder.exe`：
内置 Python 解释器、全部依赖与 HTML 模板，用户拿到 exe 即可运行，无需安装 Python 或任何库。

### 打包环境准备

```powershell
pip install pyinstaller        # 仅打包者需要；使用者无需任何环境
```

> 注意：必须使用 **python.org 官方 win-amd64 解释器**。
> MSYS2 / MinGW 的 Python（`sysconfig.get_platform()` 返回 `mingw_*`）PyInstaller 不支持。

### 一键打包

```powershell
# 在项目根目录执行
D:\python3.12\python.exe build_exe.py
```

脚本会清理 `build/`、`dist/`，并以如下关键参数打包（等价于手动执行）：

```
pyinstaller app.py --name test-builder --onefile --console --clean --noconfirm
  --add-data "agent/templates;agent/templates"     # 内置 HTML 模板
  --collect-submodules agent                        # 收集全部解析子模块
  --hidden-import agent.gui --hidden-import agent.cli
```

产物：`dist/test-builder.exe`（约 10.9 MB）。运行时模板通过 `sys._MEIPASS` 定位，
已随 exe 一起打包，无需外部文件。

### exe 使用方式

exe 同时支持**图形界面**与**命令行**两种模式：

```powershell
# 图形界面：直接双击 test-builder.exe，或在命令行无参数运行
test-builder.exe

# 命令行：带参数即走 CLI（与 python run.py 完全一致）
test-builder.exe --help
test-builder.exe validate -i samples
test-builder.exe build -i samples -o out.html --title "我的刷题系统" --no-llm
test-builder.exe parse -i samples > questions.json
```

实现细节：exe 采用 `--console` 模式以便 CLI 输出可见；**无参数启动**时会通过
`GetConsoleWindow` + `GetConsoleProcessList` 判断是否为"双击启动"（独占控制台），
是则自动隐藏多余的控制台黑窗，从而在单文件 exe 中同时满足两种使用方式。

### 打包验证（实测结果）

| 验证项 | 命令 | 结果 |
| --- | --- | --- |
| CLI 导入校验 | `test-builder.exe validate -i samples` | 5 个文件全部通过，33 题有效，退出码 0 ✅ |
| CLI 生成 HTML | `test-builder.exe build -i samples -o out.html` | 生成 30 题（excel/json/table/hybrid/hybrid），退出码 0 ✅ |
| 模板内置 | 生成的 `out.html` | 39.9 KB，包含题库 JSON 与 `localStorage` 逻辑，样式结构完整 ✅ |
| GUI 启动 | 双击 `test-builder.exe` | 图形窗口正常创建并驻留 ✅ |
| 中文输出 | 重定向到文件 | CLI 输出强制 UTF-8，无乱码 ✅ |
| 免环境 | 独立 exe | 无需安装 Python / 依赖，内置解释器与模板 ✅ |
