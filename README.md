# Codex Usage Receipt

把本机 Codex 的原始 JSONL 会话日志整理成一份可审计、可打印、按模型拆分的 token 消费收据。

这个项目最适合这些场景：

- 你想知道某个时间段内 Codex 到底消耗了多少 token。
- 你需要把 Windows 和 WSL 里的 Codex 使用量一起统计。
- 你想按模型列出输入、缓存命中、输出 token 和估算成本。
- 你要生成一份面向人看的收据、费用报告、PDF 或黑白打印件。
- 你希望模型在统计前先确认时间段，避免把“最近”“这个月”这类口径算错。

> 说明：这是本地估算收据，不是 OpenAI 官方税务发票。项目默认只读取本机日志，不会上传你的日志内容。

## 功能概览

- 从原始 Codex JSONL 日志统计 `token_count` 事件。
- 默认扫描 Windows 用户目录和 WSL Ubuntu root 目录。
- 按模型汇总：
  - fresh input tokens
  - cache-hit input tokens
  - output tokens
  - reasoning output tokens
  - usage event count
  - model-specific estimated USD cost
- 支持当前 Codex rate limit 快照：
  - primary window used / remaining
  - secondary window used / remaining
  - reset time
- 内置价格表，也支持命令行覆盖价格。
- 优先使用 LaTeX 生成漂亮的 PDF；如果没有 LaTeX，可以降级为 Python 纯文本收据。
- 可以作为 Codex skill 使用，也可以直接运行脚本。

## 项目结构

```text
codex-usage-receipt/
├── SKILL.md
├── README.md
├── scripts/
│   ├── codex_usage_summary.py
│   └── render_text_receipt.py
└── evals/
    └── evals.json
```

`SKILL.md` 是给 Codex/Claude 使用的工作流说明。  
`codex_usage_summary.py` 负责读取 JSONL 日志并输出结构化统计 JSON。  
`render_text_receipt.py` 负责把统计 JSON 渲染为纯文本收据，作为没有 LaTeX 时的可靠 fallback。

## 安装为 Codex Skill

把本仓库放到你的 Codex skills 目录下：

```powershell
cd $env:USERPROFILE\.codex\skills
git clone https://github.com/<owner>/codex-usage-receipt.git
```

目录名应保持为：

```text
codex-usage-receipt
```

安装后，可以在 Codex 里自然地说：

```text
打印 2026-05-23 以来的 Codex token 消费收据，Windows 和 WSL 都要算上，黑白打印。
```

或者：

```text
帮我统计 Codex token 消耗，做成收据。
```

如果你没有给出明确时间段，skill 会先问你要统计哪段时间。

## 直接命令行使用

先生成统计 JSON：

```powershell
python scripts\codex_usage_summary.py `
  --since 2026-05-23 `
  --until 2026-07-05 `
  --timezone +08:00 `
  --output work\codex-usage-summary.json
```

再生成纯文本收据：

```powershell
python scripts\render_text_receipt.py `
  work\codex-usage-summary.json `
  --output outputs\codex-usage-receipt.txt
```

如果只想看 JSON，可以省略 `--output`：

```powershell
python scripts\codex_usage_summary.py --since 2026-05-23 --until 2026-07-05
```

## 时间段规则

`--since` 是必填项。  
`--until` 是可选项，省略时表示统计到当前时间。

日期可以写成：

```text
2026-05-23
```

也可以写成带时间的形式：

```text
2026-05-23T00:00:00
```

如果 `--until` 只给日期，例如 `2026-07-05`，脚本会把它当作当天 `23:59:59`。

默认时区是 `+08:00`，可以通过 `--timezone` 覆盖。

## 默认日志位置

脚本默认扫描这些位置：

```text
%USERPROFILE%\.codex\sessions
%USERPROFILE%\.codex\archived_sessions
\\wsl.localhost\Ubuntu\root\.codex\sessions
\\wsl.localhost\Ubuntu\root\.codex\archived_sessions
```

如果你的 WSL 用户不是 root，或者发行版不叫 Ubuntu，可以用 `--root` 加额外路径：

```powershell
python scripts\codex_usage_summary.py `
  --since 2026-05-23 `
  --until 2026-07-05 `
  --root "WSL home=\\wsl.localhost\Ubuntu\home\<linux-user>\.codex\sessions" `
  --output work\codex-usage-summary.json
```

`--root` 支持两种写法：

```text
label=path
path
```

带 label 时，输出里的 `by_source` 会使用这个名称。

## 计费口径

脚本默认使用 `event_msg` 中的 `payload.type == "token_count"` 事件，并读取 `info.last_token_usage`。

这样做是因为 `total_token_usage` 是累计值，在会话压缩、续写或恢复时可能重置或重复。如果直接把累计值相加，容易把 token 数放大。

核心计算公式：

```text
fresh_input_tokens = input_tokens - cached_input_tokens

cost =
  fresh_input_tokens / 1_000_000 * input_rate
+ cached_input_tokens / 1_000_000 * cache_hit_rate
+ output_tokens / 1_000_000 * output_rate
+ cache_creation_tokens / 1_000_000 * cache_creation_rate
```

