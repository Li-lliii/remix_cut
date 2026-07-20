"""
使用制定的Comfyui客户端进行工作流的视频生成。

输入视频和音频，输出对口型后的视频
"""
import json
import uuid
import time
import shutil
import urllib.request
import urllib.parse
import urllib.error
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ComfyUIClient:
    """ComfyUI 客户端类"""
    
    def __init__(self, config):
        """
        初始化 ComfyUI 客户端
        
        Args:
            config: 配置模块
        """
        self.config = config
        self.server_address = config['server_address']
        self.client_id = str(uuid.uuid4())
        self.workflow_path = config['workflow_path']
        
    def _request(self, endpoint: str, data: Optional[bytes] = None) -> Dict[str, Any]:
        """发送 HTTP 请求到 ComfyUI"""
        url = f"http://{self.server_address}/{endpoint}"
        req = urllib.request.Request(url, data=data)
        req.add_header('Content-Type', 'application/json')
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            logger.error(f"ComfyUI 请求失败: {e} body={body}")
            raise RuntimeError(f"HTTP Error {e.code}: {e.reason}; body={body}") from e
        except Exception as e:
            logger.error(f"ComfyUI 请求失败: {e}")
            raise
    
    def check_health(self) -> bool:
        """检查 ComfyUI 服务状态"""
        try:
            self._request("queue")
            return True
        except Exception:
            return False
    
    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        return self._request("queue")
    
    def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """获取任务历史"""
        return self._request(f"history/{prompt_id}")
    
    def queue_prompt(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """
        提交工作流到 ComfyUI
        
        Args:
            workflow: 工作流 JSON
            
        Returns:
            包含 prompt_id 的响应
        """
        run_id = str(uuid.uuid4())
        payload = {
            "prompt": workflow,
            "client_id": self.client_id,
            "extra_data": {
                "extra_pnginfo": {
                    "run_id": run_id
                }
            }
        }
        
        data = json.dumps(payload).encode('utf-8')
        return self._request("prompt", data)
    
    def copy_to_comfyui_input(self, file_path: str, filename: Optional[str] = None) -> str:
        """
        复制文件到 ComfyUI input 目录
        
        Args:
            file_path: 源文件路径
            filename: 目标文件名 (可选)
            
        Returns:
            目标文件名
        """
        source = Path(file_path)
        if filename is None:
            filename = f"{uuid.uuid4().hex[:8]}_{source.name}"
        
        target = Path(self.config['input_dir']) / filename
        
        # 确保目录存在
        target.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(source, target)
        logger.info(f"复制文件到 ComfyUI: {target}")
        
        return filename
    
    def load_workflow(self) -> Dict[str, Any]:
        """加载工作流模板"""
        with open(self.workflow_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def prepare_workflow(self, video_filename: str, audio_filename: str) -> Dict[str, Any]:
        """
        准备工作流，注入视频和音频输入
        需要修改对应的工作流，使用工作流中的节点来说明需要修改的节点和参数
        
        Args:
            video_filename: 视频文件名 (在 ComfyUI input 目录中)
            audio_filename: 音频文件名 (在 ComfyUI input 目录中)
            
        Returns:
            修改后的工作流
        """
        workflow = self.load_workflow()
        
        # 修改节点 47: VHS_LoadVideo - 注入视频
        if "47" in workflow:
            workflow["47"]["inputs"]["video"] = video_filename
            logger.info(f"设置视频输入: {video_filename}")
        else:
            logger.warning("工作流中未找到节点 47 (VHS_LoadVideo)")
        
        # 修改节点 55: LoadAudio - 注入音频
        if "55" in workflow:
            workflow["55"]["inputs"]["audio"] = audio_filename
            logger.info(f"设置音频输入: {audio_filename}")
        else:
            logger.warning("工作流中未找到节点 55 (LoadAudio)")
        
        # 修改节点 46: VHS_VideoCombine - 更新输出前缀
        if "46" in workflow:
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H%M%S")
            workflow["46"]["inputs"]["filename_prefix"] = f"metahuman/{date_str}/{time_str}"
        
        # 更新随机种子以确保每次生成不同结果
        import random
        if "53" in workflow:  # WanVideoSampler
            workflow["53"]["inputs"]["seed"] = random.randint(0, 2**50 - 1)
        
        return workflow
    
    def submit_job(self, video_path: str, audio_path: str) -> str:
        """
        提交视频生成任务
        
        Args:
            video_path: 原始视频路径
            audio_path: 生成的音频路径
            
        Returns:
            任务 ID (prompt_id)
        """
        logger.info("正在提交 ComfyUI 任务...")
        
        # 复制文件到 ComfyUI input 目录
        video_filename = self.copy_to_comfyui_input(video_path)
        audio_filename = self.copy_to_comfyui_input(audio_path)
        
        # 准备工作流
        workflow = self.prepare_workflow(video_filename, audio_filename)
        
        # 提交任务
        result = self.queue_prompt(workflow)
        
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            error = result.get("error", "未知错误")
            raise Exception(f"任务提交失败: {error}")
        
        logger.info(f"任务提交成功: {prompt_id}")
        return prompt_id
    
    def wait_for_completion(self, prompt_id: str, timeout: int = 900, poll_interval: int = 5) -> Dict[str, Any]:
        """
        等待任务完成
        
        Args:
            prompt_id: 任务 ID
            timeout: 超时时间(秒)
            poll_interval: 轮询间隔(秒)
            
        Returns:
            任务结果
        """
        logger.info(f"等待任务完成: {prompt_id}")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                history = self.get_history(prompt_id)
                
                if prompt_id not in history:
                    time.sleep(poll_interval)
                    continue
                
                task_data = history[prompt_id]
                status = task_data.get('status', {}).get('status_str', '').lower()
                
                if status in ('success', 'completed'):
                    logger.info(f"任务完成: {prompt_id}")
                    return {
                        "status": "success",
                        "data": task_data
                    }
                
                if status in ('error', 'failed'):
                    logger.error(f"任务失败: {prompt_id}")
                    return {
                        "status": "error",
                        "data": task_data,
                        "errors": task_data.get('node_errors', {})
                    }
                
            except Exception as e:
                logger.warning(f"查询任务状态失败: {e}")
            
            time.sleep(poll_interval)
        
        logger.error(f"任务超时: {prompt_id}")
        return {"status": "timeout"}
    
    def extract_output_video(self, task_data: Dict[str, Any]) -> Optional[str]:
        """
        从任务结果中提取输出视频路径
        
        Args:
            task_data: 任务数据
            
        Returns:
            视频文件路径
        """
        VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.mkv', '.avi'}
        outputs = task_data.get('outputs', {})
        
        for output in outputs.values():
            for key in ('videos', 'gifs', 'video'):
                for item in output.get(key, []):
                    filename = item.get('filename', '')
                    suffix = Path(filename).suffix.lower()
                    fmt = (item.get('format') or '').lower()
                    
                    if fmt.startswith('video/') or suffix in VIDEO_EXTENSIONS:
                        fullpath = item.get('fullpath')
                        if fullpath and Path(fullpath).exists():
                            return fullpath
        
        return None
    
    def generate_video(self, video_path: str, audio_path: str, timeout: int = 900) -> Dict[str, Any]:
        """
        完整的视频生成流程
        
        Args:
            video_path: 原始视频路径
            audio_path: 生成的音频路径
            timeout: 超时时间
            
        Returns:
            包含状态和输出路径的结果
        """
        # 提交任务
        prompt_id = self.submit_job(video_path, audio_path)
        
        # 等待完成
        result = self.wait_for_completion(prompt_id, timeout)
        
        if result["status"] == "success":
            output_path = self.extract_output_video(result["data"])
            if output_path:
                # 复制到输出目录
                output_filename = f"metahuman_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                final_path = Path(self.config["output_dir"]) / output_filename
                shutil.copy2(output_path, final_path)
                
                return {
                    "status": "success",
                    "prompt_id": prompt_id,
                    "output_path": str(final_path),
                    "filename": output_filename
                }
            else:
                return {
                    "status": "error",
                    "prompt_id": prompt_id,
                    "message": "无法找到输出视频"
                }
        
        return {
            "status": result["status"],
            "prompt_id": prompt_id,
            "message": result.get("errors", "任务失败")
        }

    def submit_video_job(self, video_path: str, audio_path: str) -> Dict[str, Any]:
        prompt_id = self.submit_job(video_path, audio_path)
        return {"status": "submitted", "prompt_id": prompt_id}

    def poll_video_job(self, prompt_id: str) -> Dict[str, Any]:
        history = self.get_history(prompt_id)
        if prompt_id not in history:
            return {"status": "pending", "prompt_id": prompt_id}

        task_data = history[prompt_id]
        status = task_data.get("status", {}).get("status_str", "").lower()
        if status in ("success", "completed"):
            output_path = self.extract_output_video(task_data)
            if not output_path:
                return {
                    "status": "error",
                    "prompt_id": prompt_id,
                    "message": "无法找到输出视频",
                }
            output_filename = f"metahuman_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            final_path = Path(self.config["output_dir"]) / output_filename
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output_path, final_path)
            return {
                "status": "success",
                "prompt_id": prompt_id,
                "output_path": str(final_path),
                "filename": output_filename,
            }
        if status in ("error", "failed"):
            return {
                "status": "error",
                "prompt_id": prompt_id,
                "message": task_data.get("node_errors", {}) or "任务失败",
            }
        return {"status": "pending", "prompt_id": prompt_id}

if __name__ == "__main__":
    import yaml
    with open('./function/remix_cut/config.yaml', 'r') as f:
        config = yaml.safe_load(f) 
    comfyui_client = ComfyUIClient(config['comfyui'])
    video_path = "/home/kemove/zhouzhibao/bs_media/function/remix_cut/test_video/25410_3mins.mp4"
    audio_path = "/home/kemove/zhouzhibao/bs_media/function/remix_cut/output/tts_test/dongbei_clone_5s.wav"
    results = comfyui_client.generate_video(video_path, audio_path)
    
