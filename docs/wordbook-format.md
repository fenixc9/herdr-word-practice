# 词书格式

词书有两种写法：TSV（推荐，信息最全）和 JSON（好导入）。CSV 是 JSON 的简化入口。

## TSV

每行一个词，9 列用 `Tab` 分隔；列不够时后面的留空即可（末尾的 `syn`、`root`、`phr`
最常省略）。
文件开头可以有 `# key=value` 元数据行。

```tsv
# id=coding
# name=程序员英语
# name_en=Coding English
# description=vibe coding 里天天见的技术词
deploy	/dɪˈplɔɪ/	v.	部署	We deploy twice a day behind a flag.	我们每天在开关后面部署两次。	release,roll out	de-（去掉）+ ploy（折叠）	deploy to production,roll out a release
```

| 列 | 键 | 必填 | 说明 |
| --- | --- | --- | --- |
| 1 | `w` | 是 | 单词。同一本词书里不能重复（大小写不敏感） |
| 2 | `ipa` | 否 | 音标，例如 `/kæʃ/` |
| 3 | `pos` | 否 | 词性，例如 `n.`、`v.`、`adj.` |
| 4 | `cn` | 是 | 中文释义；多义用「；」分隔 |
| 5 | `en` | 否 | 英文例句 |
| 6 | `zh` | 否 | 例句的中文翻译 |
| 7 | `syn` | 否 | 近义词，用 `,` 分隔 |
| 8 | `root` | 否 | 词根/词源/助记 |
| 9 | `phr` | 否 | 常见搭配，用 `,` 分隔；答完题后显示 |

元数据键：

| 键 | 说明 |
| --- | --- |
| `id` | 词书 id，命令行里 `-b` 用它。缺省时取文件名 |
| `name` | 显示名，例如 `程序员英语` |
| `name_en` | 英文名，可省 |
| `description` | 一句话说明，`words books` 里显示 |

解析很严格，坏数据会直接报错而不是悄悄跳过——因为你自己也会是这份数据的使用者：

```
data/wordbooks/x.tsv line 12: duplicate 'cache'
data/wordbooks/x.tsv line 4: missing or empty 'cn'
```

### 为什么例句很重要

`dictation` 模式会把例句里的目标词挖掉变成 `______`：

```
Keep a ______ ready before you deploy.
```

所以词书里有例句，默写模式才有语境可用；只有中文释义时它会退化成纯拼写练习。

## JSON

```json
{
  "id": "mine",
  "name": "我的词表",
  "description": "从错题本里抄下来的",
  "words": [
    {"w": "cache", "ipa": "/kæʃ/", "pos": "n.", "cn": "缓存",
     "en": "The cache hides the real latency.", "zh": "缓存掩盖了真实延迟。",
     "syn": ["store", "buffer"], "root": "cach（藏）",
     "phr": ["cache hit", "cache miss"]},
    {"word": "rollback", "meaning": "回滚"}
  ]
}
```

为了手写方便，键名支持长写别名：

| 短名 | 长名 |
| --- | --- |
| `w` | `word`, `english` |
| `cn` | `meaning`, `zh_meaning`, `translation` |
| `en` | `example`, `sentence` |
| `zh` | `example_zh`, `example_translation` |
| `phr` | `phrases`, `collocations` |

`ipa` / `pos` / `syn` / `root` 只认本名。只有 `w`（单词）和 `cn`（释义）是必填的；
其余留空时界面上对应行直接不显示。

## CSV

两列：`单词,释义`，第一行若是 `word,meaning` 这样的表头会自动跳过。

```csv
word,meaning
cache,缓存
schema,表结构
```

## 导入

```bash
words import ~/mine.tsv                 # id 取自元数据或文件名
words import ~/mine.json --id mine --name 我的词
words import ~/mine.csv --use           # 导入并切为默认词书
```

导入的文件会复制到状态目录：

```
~/.local/state/herdr/plugins/herdr-word-practice/books/mine.json
```

统一转成 JSON 存放（哪怕你导入的是 TSV），因为这样才能保留元数据。
想改内容，直接改这个 JSON 再 `words books` 看效果即可；删掉文件就等于删掉词书。