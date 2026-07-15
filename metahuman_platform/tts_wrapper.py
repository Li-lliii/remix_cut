#!/usr/bin/env python3
"""
临时 TTS 脚本 - 通过 uv 环境调用 IndexTTS
"""
import sys
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='IndexTTS 语音合成')
    parser.add_argument('--reference_audio', required=True, help='参考音频路径')
    parser.add_argument('--text', required=True, help='目标文本')
    parser.add_argument('--output', required=True, help='输出音频路径')
    parser.add_argument('--config_path', default='./checkpoints/config.yaml', help='配置文件路径')
    parser.add_argument('--model_dir', default='./checkpoints', help='模型目录')
    
    args = parser.parse_args()
    
    try:
        from indextts.infer_v2 import IndexTTS2
        
        print(f"正在初始化 IndexTTS...")
        tts = IndexTTS2(
            cfg_path=args.config_path,
            model_dir=args.model_dir,
            use_fp16=False
        )
        
        print(f"正在合成语音: '{args.text[:50]}...'")
        tts.infer(
            spk_audio_prompt=args.reference_audio,
            text=args.text,
            output_path=args.output,
            verbose=True
        )
        
        print(f"✓ 语音合成完成: {args.output}")
        
    except Exception as e:
        print(f"✗ 语音合成失败: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()