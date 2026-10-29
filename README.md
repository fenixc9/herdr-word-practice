# herdr words

在 vibe coding 的间隙背单词。

一个 herdr 插件：按 `prefix+w`，弹出一张卡片，打一个词，90 秒后回到代码。
它借鉴了 [TypeWords](https://github.com/zyronon/TypeWords) 的思路——**靠打字回忆，而不是翻看**——
再把「间隔重复 + 打字判分 + 音标/例句/词根」压进一个能塞进侧栏的终端界面。

```
╭ words · 默写 ─────────────────────────────────────────── 3/10  🔥5 ╮
├──────────────────────────────────────────────────────────────────────────┤
                                                                            
                              _ _ _ _ _ _ _ _                               
                             /ˈroʊlbæk/  n./v.                              
                                    回滚                                    
                                                                            
                   Keep a ______ ready before you deploy.                   
                                                                            
                        ╭─ 输入 ────────────────────╮                       
                        │ rollb                    │                       
                        ╰──────────────────────────╯                       
                        8 个字母                                            
                                                                            
                                                                            
                                                                            
├──────────────────────────────────────────────────────────────────────────┤
 ▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱▱▱    20%   ✓2/✗0   100%   今日 12/20   01:14   🔊          
 ⏎ 提交 · ⇥ 提示 · ⌃r 发音 · ⌃f 收藏 · ⌃m 掌握 · ? 帮助 · esc 退出          
```

## 为什么是这个形态

- **打字，不是选择。** 选择题会让你认词，打字才逼你拼出来。拼错就是没记住，这个信号比「我感觉我会」可靠得多。
- **一张卡片。** 没有列表、没有菜单、没有进度页要先翻。打开就想打，打完就能走。
- **可以随时中断。** Esc 立刻退出并保存；没打完的那组下次接着来，不会清零。
- **只占用眼前这一小块。** 在当前 tab 里 split 出一块，Esc 一按就收回去（实测 40ms），
  不用切 tab、也不会把布局搞乱。
- **主动提醒但不烦人。** agent 干完活变空闲时才提醒，45 分钟内只提醒一次，23:00–08:00 静默。

## 安装

一条命令：

```bash
cd ~/project/herdr-english-learn
./scripts/install.sh
```

它做四件事（幂等，可以反复跑）：

1. `herdr plugin link` 把插件注册到 herdr
2. 把 `words` 软链到 `~/.local/bin`（命令行入口）
3. 往 `~/.config/herdr/config.toml` 追加 `prefix+w` / `prefix+shift+w` / `prefix+alt+w`
4. `herdr server reload-config` + 自检

先看看会改什么：`./scripts/install.sh --dry-run`。

装完按 **`prefix+w`** 就能开始。卸载：

```bash
herdr plugin unlink herdr.words
rm -f ~/.local/bin/words
# 键位留在 config.toml 里，不需要就删掉那三块 [[keys.command]]
```

### 前置条件

- `herdr >= 0.9.0`（`herdr --version`）
- `python3 >= 3.9`，只用标准库，无需 pip 安装任何东西
- 发音可选：按 `espeak-ng` → `espeak` → `say` → `spd-say` 的顺序取第一个可用的；
  一个都没有也能用，只是没声音（`words doctor` 会标出来）

### 手工安装（等价）

```bash
herdr plugin link ~/project/herdr-english-learn
ln -s ~/project/herdr-english-learn/scripts/words ~/.local/bin/words
herdr server reload-config
```

键位写进 `~/.config/herdr/config.toml`：

```toml
[[keys.command]]
key = "prefix+w"
type = "plugin_action"
command = "herdr.words.drill"
description = "背单词"

[[keys.command]]
key = "prefix+shift+w"
type = "plugin_action"
command = "herdr.words.dictation"
description = "背单词：默写"

[[keys.command]]
key = "prefix+alt+w"
type = "plugin_action"
command = "herdr.words.stats"
description = "背单词：学习进度"
```

## 和 TypeWords 的对应关系

功能对齐（TypeWords → 这里）：

| TypeWords | words |
| --- | --- |
| 跟打 / 默写 / 自测 / 看中文拼写 | 同名三种打字模式 + 自测（`-m follow/dictation/spelling/selfcheck`） |
| 智能模式（记忆曲线） | `-m smart`，SM-2 变体，到期优先 |
| 自由模式 | `-m free`，不管曲线，随便练 |
| 音标 + 美/英发音 | 音标展示；`accent=us/uk` 切换 TTS 口音 |
| 例句 | 每个词一句技术/日常语境例句 + 中文翻译，默写时挖空 |
| 短语搭配 | 436 个词带常见搭配，答完显示 |
| 近义词 / 词根词源 | 全部词有近义词；110 个词有词源拆解 |
| 错误统计 | `words stats`：正确率、每日柱状、每词对错次数 |
| 收藏 / 错词本 / 已掌握 | `favorites` / `review` 模式 + `Ctrl+M` 标记掌握 |
| 多词书 | 三本内置 + 自定义导入 |
| 键盘音效 | 只有发音，没有按键音效（便携性优先，见下） |
| 文章背单词 | 未实现——这里的场景是「90 秒一组」，文章属于坐着学而不是间隙学 |

刻意不一样的地方：

- **终端而不是网页。** 这个工具的入口是「我在 herdr 里，写代码的间隙」；
  打开浏览器标签页这件事本身就足以让人放弃。
- **没有连续打卡压力。** 有 streak 显示，但没有惩罚、没有推送轰炸：
  提醒 45 分钟最多一次，夜里静默。
- **一次一组，而不是一整个学习计划。** 没有「今日必须完成 200 词」这种设计，
  因为间隙的长度不由你决定。

## 键盘

| 键 | 作用 |
| --- | --- |
| 字母 | 输入；**拼完自动提交**，不用按回车 |
| `Enter` | 提交 / 下一张 / 完成页再来一组 |
| `Tab` | 提示下一个字母（用过提示仍算对，但只给「认识」档） |
| `Backspace` | 删一个字母 |
| `Ctrl+R` | 重播发音（口音由 `accent` 设置决定） |
| `Ctrl+F` | 收藏 / 取消收藏 |
| `Ctrl+M` | 标记为已掌握（不再出现在智能复习里） |
| `Ctrl+S` | 静音开关（会写进设置） |
| `Ctrl+B` | 切换词书（列表里按数字或 ↑↓+⏎ 选，立即切过去） |
| `1`–`4` | 自测模式：不认识 / 模糊 / 认识 / 太简单 |
| `?` | 帮助 |
| `Esc` | 退出（自动保存）。herdr 客户端会为单独 Esc 等一次超时才转发，觉得慢就按 `Ctrl+C` |
| `Ctrl+C` | 退出（同样保存）——不经过 Esc 消歧，立刻生效 |

## 记忆曲线

简化版 SM-2，按「一次训练 10 个词」的粒度调过：

- 第一次答对 → 10 分钟后
- 第二次答对 → 1 天后
- 之后间隔乘以 ease（2.5 起，答对 +0.1 左右，答错 −0.2，夹在 1.3–2.8）
- 答错 → 回到「学习中」，10 分钟后再来，ease 下降
- 间隔 ≥ 21 天且复习 ≥ 4 次 → 已掌握，不再进智能复习
- 用了提示 → quality 封顶 3，ease 涨得少

所以一天里可以练很多组：新词 10 分钟后回来，正是「vibe coding 的间隙」这个节奏。

## 词书

内置三本，共 7085 个词：

| id | 名称 | 词数 | 内容 |
| --- | --- | --- | --- |
| `cet4` | CET-4 核心 | 4537 | 四级大纲全词表（含音标、词性、中文释义） |
| `cet6` | CET-6 进阶 | 2271 | 六级大纲全词表 |
| `coding` | 程序员英语 | 277 | 日志、commit、文档里天天见的词（每词 2–3 条例句） |

**CET-4 / CET-6 是完整大纲词表**：每个词都有音标、词性、中文释义，数据来自
[mahavivo/english-wordlists](https://github.com/mahavivo/english-wordlists)（MIT），
用 `scripts/fetch-wordlists.py` 重新生成即可。

**例句、近义词、搭配是手写的**，覆盖其中 1000 多个高频词（含全部 277 个程序员词）：
答完题会给出长短两条例句、近义词、常见搭配（436 词）和词源拆解（110 词），
比如 `deploy` → `deploy to production`、`de-（去掉）+ ploy（折叠）→ 展开`。

手写内容存放在 `data/wordbooks/curated/`，重跑脚本时会自动合并，不会被覆盖。

```bash
# 训练中直接按 Ctrl+B 切词书（会记住选择）
words books                     # 词书列表 + 每本的学习状态
words books --words coding      # 打印整本词书的单词
words drill -b coding -m dictation
words settings accent=uk         # 换英音
words settings book=coding      # 改成默认词书
```

### 导入自己的词表

支持 TSV / CSV / JSON，导入后存到 `<state>/books/`，可以 `--use` 直接切过去：

```bash
# 两列 CSV：单词,释义
words import ~/words.csv --id mine --name 我的词 --use

# TSV 带完整字段（推荐，见 docs/wordbook-format.md）
words import ~/words.tsv
```

JSON 里的键可以写短名（`w`/`cn`/`en`）也可以写长名（`word`/`meaning`/`example`），
手写词表时怎么顺手怎么来。

## 命令行

```
words drill [-m MODE] [-b BOOK] [-n SIZE] [--no-sound] [--plan] [--once]
words stats [--json] [--wait]
words books [--json] [--words BOOK]
words import PATH [--id ID] [--name NAME] [--use]
words settings [key=value ...] [--json]
words reset [--yes]
words doctor [--json]
```

- `drill --plan` 只列出这一轮会练哪些词，不进界面（适合先看看今天的安排）。
- `drill --once` 渲染一帧就退出，方便在没有 tty 的地方预览。
- `stats --wait` 打印后等回车，用于 herdr 里的进度窗格。
- `doctor` 检查 python、目录、发音引擎、herdr CLI、词书是否就绪。

在 herdr 外面直接 `python3 main.py drill` 也能用，状态保存在
`~/.local/state/herdr/plugins/herdr.words/`。

## 设置

```bash
words settings                       # 看当前设置
words settings session_size=8        # 每组 8 个词
words settings daily_goal=30         # 每日目标 30 个
words settings book=coding           # 默认词书
words settings nudge.min_gap_minutes=30
words settings nudge.quiet_hours=[23,8]   # JSON 值也行
words settings nudge.enabled=false   # 关掉空闲提醒
```

默认值：

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `book` | `cet4` | 默认词书 |
| `mode` | `smart` | 默认模式 |
| `session_size` | `10` | 一组多少个词 |
| `daily_new_limit` | `8` | 每天最多引入多少新词 |
| `daily_goal` | `20` | 状态栏里的每日目标 |
| `sound` | `true` | 答对时是否发音 |
| `accent` | `us` | 发音口音：`us` / `uk` |
| `theme` | `auto` | 配色：`auto`（深浅背景都能看）/ `dark` / `light` |
| `auto_pronounce` | `true` | 答对后自动读一遍 |
| `notify_on_finish` | `true` | 练完弹一条通知 |
| `nudge.enabled` | `true` | agent 空闲时是否提醒 |
| `nudge.min_gap_minutes` | `45` | 两次提醒的最小间隔 |
| `nudge.quiet_hours` | `[23, 8]` | 静默时段（跨午夜） |

## 在 herdr 里怎么接的

- `[[startup]]` → `main.py startup`：建好 state/config 目录。
- `[[events]] on = "pane.agent_status_changed"` → `main.py event`：
  读 payload 里的状态，只有 `idle`/`done` 才考虑提醒，再套上节流和静默时段，
  最多发一条 `herdr notification show`。默认不自动开窗格（`nudge.auto_open = true` 可以开）。
  注意 herdr 0.9.x 里 `agent.idle` **不是**合法事件名，会告警。
- `[[panes]] break`：split，跑 `main.py drill`。
  （原来是 popup，但 popup 关闭时要 1s 左右，split 只要 40ms，对「90 秒一组」来说太不值。）
- `[[panes]] stats`：popup，跑 `main.py stats --wait`。
- `[[actions]]`：八个动作（各模式 + 进度 + 手动提醒）。**action 没有 PTY**，
  所以每个交互动作都是 `main.py open-pane …`，由它去调 `herdr plugin pane open`。

## 数据存在哪

```
~/.local/state/herdr/plugins/herdr.words/
├── progress.json        # 每个词的状态、每日统计（原子写 + flock）
├── nudge.json           # 上次提醒时间
└── books/*.json         # 导入的自定义词书
~/.config/herdr/plugins/config/herdr.words/settings.json
```

在 herdr 外面用 `words …` 时，会自动沿用同一个目录（如果它已存在），
所以终端里练的和 popup 里练的是同一份进度；只有完全没有 herdr 时才会落到
`~/.local/state/herdr-words/`。

`progress.json` 是人类可读的 JSON，坏了会自动备份成 `progress.corrupt-<ts>.json` 并重新开始，
不会让插件起不来。`words reset --yes` 清空进度。

## 开发

```bash
python3 -m pytest tests/ -q       # 137 个测试，含真实 pty 的端到端跑测
python3 main.py drill --once --no-color --width 76 --height 20   # 看渲染
```

- `scripts/install.sh` 安装（link 插件 + words 命令 + 键位 + 重载）
- `worddrill/data.py` 词书解析（TSV/CSV/JSON）
- `worddrill/srs.py` SM-2 变体与组题策略
- `worddrill/session.py` 打字/提示/判分状态机
- `worddrill/ui.py` 无第三方依赖的终端渲染与按键解码
- `worddrill/store.py` 进度与设置持久化
- `worddrill/herdr.py` 对 herdr CLI 的薄封装
- `worddrill/cli.py` 子命令

更细的设计取舍见 [docs/design.md](docs/design.md)，词书格式见
[docs/wordbook-format.md](docs/wordbook-format.md)。

## 排错

**弹出后一片空白？**

1. 先确认宿主主题：`words stats --theme light` 和 `--theme dark` 各看一次，
   哪个看得清就 `words settings theme=light`（或 `dark`）固定下来。
   默认的 `auto` 用终端自身前景色画正文、用深浅背景都能读的中间调画强调色，
   所以正常情况不需要改。
2. 确认进程起来了：`pgrep -f "main.py drill"` 应该有输出。
3. 看 herdr 侧日志：`herdr plugin log list`，失败的调用会带 stderr。
4. `words doctor` 会打印 python、目录、发音引擎、词书是否正常。

**中文/边框看起来错位？**

宽度按显示列（CJK = 2 列）计算，并且刻意不用"宽度取决于字体"的字符做布局：

- 分隔符是 ASCII 的 `|`，不是 `·`（`·` 在中文环境常被渲染成 2 列，会把底栏撑歪）
- `…`、`—`、`→` 也都换成了 ASCII
- 边框用制表符（`─│╭╮╰╯`），这类字形在所有等宽字体里恒为 1 列
- 窄窗口下按键提示整条丢弃（`esc 退出` 永远保留），不会把汉字劈成两半

回归测试守着：顶栏/底栏必须收口到同一列、输入框三条边等宽、状态栏与底栏不得出现
宽度不确定字形（`·`、`—`、`…`、`→`、`●`）。

**输入单词没反应？**

已在 2026-10-29 修复：界面在"终端尺寸没变"时会跳过重绘，导致敲键后不刷新，
只有拼完（自动提交）或按回车才看得见。现在每次按键都强制重绘。

如果还遇到类似"输入无响应"，先确认窗格是聚焦的（`herdr pane current`），
再 `words drill` 在普通 shell 里跑一次对比。

**按 Esc 关窗有点慢？（herdr 侧，不是插件）**

现象：所有弹窗（包括 herdr 内置的）都要等一会儿才关。

原因在 herdr 客户端：它收到单独 `Esc` 后要等一个 input timeout / 一次 flush，才能判断这是
"纯 Esc" 还是 Alt 组合键的开头。client 日志里能直接看到：

```
WARN herdr::raw_input: flushing lone escape after input timeout;
     if this follows an alt chord or focus switch it may reach the pane as plain esc
```

验证方法：绕过 client、直接用 API 送 Esc，窗格 40ms 就消失：

```bash
herdr pane send-keys <PANE_ID> esc     # 40ms
```

**绕过办法**：按 `Ctrl+C` 退出。控制字符没有 Esc 消歧，client 会立刻转发。
底栏提示现在也写成 `esc/⌃c 退出`。

现在默认用 `split`，按 Esc → 窗格消失实测 **40ms**（含落盘、关窗）。

早期版本用的是 `popup`：进程 40ms 就退了，但弹窗在屏幕上要挂 1 秒多才收掉。
如果你的 herdr 版本对 popup 处理不同，可以改 manifest 里 `break` 的 placement 对比：

```toml
[[panes]]
id = "break"
placement = "popup"   # 需要同时加 width = "72%" / height = "70%"
```

**其他常查项**

- 没声音：`words doctor` 里 pronunciation 是否 ok；或 `words settings sound=false`
  确认不是音量问题。
- 键位不生效：`herdr config check`，再 `herdr server reload-config`。
- 进度看着不对：`words stats`，或直接看
  `~/.local/state/herdr/plugins/herdr.words/progress.json`。

## 已知边界

- 只在 Linux / macOS 上验证过（manifest 里也是这么声明的）；Windows 没测。
- 发音依赖系统 TTS，音色取决于装了什么。
- 词书是手写的精选集，不是完整四六级词库——够用来养成习惯，不够应付报名考试。
- 没有云同步：换机器需要自己拷 `progress.json`。