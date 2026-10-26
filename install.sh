#!/usr/bin/env bash
set -e

echo "=========================================="
echo " 🎬 Story Studio · 故事工坊 一键安装器"
echo "=========================================="

USER_HOME="$HOME"
TARGET_SKILLS_DIR=""

# 探测常见 Agent skills 目录
for candidate in "$USER_HOME/.codex/skills" "$USER_HOME/.claude/skills" "$USER_HOME/.agents/skills"; do
    parent_dir=$(dirname "$candidate")
    if [ -d "$parent_dir" ]; then
        TARGET_SKILLS_DIR="$candidate"
        break
    fi
done

if [ -z "$TARGET_SKILLS_DIR" ]; then
    TARGET_SKILLS_DIR="$USER_HOME/.codex/skills"
fi

mkdir -p "$TARGET_SKILLS_DIR"
DEST_DIR="$TARGET_SKILLS_DIR/story-studio"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "目标技能目录: $TARGET_SKILLS_DIR"
echo "安装路径: $DEST_DIR"

if [ "$SRC_DIR" = "$DEST_DIR" ]; then
    echo "[OK] 当前已经在目标技能目录中，无需重复复制。"
else
    echo "正在安装技能文件到 $DEST_DIR..."
    mkdir -p "$DEST_DIR"
    cp -R "$SRC_DIR"/* "$DEST_DIR"/
    echo "[OK] 技能文件安装完成！"
fi

if [ -f "$DEST_DIR/scripts/bootstrap.sh" ]; then
    echo ""
    echo "正在运行环境依赖检查..."
    bash "$DEST_DIR/scripts/bootstrap.sh" check || true
fi

echo ""
echo "=========================================="
echo "🎉 安装完成！"
echo "现在你可以在 AI Agent 中直接发送："
echo "  使用 \$story-studio，帮我一键配置全部运行环境。"
echo "=========================================="
