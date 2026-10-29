# herdr words

在 vibe coding 的间隙背单词。

一个 herdr 插件：按 `prefix+w`，弹出一张卡片，打一个词，90 秒后回到代码。
它借鉴了 [TypeWords](https://github.com/zyronon/TypeWords) 的思路——**靠打字回忆，而不是翻看**——
再把「间隔重复 + 打字判分 + 音标/例句/词根」压进一个能塞进 popup 的终端界面。

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
- **只占用眼前这一小块。** popup 悬浮在当前 tab 上，不抢布局，关掉就回到原来的光标位置。
- **主动提醒但不烦人。** agent 干完活变空闲时才提醒，45 分钟内只提醒一次，23:00–08:00 静默。

## 安装

```bash
herdr plugin link ~/project/herdr-english-learn    # 本地目录
herdr plugin list                                  # 应当看到 herdr.words
```

需要 `python3`（3.9+，只用标准库）、`herdr >= 0.9.0`。发音用系统 TTS，
按 `espeak-ng` → `espeak` → `say` → `spd-say` 的顺序取第一个可用的；都没有就安静地跳过。

命令行工具叫 `words`，把它放进 PATH：

```bash
ln -s ~/project/herdr-english-learn/scripts/words ~/.local/bin/words
words --version
words doctor
```

（不想装也行：`python3 ~/project/herdr-english-learn/main.py drill` 等价，
在插件目录里 `./scripts/words drill` 也可以。）

绑定按键（`~/.config/herdr/config.toml`）：

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

然后 `herdr server reload-config`，按 `prefix+w` 就能开始。

## 八种模式

| 模式 | 命令 | 给什么 | 练什么 |
| --- | --- | --- | --- |
| 智能复习 | `-m smart` | 该复习的词 + 少量新词 | 默认模式：先还债，再学新 |
| 自由练习 | `-m free` | 这本词书里随便挑的词 | 不管记忆曲线，想练就练 |
| 跟打 | `-m follow` | 单词、音标、释义、例句 | 建立拼写手感，最适合第一次见 |
| 默写 | `-m dictation` | 长度提示 + 挖空例句 | 从语境回忆拼写 |
| 看中文拼写 | `-m spelling` | 只有中文释义 | 最硬的回忆：从意义找形式 |
| 自测 | `-m selfcheck` | 单词 + 释义，按 1–4 自评 | 通勤/开会时不动手也能过 |
| 错词本 | `-m review` | 拼错过的词 | 专治反复错的词 |
| 收藏夹 | `-m favorites` | 你按过 Ctrl+F 的词 | 自己攒的难词表 |

`smart` 会看每个词的状态：到期的先来，其次是学习中、错得多的，最后才补新词
（每天新词上限默认 8 个，可在设置里改）。新词第一次出现用「跟打」露出全词，
之后再遇到就变成挖空默写——这是 TypeWords 里「先跟打后默写」的思路。

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
| `1`–`4` | 自测模式：不认识 / 模糊 / 认识 / 太简单 |
| `?` | 帮助 |
| `Esc` | 退出（自动保存） |

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

内置三本，共 1146 个词：

| id | 名称 | 词数 | 内容 |
| --- | --- | --- | --- |
| `cet4` | CET-4 核心 | 549 | 四级高频词，够用在阅读和写作 |
| `cet6` | CET-6 进阶 | 320 | 六级进阶词，也是技术文档里的常客 |
| `coding` | 程序员英语 | 277 | 日志、commit、文档里天天见的词 |

每个词都有音标、词性、中文释义、英文例句 + 中文翻译、近义词；答错/答对之后还会给出
常见搭配（436 个词）和词源拆解（110 个词），比如 `deploy` → `deploy to production`、
`de-（去掉）+ ploy（折叠）→ 展开`。例句都是技术或日常语境，比如
`The cache hides the real latency.`

```bash
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
- `[[panes]] break`：popup，72% × 70%，跑 `main.py drill`。
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
python3 -m pytest tests/ -q       # 116 个测试，含真实 pty 的端到端跑测
python3 main.py drill --once --no-color --width 76 --height 20   # 看渲染
```

- `worddrill/data.py` 词书解析（TSV/CSV/JSON）
- `worddrill/srs.py` SM-2 变体与组题策略
- `worddrill/session.py` 打字/提示/判分状态机
- `worddrill/ui.py` 无第三方依赖的终端渲染与按键解码
- `worddrill/store.py` 进度与设置持久化
- `worddrill/herdr.py` 对 herdr CLI 的薄封装
- `worddrill/cli.py` 子命令

更细的设计取舍见 [docs/design.md](docs/design.md)，词书格式见
[docs/wordbook-format.md](docs/wordbook-format.md)。

## 已知边界

- 只在 Linux / macOS 上验证过（manifest 里也是这么声明的）；Windows 没测。
- 发音依赖系统 TTS，音色取决于装了什么。
- 词书是手写的精选集，不是完整四六级词库——够用来养成习惯，不够应付报名考试。
- 没有云同步：换机器需要自己拷 `progress.json`。