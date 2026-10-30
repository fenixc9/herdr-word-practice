# herdr-word-practice

**在 vibe coding 的间隙背单词。**

> **English:** a [Herdr](https://herdr.dev) plugin for vocabulary drills between coding
> sessions. Press `prefix+w`, get one card, type the word, `Esc` back to work (~90 s).
> Spaced repetition (SM-2 variant), typing recall instead of multiple choice, a periodic
> fill-in-the-blank quiz, per-wordbook review pools, and 7085 bundled words
> (CET-4 4537 + CET-6 2271 + dev English 277). Pure Python 3, stdlib only, no build step.
>
> ```bash
> herdr plugin install fenixc9/herdr-word-practice --ref main
> herdr plugin action invoke herdr-word-practice.setup
> ```
>
> Docs below are in Chinese.

一个 [herdr](https://github.com/) 插件：按 `prefix+w`，在当前 tab 里 split 出一张卡片，打一个词，90 秒后按 `Esc` 回到代码。

它借鉴了 [TypeWords](https://github.com/zyronon/TypeWords) 的核心思路——**靠打字回忆，而不是翻看**——
再把「间隔重复 + 打字判分 + 音标/例句/词根」压进一个能塞进侧栏的终端界面。

```
╭ word practice | 默写 ───────────────────────────────────────────── 1/3 ╮
├────────────────────────────────────────────────────────────────────────┤
                                 _ _ _ _                                  
                             /ˈaɪdl/  adj./v.                             
                                  空闲的                                  
               Use the ______ time between tasks to drill.                
                   Idle time is when the bugs surface.                     
                           空闲时 bug 才浮现。                            
                       ╭─ 输入 ───────────────────╮                       
                       │ 开始输入...            ▏ │                       
                       ╰──────────────────────────╯                       
                       4 个字母                                           
├────────────────────────────────────────────────────────────────────────┤
│ ▱▱▱▱▱▱▱▱▱▱▱▱▱▱    0%  今日 0/20 词  累计 0 词  ✓0/✗0  00:00            │
╰─ ⏎ 提交  |  ⇥ 提示  |  ⌃k 掌握  |  ⌃b 词书  |  ? 帮助  |  esc/⌃c 退出 ─╯
```

带音标、词性、长短两条例句、中文翻译；答完给出对错判定、近义词、搭配和词源。

---

## 目录

- [特性](#特性)
- [安装](#安装)
- [使用](#使用)
- [扩展词表](#扩展词表)
- [记忆曲线怎么算的](#记忆曲线怎么算的)
- [设置与命令行](#设置与命令行)
- [数据存在哪](#数据存在哪)
- [开发](#开发)
- [常见问题](#常见问题)
- [许可与致谢](#许可与致谢)

---

## 特性

| 功能 | 说明 |
| --- | --- |
| **七种练习模式** | 跟打 / 默写 / 看中文拼写 / 自测 / 智能复习 / 小测验 / 错词本 |
| **打字判分** | 拼完自动提交，逐字母显示对错；`Tab` 给一个字母提示 |
| **间隔重复** | SM-2 变体：10 分钟 → 1 天 → 按 ease 增长，答错回到学习中 |
| **内置 7085 词** | CET-4 4537 + CET-6 2271 + 程序员英语 277，全部带音标/词性/中文 |
| **例句与搭配** | 高频词有长短两条例句 + 中文翻译、近义词、搭配（436 词）、词源（110 词） |
| **定期小测验** | 每 2 组自动插入 3 道题：一半遮字母填空，一半完全默写 |
| **随时切词书** | `Ctrl+B` 打开词书列表，选中即切，记住选择 |
| **进度可见** | 状态栏显示今日词数 / 累计词数 / 当前词书，答完立刻变 |
| **自己加词** | TSV / CSV / JSON 导入，或直接往 `data/wordbooks/` 放文件 |
| **空闲提醒** | agent 干完活变空闲时提醒一次（45 分钟节流 + 夜间静默） |
| **零依赖** | 纯 Python 3 标准库，不需要 pip install，没有构建步骤 |

---

## 安装

### 前置条件

| 依赖 | 版本 | 检查 |
| --- | --- | --- |
| herdr | `>= 0.9.1` | `herdr --version` |
| Python | `>= 3.9` | `python3 --version` |

不需要 `pip install` 任何东西——只用标准库，没有构建步骤。

### 从 GitHub 安装（推荐）

用 herdr 原生的插件安装：

```bash
herdr plugin install fenixc9/herdr-word-practice --ref main
```

然后一条命令完成剩下的接线（写入键位、把 `words` 命令挂到 PATH、重载配置）：

```bash
herdr plugin action invoke herdr-word-practice.setup
```

就这两条。按 **`prefix+w`** 开始背。

`setup` 是幂等的，**升级后再跑一次**即可：

```bash
herdr plugin update herdr-word-practice
herdr plugin action invoke herdr-word-practice.setup
```

想固定到某个 commit：

```bash
herdr plugin install fenixc9/herdr-word-practice --ref <COMMIT_SHA>
```

### 不用 keybinding 也能开

```bash
# 直接开一个训练窗格
herdr plugin pane open --plugin herdr-word-practice --entrypoint break

# 或者跑某个动作（drill / follow / dictation / spelling / selfcheck / quiz / review / stats）
herdr plugin action invoke herdr-word-practice.drill
```

### 手工写键位

`setup` 干的就是这件事；想自己控制就手动加进 `~/.config/herdr/config.toml`：

```toml
[[keys.command]]
key = "prefix+w"
type = "plugin_action"
command = "herdr-word-practice.drill"
description = "背单词"

[[keys.command]]
key = "prefix+shift+w"
type = "plugin_action"
command = "herdr-word-practice.dictation"
description = "背单词：默写"

[[keys.command]]
key = "prefix+alt+w"
type = "plugin_action"
command = "herdr-word-practice.stats"
description = "背单词：学习进度"
```

然后 `herdr server reload-config`。

### 用 `words` 命令

`setup` 会把 `words` 软链到 `~/.local/bin/words`（指向插件安装目录里的 `scripts/words`）。
如果那个目录不在 PATH 里，加一行就好：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

不想用命令行入口也行，所有功能都能通过上面的 herdr 动作到达；`words` 只是让
`books` / `stats` / `settings` / `import` 这些一次性操作更顺手。

### 不用 herdr 也能用

界面是纯 ANSI 的，任何终端都行——适合先看看长什么样：

```bash
git clone https://github.com/fenixc9/herdr-word-practice.git
cd herdr-word-practice
python3 main.py drill
```

### 开发模式（改代码立刻看效果）

想让 herdr 直接跑你本地的 checkout，用 `link` 而不是 GitHub 安装：

```bash
git clone https://github.com/fenixc9/herdr-word-practice.git
cd herdr-word-practice
./scripts/install.sh            # = herdr plugin link . + words setup
./scripts/install.sh --dry-run  # 先看会改什么
```

两者不要同时用：同一 id 只能有一个来源，切换前先
`herdr plugin unlink herdr-word-practice` 或 `herdr plugin uninstall herdr-word-practice`。

### 卸载

```bash
herdr plugin uninstall herdr-word-practice     # GitHub 安装的版本
rm -f ~/.local/bin/words
rm -rf ~/.local/state/herdr/plugins/herdr-word-practice    # 进度也会删掉
# 键位留在 config.toml 里，不需要就删掉那三块 [[keys.command]]
```

### 更新

```bash
herdr plugin update herdr-word-practice
herdr plugin action invoke herdr-word-practice.setup   # 有新键位时才需要
```

进度存在 state 目录里，更新不会丢。

## 使用

### 七种模式

```bash
words drill                        # 智能复习（默认）
words drill -m follow              # 跟打：看着单词打一遍
words drill -m dictation           # 默写：只看中文和挖空例句
words drill -m spelling            # 看中文拼写
words drill -m selfcheck           # 自测：认识/模糊/不认识，不动手
words drill -m quiz                # 小测验：只考学过的词
words drill -m review              # 错词本
words drill -m free                # 自由练：不管记忆曲线
words drill -b cet6 -n 5           # 换词书、每组 5 个
```

在 herdr 里也有对应动作（`herdr plugin action list --plugin herdr-word-practice`）：
`drill` / `follow` / `dictation` / `spelling` / `selfcheck` / `quiz` / `review` / `stats` / `nudge-now`。

### 键位

| 键 | 作用 |
| --- | --- |
| 字母 | 输入；**拼完自动提交**，不用按回车 |
| `Enter` | 提交 / 下一张 / 完成页再来一组 |
| `Tab` | 提示**下一个**字母——从你已经打对的位置往后给，不是从头重来；输入框下显示「已提示 N」= 你按了几次（用过提示仍算对，但只给「认识」档） |
| `Backspace` | 删一个字母 |
| `Ctrl+K` | 标记为已掌握（不再出现在智能复习里） |
| `Ctrl+B` | 切换词书（数字或 ↑↓+⏎ 选，立即切过去） |
| `Ctrl+Q` | 现在来一次小测验 |
| `1`–`4` | 自测模式：不认识 / 模糊 / 认识 / 太简单 |
| `?` | 帮助 |
| `Esc` | 退出（自动保存） |
| `Ctrl+C` | 退出（同样保存）——比 Esc 快，见[常见问题](#按-esc-关窗有点慢) |

> `Esc` 在 herdr 里要等一次超时才被转发（客户端为区分 `Alt+` 组合键），按 `Ctrl+C` 立刻生效。

### 状态栏

```
│ ▰▰▱▱▱▱▱▱▱▱  10%  今日 65/20 词  累计 65 词  程序员英语  ✓1/✗0  00:42 │
```

- **今日 65/20 词**：今天练过的**不同单词数** / 每日目标
- **累计 65 词**：建立进度以来练过的不同单词数
- **程序员英语**：当前词书（标题栏里也有）
- 窗口窄时从右往左整段丢弃，`今日` / `累计` 永远保留

### 定期小测验

每完成 2 组（`quiz_every_sessions`），下一组「智能复习」以 3 道**小测验**开场：

```
╭ word practice | CET-4 核心  | 小测验 ──────────────── 1/8 ╮
                   i _ _ l _ _ e _ _                        ← 填空
                          /ˈɪmplɪment/  v.
                                实现
```

- 第 1、3、5… 题是**填空**：保留首字母和每三个字母中的一个（`cache` → `c _ _ h _`）
- 第 2、4、6… 题是**完全默写**：只给音标、释义、例句
- 只从**学过**的词里出题（`reps > 0`），错得多的优先
- 想立刻测一次：`Ctrl+Q`，或 `words drill -m quiz`

调频率：

```bash
words settings quiz_every_sessions=1   # 每组都测
words settings quiz_every_sessions=0   # 关掉定时测验
words settings quiz_size=5             # 每次 5 题
```

### 内置词书

**每本词书有独立的复习池。** 进度按 `词书:单词` 记，切词书不会带走、也不会污染另一本：

- 到期队列、错词本、已掌握标记、每日新词额度（`daily_new_limit`）都按词书各算各的
- 状态栏的「今日 / 累计」跟着当前词书走
- 「连续天数」是全局的——它是习惯指标，不是某一本书的指标

```bash
words books                     # 每本书各自的新/学习中/复习/已掌握
words stats                     # 待复习 = 当前词书
```

| id | 名称 | 词数 | 内容 |
| --- | --- | --- | --- |
| `cet4` | CET-4 核心 | 4537 | 四级大纲全词表 |
| `cet6` | CET-6 进阶 | 2271 | 六级大纲全词表 |
| `coding` | 程序员英语 | 277 | 日志、commit、文档里天天见的词 |

```bash
words books                     # 列表 + 每本的学习状态
words books --words coding      # 打印整本词书
words settings book=cet6        # 改成默认词书
```

训练中直接按 `Ctrl+B` 切词书，选择会被记住。

---

## 扩展词表

三条路，按介入深度从浅到深。

### 一、导入自己的词表（最快）

支持 TSV / CSV / JSON，导入后存进 `<state>/books/`，可以 `--use` 直接切过去：

```bash
# 两列 CSV：单词,释义
words import ~/my-words.csv --id mine --name 我的词 --use

# TSV，带完整字段（推荐）
words import ~/my-words.tsv --id mine --name 我的词
```

最小能用的 CSV / TSV 只需要两列：

```csv
word,meaning
cache,缓存
rollback,回滚
```

JSON 的键可以写短名（`w`/`cn`/`en`）也可以写长名（`word`/`meaning`/`example`），
手写时怎么顺手怎么来。

导入后立刻可用：`words drill -b mine`。

### 二、直接放一个词书文件

把文件丢进 `data/wordbooks/`，重启即出现在列表里——**最省事，且能进 git**。

完整 9 列 TSV 格式（`docs/wordbook-format.md` 有逐列说明）：

| # | 列 | 必填 | 说明 |
| --- | --- | --- | --- |
| 1 | `word` | ✅ | 单词 |
| 2 | `ipa` | | 音标，不带斜杠，如 `ˈkæʃ` |
| 3 | `pos` | | 词性，如 `n./v.` |
| 4 | `cn` | ✅ | 中文释义 |
| 5 | `en` | | 英文例句 |
| 6 | `zh` | | 例句中文翻译 |
| 7 | `syn` | | 近义词，逗号分隔 |
| 8 | `root` | | 词源拆解 |
| 9 | `phr` | | 常见搭配，逗号分隔 |

```tsv
cache	ˈkæʃ	n./v.	缓存	The cache is warm.	缓存是热的。	buffer,store	buffer,invalidat
rollback	ˈroʊlbæk	n./v.	回滚	Keep a rollback ready.	准备好回滚方案。	revert	rollback plan
```

只有第 1、4 列是必需的，其余留空即可。

### 三、给已有词补多条例句

例句可以放进**同名 sidecar 文件**，和词表并列：`data/wordbooks/<book>.examples.tsv`。

```tsv
# 第 1 列单词，第 2 列英文例句，第 3 列中文翻译
cache	The cache is warm, so the query returns in a millisecond.	缓存是热的，所以查询一毫秒就返回。
cache	A stale cache is worse than no cache.	过期的缓存比没有缓存更糟。
```

- 同一个词写多行 = 多个例句；短句在前长句在后，界面上最多显示两条
- 只有第 1、2 列必需
- 以主例句开头重复句会被自动去重

现在的例句覆盖：cet4 531 词、cet6 236 词、coding 277 词（每词 2–3 条）。

### 四、重新生成四六级大纲词表

CET-4 / CET-6 数据来自 [mahavivo/english-wordlists](https://github.com/mahavivo/english-wordlists)（MIT），
用脚本重新拉取：

```bash
python3 scripts/fetch-wordlists.py            # 下载 + 解析 + 合并
python3 scripts/fetch-wordlists.py --check    # 只看会改什么
```

脚本会：

1. 下载 CET4 / CET6 大纲词表，解析 `word [ipa] pos.释义`
2. 合并 `data/wordbooks/curated/*.tsv` —— **手写内容永远不会被覆盖**
3. 写出 `data/wordbooks/cet4.tsv` / `cet6.tsv`

所以想给大纲词补音标、例句、词根，改 `curated/` 下的文件再跑脚本即可。

### 加词之后要做什么？

不用做什么。词书按需加载，`words books` 立刻能看到；进度按 `词书:单词` 记，
换了词书或删了词都不会串味（`words reset --yes` 可清空）。

---

## 记忆曲线怎么算的

简化版 SM-2，按「一组 10 个词」的粒度调过：

- 第一次答对 → 10 分钟后
- 第二次答对 → 1 天后
- 之后间隔 × ease（2.5 起，答对约 +0.1，答错 −0.2，夹在 1.3–2.8）
- 答错 → 回到「学习中」，10 分钟后再来，ease 下降
- 间隔 ≥ 21 天且复习 ≥ 4 次 → 已掌握，不再进智能复习
- 用了 `Tab` 提示 → quality 封顶 3，ease 涨得少

所以一天里可以练很多组：新词 10 分钟后回来，正好是「vibe coding 的间隙」这个节奏。

组题顺序：本轮到期的 → 新词（受 `daily_new_limit` 限制）→ 弱项 → 剩下的。
同一组内不重复，刚答过的词不会立刻又出现在下一组。

---

## 设置与命令行

### 设置

```bash
words settings                        # 看当前设置
words settings session_size=8         # 每组 8 个词
words settings daily_goal=30          # 每日目标 30 个
words settings book=coding            # 默认词书
words settings theme=light            # 深色背景请用 dark
words settings nudge.quiet_hours=[23,8]   # JSON 值也行
words settings nudge.enabled=false    # 关掉空闲提醒
```

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `book` | `cet4` | 默认词书 |
| `mode` | `smart` | 默认模式 |
| `session_size` | `10` | 一组多少个词 |
| `daily_new_limit` | `8` | 每天最多引入多少新词 |
| `daily_goal` | `20` | 状态栏「今日 x/20 词」的目标值 |
| `quiz_every_sessions` | `2` | 每 N 组插入一次小测验；`0` 关闭 |
| `quiz_size` | `3` | 定时插入的测验题数 |
| `theme` | `auto` | 配色：`auto` / `dark` / `light` |
| `notify_on_finish` | `true` | 练完弹一条通知 |
| `nudge.enabled` | `true` | agent 空闲时是否提醒 |
| `nudge.min_gap_minutes` | `45` | 两次提醒的最小间隔 |
| `nudge.quiet_hours` | `[23, 8]` | 静默时段（跨午夜），用机器本地时间 |
| `nudge.auto_open` | `false` | 提醒时直接开窗格 |

### 命令行

```
words drill [-m MODE] [-b BOOK] [-n SIZE] [--plan] [--once] [--theme T]
words stats [--json] [--wait]
words books [--json] [--words BOOK]
words import PATH [--id ID] [--name NAME] [--use]
words settings [key=value ...] [--json]
words setup [--dry-run] [--json]     # 写键位 + 链接 words + 重载（setup action 调的就是它）
words reset [--yes]
words doctor [--json]
```

- `drill --plan` 只列出这一轮会练哪些词，不进界面
- `drill --once` 渲染一帧就退出（无 tty 时预览布局）
- `stats --wait` 打印后等回车，给 herdr 的进度窗格用
- `doctor` 检查 python、目录、herdr CLI、词书是否就绪

---

## 数据存在哪

```
~/.local/state/herdr/plugins/herdr-word-practice/
├── progress.json        # 每个词的状态 + 每日统计（原子写 + flock）
├── nudge.json           # 上次提醒时间
└── books/*.json         # 导入的自定义词书
~/.config/herdr/plugins/config/herdr-word-practice/settings.json
```

在 herdr 外面用 `words …` 时也会沿用同一个目录（存在的话），所以终端里练的和窗格里练的是同一份进度。

`progress.json` 是人类可读的 JSON；坏了会自动备份成 `progress.corrupt-<ts>.json` 并重新开始，
不会让插件起不来。`words reset --yes` 清空进度。

---

## 开发

```bash
python3 -m pytest tests/ -q                                        # 148 个测试（含真实 pty 端到端）
python3 -m flake8 --max-line-length=100 worddrill/ main.py tests/  # 风格检查
python3 main.py drill --once --width 76 --height 20 -b coding      # 看渲染
```

| 文件 | 职责 |
| --- | --- |
| `worddrill/data.py` | 词书解析（TSV/CSV/JSON）、例句 sidecar、遮字填空 |
| `worddrill/srs.py` | SM-2 变体、组题策略、模式表 |
| `worddrill/session.py` | 打字 / 提示 / 判分状态机 |
| `worddrill/ui.py` | 终端渲染与按键解码（无第三方依赖） |
| `worddrill/term.py` | 显示宽度、CJK 对齐、配色 |
| `worddrill/store.py` | 进度与设置持久化 |
| `worddrill/herdr.py` | 对 herdr CLI 的薄封装 |
| `worddrill/cli.py` | 子命令 |

设计取舍见 [docs/design.md](docs/design.md)，词书格式见 [docs/wordbook-format.md](docs/wordbook-format.md)。

---

## 常见问题

### 打开后一片空白？

1. 先固定配色：`words settings theme=light`（或 `dark`）再看一次。
   默认 `auto` 用终端默认前景色画正文、用深浅背景都能读的中间调画强调色，通常不用改。
2. 确认进程起了：`pgrep -f "main.py drill"`。
3. 看 herdr 侧日志：`herdr plugin log list`，失败调用会带 stderr。
4. `words doctor` 会打印 python、目录、herdr CLI、词书的状态。

### 中文 / 边框错位？

宽度按显示列算（CJK = 2 列），并且刻意不用"宽度取决于字体"的字符做布局：

- 分隔符是 ASCII `|`，不是 `·`（`·` 常被渲染成 2 列，会把底栏撑歪）
- `…`、`—`、`→` 也都换成了 ASCII
- 边框用制表符 `─│╭╮╰╯`，等宽字体里恒为 1 列
- 窄窗口下按键提示整条丢弃（`esc 退出` 永远保留），不会把汉字劈成两半

回归测试守着：顶栏底栏收口到同一列、输入框三条边等宽、状态栏不得出现宽度不确定字形。

### 输入没反应？

界面在"终端尺寸没变"时曾跳过重绘；已修复为每次按键都强制重绘。
若仍遇到，先确认窗格聚焦（`herdr pane current`），再在普通 shell 里跑 `words drill` 对比。

### 按 Esc 关窗有点慢？

这是 herdr 客户端的行为，不是插件：收到单独 `Esc` 后它要等一次 input timeout，
才能判断是"纯 Esc"还是 `Alt+` 组合键的开头。client 日志里能看到：

```
WARN herdr::raw_input: flushing lone escape after input timeout;
     if this follows an alt chord or focus switch it may reach the pane as plain esc
```

绕过办法：按 **`Ctrl+C`** 退出（控制字符不参与 Esc 消歧，立刻转发）。底栏也写成 `esc/⌃c 退出`。

插件本身退出很快：按 Esc/Ctrl+C 到窗格消失实测 **40ms**（含落盘）。

### `herdr plugin install` 失败？

```bash
herdr plugin install fenixc9/herdr-word-practice --ref main -y   # -y 用于非交互
herdr plugin log list --plugin herdr-word-practice              # 看 install/setup 的输出
```

要求 herdr `>= 0.9.1`。如果你之前用 `link` 装过同一个 id，先
`herdr plugin unlink herdr-word-practice`，两者不能同时存在。

### 键位不生效？

```bash
herdr config check
herdr server reload-config
```

### 为什么用 split 而不是 popup？

popup 关闭时屏幕要挂 1 秒多才收掉，split 只要 40ms——对「90 秒一组」来说太不值。
想换回来可以改 manifest 里 `break` 的 placement（需要同时补 `width` / `height`）。

---

## 许可与致谢

- 本项目代码：[MIT](LICENSE)
- CET-4 / CET-6 词表数据：[mahavivo/english-wordlists](https://github.com/mahavivo/english-wordlists)（MIT）
- 交互思路参考：[TypeWords](https://github.com/zyronon/TypeWords)

真实语料（例句、搭配、词源）为本项目手写。