'''
将文件夹内所有视频转换为720p分辨率，使用GPU加速（NVIDIA NVENC）
方法为batch_convert_videos(input_folder, output_folder, max_workers=2)
'''


import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

# 直接使用物理 GPU 索引，不要设置 CUDA_VISIBLE_DEVICES
# CUDA_VISIBLE_DEVICES 会把 GPU 3 重映射为虚拟索引 0，与 ffmpeg 的 -hwaccel_device/-gpu 参数冲突
GPU_DEVICE_ID = 3

def convert_video_to_720p_gpu(input_path, output_path):
    """
    使用 GPU (NVIDIA NVENC) 加速转换视频为 720p
    流程：CUDA 硬件解码 → GPU 显存内 NPP 硬件缩放 → NVENC 硬件编码
    注意：不设置 CUDA_VISIBLE_DEVICES，直接用物理 GPU 索引
    """
    command = [
        'ffmpeg',
        # 1. 硬件解码（NVDEC），直接在 GPU 显存中解码
        '-hwaccel', 'cuda',
        '-hwaccel_device', str(GPU_DEVICE_ID),   # 使用物理 GPU 索引 3
        '-hwaccel_output_format', 'cuda',         # 解码结果留在 GPU 显存

        # 2. 输入文件
        '-i', input_path,

        # 3. 视频滤镜：scale_npp（libnpp 硬件缩放，比 scale_cuda 更稳定）
        #    数据全程在 GPU 显存中，无需 CPU<->GPU 拷贝
        '-vf', 'scale_npp=720:1280',

        # 4. 视频编码：NVENC 硬件编码
        '-c:v', 'h264_nvenc',
        '-gpu', str(GPU_DEVICE_ID),              # 编码也使用物理 GPU 索引 3
        '-preset', 'p4',    # p1最快质量低, p7最慢质量高, p4 为较好平衡点
        '-rc', 'vbr',       # 动态码率
        '-cq', '23',        # 质量参数，越小质量越好

        # 5. 音频直接复制，不重编码
        '-c:a', 'copy',

        # 6. 覆盖输出文件
        '-y',
        output_path
    ]

    try:
        subprocess.run(command, check=True, capture_output=True)
        return True, f"GPU转换成功: {os.path.basename(input_path)}"
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='ignore')
        return False, f"GPU转换失败: {os.path.basename(input_path)}\n错误: {error_msg}"


def batch_convert_videos(input_folder, output_folder, max_workers=2):
    """
    批量转换
    注意：GPU 并发数不宜过高，受限于显存大小。
    """
    if not os.path.exists(input_folder):
        print(f"错误：输入文件夹 '{input_folder}' 不存在")
        return

    os.makedirs(output_folder, exist_ok=True)

    video_extensions = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')
    video_files = [f for f in os.listdir(input_folder) if f.lower().endswith(video_extensions)]

    if not video_files:
        print("未找到视频文件")
        return

    print(f"找到 {len(video_files)} 个视频文件，开始 GPU {GPU_DEVICE_ID} 加速转换...")
    print("-" * 50)

    tasks = []
    for video_file in video_files:
        input_path = os.path.join(input_folder, video_file)
        output_path = os.path.join(output_folder, video_file)
        tasks.append((input_path, output_path))

    success_count = 0
    fail_count = 0

    # max_workers 建议设为 2-4，受限于显存大小
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(convert_video_to_720p_gpu, inp, out) for inp, out in tasks]

        for future in futures:
            success, message = future.result()
            if success:
                success_count += 1
                print(f"✅ {message}")
            else:
                fail_count += 1
                print(f"❌ {message}")

    print("-" * 50)
    print(f"转换完成！成功: {success_count} 个, 失败: {fail_count} 个")


# ================= 使用示例 =================
if __name__ == "__main__":
    source_dir = "../video"
    target_dir = "../video_720"

    # 开启 2 个并发（根据显存大小调整，显存大可以设为 4）
    batch_convert_videos(source_dir, target_dir, max_workers=100)