默认认为 cache creation 单价为 `$0.00/M`。

## 默认价格表

单位：USD / 1M tokens。

| Model | Input | Cache hit | Output | Cache creation |
|---|---:|---:|---:|---:|
| `gpt-5.5` | `$5.00` | `$0.50` | `$30.00` | `$0.00` |
| `gpt-5.4` | `$2.50` | `$0.25` | `$15.00` | `$0.00` |
| `gpt-5.4-mini` | `$0.75` | `$0.075` | `$4.50` | `$0.00` |
| `gpt-5.3-codex` | `$1.75` | `$0.175` | `$14.00` | `$0.00` |
| `gpt-5.3-codex-spark` | `$1.75` | `$0.175` | `$14.00` | `$0.00` |

如果价格发生变化，可以用 `--price` 覆盖：

```powershell
python scripts\codex_usage_summary.py `
  --since 2026-05-23 `
  --until 2026-07-05 `
  --price gpt-5.3-codex-spark=1.75,0.175,14,0 `
  --output work\codex-usage-summary.json
```

格式为：

```text
model=input,cache_hit,output,cache_creation
```

如果省略第四项，cache creation 默认是 `0`。

## 输出 JSON 字段

`codex_usage_summary.py` 输出的 JSON 主要包含：

- `generated_at`：生成时间。
- `since` / `through`：统计时间段。
- `first_event` / `last_event`：实际命中的第一条和最后一条使用事件。
- `files_found`：扫描到的 JSONL 文件数量。
- `included_sessions`：实际包含使用量的 session 数量。
- `models`：按模型拆分的 token 和成本。
- `total`：总 token、总成本、缓存命中率和成本组件。
- `by_source`：按日志来源拆分，例如 Windows 和 WSL。
- `rate_limits`：从日志里读到的最新 Codex 限额快照。
- `pricing`：本次计算使用的价格表。
- `notes`：方法说明和注意事项。

## 没有 LaTeX 时怎么办

LaTeX 只是生成漂亮 PDF 的首选，不是硬依赖。

如果没有安装 TeX Live、Tectonic 或其它 LaTeX 工具，直接用纯文本 fallback：

```powershell
python scripts\render_text_receipt.py `
  work\codex-usage-summary.json `
  --output outputs\codex-usage-receipt.txt
```

在 Windows 上可以直接打印文本：

```powershell
Get-Content outputs\codex-usage-receipt.txt | Out-Printer -Name "<Printer Name>"
```

如果需要 PDF，但没有 LaTeX，可以让 Codex 使用 Python、浏览器打印、ReportLab、Pillow 或系统已有工具生成替代版。不要为了生成 PDF 自动安装大型依赖，除非用户明确同意。

## 打印建议

生成 PDF 或 PNG 后，建议转成灰度再打印。

如果系统有 `pdftoppm`：

```powershell
pdftoppm -singlefile -png -gray -r 300 receipt.pdf receipt-print
```

打印后检查队列：

```powershell
Get-PrintJob -PrinterName "<Printer Name>" -ErrorAction SilentlyContinue
Get-Printer -Name "<Printer Name>" | Select Name,PrinterStatus,JobCount,WorkOffline
```

如果队列未清空或打印机离线，应明确告知用户，不要假装已经打印成功。

## 隐私与安全

- 脚本只读取本机 JSONL 日志。
- 默认不会上传日志、token 明细或生成的报告。
- 如果你把生成的报告提交到 GitHub，请先确认其中没有私人路径、账户信息、用量细节或其它敏感内容。
- 本仓库只应提交工具代码、skill 文档和示例，不应提交真实收据、真实日志或 `outputs/` 目录。

## 常见问题

### 为什么不用 CC Switch 或截图里的数据？

这个项目的目标是从原始 Codex JSONL 日志重建账单口径。CC Switch、截图或其它工具可以用来交叉验证，但不应作为默认来源。

### 为什么 Windows 和 WSL 分开算？

Codex 可能在 Windows 和 WSL 中各自产生日志。只看 `%USERPROFILE%\.codex\sessions` 可能漏掉 WSL 中的大量使用量。

### 为什么 `total_token_usage` 不直接相加？

因为它是会话累计值。会话压缩、恢复、重试或上下文切换时，累计值可能重置或重复。默认使用 `last_token_usage` 逐事件累加更稳定。

### 如果某个模型没有价格怎么办？

不要静默套用别的模型价格。应该：

1. 在报告里标记为 unpriced；或
2. 询问用户价格；或
3. 在确认官方/本地价格后用 `--price` 覆盖。

## 开发与校验

语法检查：

```powershell
python -m py_compile scripts\codex_usage_summary.py scripts\render_text_receipt.py
```

查看命令帮助：

```powershell
python scripts\codex_usage_summary.py --help
python scripts\render_text_receipt.py --help
```

测试用例在：

```text
evals/evals.json
```

它覆盖三类关键行为：

- 用户已给明确时间段时直接执行。
- 用户未给时间段时先询问。
- 没有 LaTeX 时 fallback 到纯文本。

