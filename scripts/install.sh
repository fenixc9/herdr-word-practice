#!/bin/sh
# 安装 word-practice：链接插件、放好 words 命令、写入键位、重载 herdr 配置。
#
# 每一步都是幂等的，可以反复跑：
#   ./scripts/install.sh          # 正常安装
#   ./scripts/install.sh --dry-run  # 只打印将要做什么
set -eu

dry_run=0
[ "${1:-}" = "--dry-run" ] && dry_run=1

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(dirname -- "$here")
config_file=${HERDR_CONFIG:-$HOME/.config/herdr/config.toml}
bin_dir=${WORDS_BIN_DIR:-$HOME/.local/bin}
marker="# word-practice: 在 vibe coding 的间隙背单词"

say() { printf '%s\n' "$*"; }
run() {
    if [ "$dry_run" = 1 ]; then
        say "  [dry-run] $*"
    else
        "$@"
    fi
}

say "插件目录: $root"

# 0. 前置检查 -------------------------------------------------------------
if ! command -v herdr >/dev/null 2>&1; then
    say "错误: 找不到 herdr，请先安装 https://herdr.dev" >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    say "错误: 找不到 python3（本插件只用标准库，3.9+ 即可）" >&2
    exit 1
fi
say "herdr: $(herdr --version 2>/dev/null || echo '?')  ·  python: $(python3 -V 2>&1)"

# 1. 链接插件 -------------------------------------------------------------
say ""
say "1/4 链接插件到 herdr"
linked=$(herdr plugin list 2>/dev/null | grep -c '^- herdr\.words ' || true)
if [ "${linked:-0}" -gt 0 ]; then
    say "  已链接，跳过"
else
    run herdr plugin link "$root"
fi

# 2. 安装 words 命令 ------------------------------------------------------
say ""
say "2/4 安装 words 命令到 $bin_dir"
run mkdir -p "$bin_dir"
if [ -L "$bin_dir/words" ] || [ -e "$bin_dir/words" ]; then
    say "  已存在，覆盖为指向本插件的软链"
    run rm -f "$bin_dir/words"
fi
run ln -s "$root/scripts/words" "$bin_dir/words"
case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *) say "  注意: $bin_dir 不在 PATH 里，需要自己加一下" ;;
esac

# 3. 写入键位（幂等） -----------------------------------------------------
say ""
say "3/4 配置键位（$config_file）"
if [ ! -f "$config_file" ]; then
    run mkdir -p "$(dirname -- "$config_file")"
    run touch "$config_file"
fi
if grep -qF "$marker" "$config_file" 2>/dev/null; then
    say "  已配置过，跳过"
else
    say "  追加 prefix+w / prefix+shift+w / prefix+alt+w"
    block="$marker（prefix+w 打开一组，约 90 秒）。
[[keys.command]]
key = \"prefix+w\"
type = \"plugin_action\"
command = \"herdr-word-practice.drill\"
description = \"背单词\"

[[keys.command]]
key = \"prefix+shift+w\"
type = \"plugin_action\"
command = \"herdr-word-practice.dictation\"
description = \"背单词：默写\"

[[keys.command]]
key = \"prefix+alt+w\"
type = \"plugin_action\"
command = \"herdr-word-practice.stats\"
description = \"背单词：学习进度\""
    if [ "$dry_run" = 1 ]; then
        say "  [dry-run] 追加 3 个 [[keys.command]] 到 $config_file"
    else
        printf '\n%s\n' "$block" >>"$config_file"
    fi
fi

# 4. 重载 + 自检 ----------------------------------------------------------
say ""
say "4/4 重载配置并自检"
run herdr server reload-config
if [ "$dry_run" = 0 ]; then
    herdr config check
fi

say ""
if command -v words >/dev/null 2>&1 || [ "$dry_run" = 1 ]; then
    run words doctor
fi

say ""
say "装好了。在 herdr 里按 prefix+w 开始（第一次会弹出一个卡片窗格）。"
say "其他命令: words books · words stats · words settings · words doctor"
say "卸载: herdr plugin unlink herdr-word-practice && rm -f $bin_dir/words"
say "（键位会留在 config.toml 里，不需要就手动删掉那三块）"