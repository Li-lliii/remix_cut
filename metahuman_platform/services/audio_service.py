"""
数字人视频生成平台 - 音频处理服务 (修复版)
包含: 音频裁剪、ASR语音识别、TTS语音合成
"""
import os
import sys
import uuid
import tempfile
import shutil
import subprocess
from pathlib import Path
from typing import Optional
import logging

import librosa
import soundfile as sf
import numpy as np

# 添加项目路径到 sys.path
PROJECT_ROOT = Path("/zhouzhibiao/gen_video")
sys.path.insert(0, str(PROJECT_ROOT / "bs_media_dem/FireRedASR"))

logger = logging.getLogger(__name__)


class AudioService:
    """音频处理服务类"""
    
    def __init__(self, config):
        """
        初始化音频服务
        
        Args:
            config: 配置模块
        """
        self.config = config
        self.asr_model = None
        self._asr_loaded = False
        self._tts_loaded = False
        
        # 设置 GPU
        os.environ["CUDA_VISIBLE_DEVICES"] = config.GPU_DEVICE
    
    def load_asr_model(self):
        """延迟加载 ASR 模型"""
        if self._asr_loaded:
            return
        
        logger.info("正在加载 FireRedASR 模型...")
        try:
            from fireredasr.models.fireredasr import FireRedAsr
            self.asr_model = FireRedAsr.from_pretrained(
                self.config.ASR_MODEL_TYPE,
                str(self.config.ASR_MODEL_PATH)
            )
            self._asr_loaded = True
            logger.info("FireRedASR 模型加载完成")
        except Exception as e:
            logger.error(f"ASR 模型加载失败: {e}")
            raise
    
    def load_tts_engine(self):
        """检查 TTS 环境是否可用 - 完全通过 subprocess，避免直接导入"""
        if self._tts_loaded:
            return
        
        logger.info("检查 IndexTTS 环境...")
        try:
            # 检查 uv 环境中的 index-tts 目录
            tts_dir = self.config.PROJECT_ROOT / "bs_media_dem/index-tts"
            if not tts_dir.exists():
                raise Exception(f"IndexTTS 目录不存在: {tts_dir}")
            
            # 简单测试 uv run 是否可用 (不导入 IndexTTS 避免配置冲突)
            test_cmd = ["uv", "run", "--project", str(tts_dir), "python", "-c", "print('IndexTTS env ready')"]
            result = subprocess.run(
                test_cmd,
                cwd=str(tts_dir),
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                raise Exception(f"IndexTTS 环境测试失败: {result.stderr}")
            
            self._tts_loaded = True
            logger.info("IndexTTS 环境检查完成 - 将使用 subprocess 调用")
        except Exception as e:
            logger.error(f"TTS 环境检查失败: {e}")
            raise
    
    def trim_audio(self, audio_path: str, duration: float = 5.0, output_path: Optional[str] = None) -> str:
        """
        裁剪音频到指定时长
        
        Args:
            audio_path: 输入音频路径
            duration: 目标时长(秒)
            output_path: 输出路径，不指定则自动生成
            
        Returns:
            裁剪后的音频路径
        """
        logger.info(f"正在裁剪音频: {audio_path} -> {duration}秒")
        
        # 加载音频
        audio, sr = librosa.load(audio_path, sr=self.config.AUDIO_SAMPLE_RATE, mono=True)
        current_duration = librosa.get_duration(y=audio, sr=sr)
        
        if current_duration <= duration:
            logger.info(f"音频时长 {current_duration:.2f}s <= {duration}s，无需裁剪")
            if output_path:
                shutil.copy2(audio_path, output_path)
                return output_path
            return audio_path
        
        # 裁剪到指定时长
        samples_to_keep = int(duration * sr)
        trimmed_audio = audio[:samples_to_keep]
        
        # 保存裁剪后的音频
        if output_path is None:
            output_path = str(self.config.TEMP_DIR / f"trimmed_{uuid.uuid4().hex[:8]}.wav")
        
        sf.write(output_path, trimmed_audio, sr)
        logger.info(f"音频裁剪完成: {output_path}")
        
        return output_path
    
    def transcribe(self, audio_path: str) -> str:
        """
        语音识别 (ASR)
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            识别出的文本
        """
        self.load_asr_model()
        
        logger.info(f"正在进行语音识别: {audio_path}")
        
        uttid = f"task_{uuid.uuid4().hex[:8]}"
        
        # 加载音频并检查时长
        audio, sr = librosa.load(audio_path, sr=self.config.AUDIO_SAMPLE_RATE, mono=True)
        duration = librosa.get_duration(y=audio, sr=sr)
        
        # 对于短音频，直接识别
        results = self.asr_model.transcribe(
            [uttid],
            [audio_path],
            {
                "use_gpu": True,
                "beam_size": 3,
                "nbest": 1,
                "decode_max_len": 0,
                "softmax_smoothing": 1.25,
                "aed_length_penalty": 0.6,
                "eos_penalty": 1.0
            }
        )
        
        text = results[0]['text'] if results else ""
        logger.info(f"语音识别结果: {text}")
        
        return text
    
    def synthesize(self, reference_audio: str, target_text: str, output_path: Optional[str] = None) -> str:
        """
        语音合成 (TTS) - 使用参考音频进行声音克隆
        完全通过 uv 环境调用 IndexTTS，避免配置冲突
        
        Args:
            reference_audio: 参考音频路径 (用于声音克隆)
            target_text: 目标文本 (要合成的内容)
            output_path: 输出路径
            
        Returns:
            生成的音频路径
        """
        self.load_tts_engine()
        
        logger.info(f"正在进行语音合成: '{target_text[:50]}...'")
        
        if output_path is None:
            output_path = str(self.config.TEMP_DIR / f"tts_{uuid.uuid4().hex[:8]}.wav")
        
        # 通过 uv run 调用 IndexTTS
        tts_dir = self.config.PROJECT_ROOT / "bs_media_dem/index-tts"
        wrapper_script = self.config.BASE_DIR / "tts_wrapper.py"
        
        cmd = [
            "uv", "run", "--project", str(tts_dir),
            "python", str(wrapper_script),
            "--reference_audio", reference_audio,
            "--text", target_text,
            "--output", output_path,
            "--config_path", str(tts_dir / "checkpoints/config.yaml"),
            "--model_dir", str(tts_dir / "checkpoints")
        ]
        
        try:
            logger.info(f"执行 TTS 命令: {' '.join(cmd[:6])}...")
            result = subprocess.run(
                cmd,
                cwd=str(tts_dir),
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode != 0:
                logger.error(f"TTS 执行失败: {result.stderr}")
                raise Exception(f"语音合成失败: {result.stderr}")
            
            logger.info(f"语音合成完成: {output_path}")
            logger.debug(f"TTS 输出: {result.stdout}")
            
            # 验证输出文件是否存在
            if not Path(output_path).exists():
                raise Exception(f"输出文件未生成: {output_path}")
            
            return output_path
            
        except subprocess.TimeoutExpired:
            logger.error("TTS 执行超时")
            raise Exception("语音合成超时")
        except Exception as e:
            logger.error(f"TTS 执行异常: {e}")
            raise Exception(f"语音合成失败: {str(e)}")
    
    def process_audio_pipeline(self, user_audio: str, target_text: str) -> str:
        """
        完整的音频处理流水线:
        1. 裁剪用户音频到5秒
        2. 对裁剪后的音频进行ASR识别 (可选，用于日志记录)
        3. 使用裁剪后的音频作为参考进行TTS合成
        
        Args:
            user_audio: 用户上传的音频路径
            target_text: 用户想要合成的文本
            
        Returns:
            最终生成的音频路径
        """
        logger.info("开始音频处理流水线...")
        
        # Step 1: 裁剪音频到5秒
        trimmed_audio = self.trim_audio(
            user_audio,
            duration=self.config.AUDIO_CLIP_DURATION
        )
        
        # Step 2: ASR识别 (记录日志，便于调试)
        try:
            recognized_text = self.transcribe(trimmed_audio)
            logger.info(f"参考音频内容: {recognized_text}")
        except Exception as e:
            logger.warning(f"ASR识别失败 (不影响后续处理): {e}")
        
        # Step 3: TTS合成
        output_audio = self.synthesize(
            reference_audio=trimmed_audio,
            target_text=target_text
        )
        
        logger.info(f"音频处理流水线完成: {output_audio}")
        
        return output_audio