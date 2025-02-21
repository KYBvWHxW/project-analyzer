import os
import json
import asyncio
import aiohttp
import argparse
from dotenv import load_dotenv
from tqdm import tqdm
from datetime import datetime
import time

# Load environment variables
load_dotenv()

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
if not OPENROUTER_API_KEY:
    raise ValueError("Please set OPENROUTER_API_KEY environment variable")

# 限制并发数和重试设置
MAX_CONCURRENT_REQUESTS = 2  # 最大并发请求数
MAX_RETRIES = 5  # 最大重试次数
RETRY_DELAY = 5  # 重试延迟（秒）
MAX_CONTENT_LENGTH = 8000  # 最大内容长度

# 要跳过的目录
SKIP_DIRS = {
    'node_modules',
    'venv',
    '.git',
    '__pycache__',
    'dist',
    'build',
    '.idea',
    '.vscode',
    'vendor',
    'packages',
    'system',  # 系统模块目录
}

# 要分析的文件类型
ANALYZE_EXTENSIONS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.vue', '.java',
    '.cpp', '.c', '.h', '.hpp', '.cs', '.go', '.rb', '.php',
    '.html', '.css', '.scss', '.less', '.sql', '.md', '.json',
    '.yaml', '.yml', '.xml', '.sh', '.bash'
}

async def get_file_content(file_path):
    """Read file content safely."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

async def truncate_content(content, max_length):
    """智能截断内容"""
    if len(content) <= max_length:
        return content
    
    # 保留前半部分和后半部分
    half_length = max_length // 2
    return content[:half_length] + "\n...(内容已截断)...\n" + content[-half_length:]

async def analyze_with_claude(content, directory_name, retry_count=0):
    """发送内容到Claude进行分析"""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
    }
    
    # 截断内容
    truncated_content = await truncate_content(content, MAX_CONTENT_LENGTH)
    
    prompt = f"""请分析以下代码的结构和实现:
1. 功能概述
- 此代码的主要目标和用途是什么?
- 解决了什么具体业务/技术问题?
- 主要的输入输出是什么?

2. 架构设计
- 整体架构和模块划分
- 核心类/接口及其职责
- 关键的设计模式应用

3. 实现细节
- 主要函数的功能说明和实现逻辑
- 关键算法和数据结构
- 异常处理机制
- 性能相关的实现

4. 依赖分析
- 外部依赖项及其版本
- 模块间的依赖关系
- 关键的第三方库使用

5. 核心流程
- 主要业务流程的实现步骤
- 关键的控制流程
- 数据流转过程


分析内容:
{truncated_content}
"""

    data = {
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        async with aiohttp.ClientSession() as session:
            print(f"发送请求到 OpenRouter API...")
            print(f"请求头: {headers}")
            print(f"请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
            
            async with session.post(url, headers=headers, json=data) as response:
                response_text = await response.text()
                print(f"API响应状态码: {response.status}")
                print(f"API响应内容: {response_text}")
                
                if response.status == 200:
                    try:
                        result = json.loads(response_text)
                        content = result['choices'][0]['message']['content']
                        print(f"成功获取分析结果，长度: {len(content)}字符")
                        return content
                    except json.JSONDecodeError as e:
                        print(f"JSON解析错误: {str(e)}")
                        raise
                    except KeyError as e:
                        print(f"响应格式错误: {result}")
                        print(f"缺少键: {str(e)}")
                        raise
                elif response.status == 429:
                    if retry_count < MAX_RETRIES:
                        wait_time = RETRY_DELAY * (retry_count + 1)
                        print(f"触发速率限制，等待 {wait_time} 秒后重试...")
                        await asyncio.sleep(wait_time)
                        return await analyze_with_claude(content, directory_name, retry_count + 1)
                    else:
                        return f"达到最大重试次数 ({MAX_RETRIES})，最后错误: {response_text}"
                else:
                    return f"API错误 (HTTP {response.status}): {response_text}"
    except aiohttp.ClientError as e:
        print(f"网络请求错误: {str(e)}")
        if retry_count < MAX_RETRIES:
            wait_time = RETRY_DELAY * (retry_count + 1)
            print(f"等待 {wait_time} 秒后重试...")
            await asyncio.sleep(wait_time)
            return await analyze_with_claude(content, directory_name, retry_count + 1)
        return f"网络错误 (重试{retry_count}次后): {str(e)}"
    except Exception as e:
        print(f"未预期的错误: {str(e)}")
        if retry_count < MAX_RETRIES:
            wait_time = RETRY_DELAY * (retry_count + 1)
            print(f"等待 {wait_time} 秒后重试...")
            await asyncio.sleep(wait_time)
            return await analyze_with_claude(content, directory_name, retry_count + 1)
        return f"错误 (重试{retry_count}次后): {str(e)}"

def should_analyze_file(file_path):
    """判断是否应该分析此文件"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in ANALYZE_EXTENSIONS

