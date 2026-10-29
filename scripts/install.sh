#!/bin/sh
# 开发用安装脚本：把当前 checkout 链接进 herdr，再跑一次 setup。
#
# 正式安装请用 herdr 原生方式（不需要这个脚本）：
#   herdr plugin install fenixc9/herdr-word-practice --ref main
#   herdr plugin action invoke herdr-word-practice.setup
#
# 这个脚本只适合"我改着代码，想立刻在 herdr 里看到效果"：
#   ./scripts/install.sh            # link + setup
#   ./scripts/install.sh --dry-run  # 只打印将要做什么
set -eu

dry_run=0
[ "${1:-}" = "--dry-run" ] && dry_run=1

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(dirname -- "$here")

say() { printf '%s\n' "$*"; }
run() {
    if [ "$dry_run" = 1 ]; then
        say "  [dry-run] $*"
    else
        "$@"
    fi
}

say "插件目录: $root"

command -v herdr >/dev/null 2>&1 || {
    say "错误: 找不到 herdr，请先安装 https://herdr.dev" >&2
    exit 1
}
command -v python3 >/dev/null 2>&1 || {
    say "错误: 找不到 python3（本插件只用标准库，3.9+ 即可）" >&2
    exit 1
}
say "herdr: $(herdr --version 2>/dev/null || echo '?')  ·  python: $(python3 -V 2>&1)"

say ""
say "1/2 把本地 checkout 链接到 herdr（GitHub 安装的版本不需要这步）"
if herdr plugin list 2>/dev/null | grep -q 'herdr-word-practice'; then
    say "  已安装，重新链接以指向当前目录"
    run herdr plugin unlink herdr-word-practice || true
fi
run herdr plugin link "$root"

say ""
say "2/2 写入键位 / 链接 words 命令 / 重载配置"
if [ "$dry_run" = 1 ]; then
    run python3 "$root/main.py" setup --dry-run
else
    python3 "$root/main.py" setup
fi

say ""
say "卸载: herdr plugin unlink herdr-word-practice && rm -f \${WORDS_BIN_DIR:-\$HOME/.local/bin}/words"
say "（键位会留在 config.toml 里，不需要就手动删掉那三块）"