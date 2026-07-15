#!/bin/bash
# 测试 TTS 包装器脚本

cd /zhouzhibiao/gen_video/bs_media_dem/metahuman_platform

echo "========================================"
echo "  测试 TTS 包装器"  
echo "========================================"

# 检查必要的文件
TTS_DIR="/zhouzhibiao/gen_video/bs_media_dem/index-tts"
WRAPPER_SCRIPT="./tts_wrapper.py"

if [ ! -f "$WRAPPER_SCRIPT" ]; then
    echo "✗ TTS 包装器脚本不存在: $WRAPPER_SCRIPT"
    exit 1
fi

if [ ! -d "$TTS_DIR" ]; then
    echo "✗ IndexTTS 目录不存在: $TTS_DIR"
    exit 1
fi

echo "✓ 文件检查通过"

# 测试 uv 环境
echo "测试 uv 环境..."
cd "$TTS_DIR"
if uv run python -c "from indextts.infer import IndexTTS; print('IndexTTS 导入成功')" 2>/dev/null; then
    echo "✓ uv 环境正常，IndexTTS 可用"
else
    echo "✗ uv 环境异常，IndexTTS 不可用"
    exit 1
fi

echo ""
echo "环境检查完成！可以启动数字人平台了。"
echo "运行: ./start.sh"