def should_skip_directory(dir_path):
    """判断是否应该跳过此目录"""
    dir_name = os.path.basename(dir_path)
    return dir_name in SKIP_DIRS

async def verify_markdown(content):
    """验证生成的markdown内容是否有效"""
    if not content or len(content.strip()) < 100:
        return False
    
    # 检查是否包含基本的markdown结构
    required_sections = [
        '功能概述', '架构设计', '实现细节',
        '依赖分析', '核心流程'
    ]
    
    return all(section in content for section in required_sections)

async def analyze_single_directory(directory, base_dir):
    """分析单个目录下的所有文件"""
    if should_skip_directory(directory):
        print(f"跳过系统目录: {directory}")
        return
    
    files = []
    content_parts = []
    
    # 只获取当前目录下的文件，不包括子目录
    for item in os.listdir(directory):
        full_path = os.path.join(directory, item)
        if os.path.isfile(full_path):
            if not should_analyze_file(full_path):
                continue
            files.append(full_path)
    
    if not files:  # 如果没有文件，跳过分析
        return
    
    print(f"\n分析目录: {directory}")
    print(f"发现 {len(files)} 个文件...")
    
    for file_path in tqdm(files):
        rel_path = os.path.relpath(file_path, directory)
        content = await get_file_content(file_path)
        content_parts.append(f"\n### File: {rel_path}\n```\n{content}\n```")
    
    full_content = "\n".join(content_parts)
    dir_name = os.path.relpath(directory, base_dir)
    
    print("发送到Claude进行分析...")
    analysis = await analyze_with_claude(full_content, dir_name)
    
    # 验证分析结果并在必要时重试
    retry_count = 0
    while retry_count < MAX_RETRIES:
        if await verify_markdown(analysis):
            # 分析结果有效，保存文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(directory, f"directory_analysis_{timestamp}.md")
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(analysis)
            
            print(f"✅ 分析完成！报告已保存到: {output_file}")
            return
        
        # 分析结果无效，重试
        retry_count += 1
        if retry_count < MAX_RETRIES:
            print(f"⚠️ {directory} 的分析结果无效，第 {retry_count} 次重试...")
            await asyncio.sleep(RETRY_DELAY * retry_count)
            analysis = await analyze_with_claude(full_content, dir_name)
        else:
            print(f"❌ {directory} 的分析在 {MAX_RETRIES} 次尝试后仍然失败")

async def process_all_directories(base_dir):
    """处理所有目录"""
    dirs_to_process = []
    
    # 收集所有目录
    for root, dirs, _ in os.walk(base_dir):
        # 跳过node_modules目录
        if 'node_modules' in root:
            continue
        dirs_to_process.append(root)
    
    print(f"\n找到 {len(dirs_to_process)} 个目录需要分析")
    
    # 创建信号量限制并发
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    async def process_with_semaphore(directory):
        async with semaphore:
            await analyze_single_directory(directory, base_dir)
    
    # 为每个目录创建一个任务
    tasks = [process_with_semaphore(d) for d in dirs_to_process]
    
    # 并发执行所有任务（受信号量限制）
    await asyncio.gather(*tasks)

async def main(target_dir):
    if not os.path.isdir(target_dir):
        print(f"错误: {target_dir} 不是一个有效的目录")
        return
    
    print(f"开始分析目录: {target_dir}")
    await process_all_directories(target_dir)
    print("\n所有目录分析完成！")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='项目代码分析器')
    parser.add_argument('path', nargs='?', default='/Users/paul/GiteeProjects/baozang_app',
                        help='要分析的项目路径（默认为/Users/paul/GiteeProjects/baozang_app）')
    
    args = parser.parse_args()
    asyncio.run(main(os.path.abspath(args.path)))
