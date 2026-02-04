import os
import httpx
import json
from opencode_ai import Opencode, DefaultHttpxClient
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict


class DebugHttpxClient(DefaultHttpxClient):
    def request(self, *args, **kwargs):
        try:
            response = super().request(*args, **kwargs)
            if response.status_code >= 400:
                try:
                    content = response.content.decode('utf-8', errors='replace')
                    print(f"HTTP错误响应 (状态码 {response.status_code}): {content[:500]}")
                except:
                    print(f"HTTP错误响应 (状态码 {response.status_code}): 无法解码响应内容")
            return response
        except Exception as e:
            print(f"HTTP请求异常: {type(e).__name__}: {e}")
            raise


class OpencodeAgent:
    def __init__(self, base_url: str = None, username: str = None, password: str = None):
        """初始化OpencodeAgent客户端
        
        Args:
            base_url: Opencode服务的基础URL，默认从环境变量OPENCODE_BASE_URL获取
            username: 用户名，默认从环境变量OPENCODE_USERNAME获取
            password: 密码，默认从环境变量OPENCODE_PASSWORD获取
        """
        self.base_url = base_url or os.environ.get("OPENCODE_BASE_URL", "http://10.10.23.103:4096")
        username = username or os.environ.get("OPENCODE_USERNAME", "opencode")
        password = password or os.environ.get("OPENCODE_PASSWORD", "opencode")
        
        if password:
            self.auth = httpx.BasicAuth(username, password)
            http_client = DebugHttpxClient(auth=self.auth)
            self.client = Opencode(base_url=self.base_url, http_client=http_client)
        else:
            self.auth = None
            http_client = DebugHttpxClient()
            self.client = Opencode(base_url=self.base_url, http_client=http_client)
    
    def list_sessions(self):
        """列出所有会话
        
        Returns:
            会话列表
        """
        try:
            sessions = self.client.session.list()
            return sessions
        except json.JSONDecodeError as e:
            raise ValueError(f"API返回了无效的JSON响应: {str(e)}。可能是服务器返回了空响应或非JSON格式的错误页面。请检查服务器状态、URL配置和认证信息。")
        except Exception as e:
            raise RuntimeError(f"获取会话列表失败: {str(e)}")
    
    def create_session(self, title: str = "My Session", directory: str = None):
        """创建新会话
        
        Args:
            title: 会话标题，默认为"My Session"
            directory: 项目目录，默认为"/data/soc/"
        Returns:
            新创建的会话对象
        """
        try:
            extra_query = {}
            if directory:
                extra_query["directory"] = directory
            
            new_session = self.client.session.create(
                extra_query=extra_query,
                extra_body={"title": title}
            )
            return new_session
        except json.JSONDecodeError as e:
            raise ValueError(f"API返回了无效的JSON响应: {str(e)}。可能是服务器返回了空响应或非JSON格式的错误页面。请检查服务器状态、URL配置和认证信息。")
        except Exception as e:
            raise RuntimeError(f"创建会话失败: {str(e)}")
    
    def send_prompt(self, session_id: str, message: str, provider_id: str = "deepseek", model_id: str = "deepseek-v3.1", directory: str = ""):
        """向指定会话发送提示消息
        
        Args:
            session_id: 会话ID
            message: 要发送的消息内容
            provider_id: 模型提供商ID，默认为"deepseek"
            model_id: 模型ID，默认为"deepseek-v3.1"
            directory: 项目目录，默认为"/data/LUCKYORDER/"
            
        Returns:
            AI的回复响应
        """
        try:
            extra_query = {}
            if directory:
                extra_query["directory"] = directory
            
            extra_body = {
                "parts": [
                    {
                        "type": "text",
                        "text": message
                    }
                ]
            }
            
            resp = self.client.session.chat(
                id=session_id,
                model_id=model_id,
                parts=extra_body["parts"],
                provider_id=provider_id,
                extra_query=extra_query,
                timeout=300000 # 5分钟
            )
            return resp
        except json.JSONDecodeError as e:
            raise ValueError(f"API返回了无效的JSON响应: {str(e)}。可能是服务器返回了空响应或非JSON格式的错误页面。请检查服务器状态、URL配置和认证信息。")
        except Exception as e:
            raise RuntimeError(f"发送消息失败: {str(e)}")

    def parse_response(self, resp):
        """解析响应结果
        
        Args:
            resp: 响应对象或字典
            
        Returns:
            解析后的文本结果，如果是JSON字符串则尝试解析为对象
        """
        if hasattr(resp, 'to_dict'):
            resp_dict = resp.to_dict()
        elif isinstance(resp, dict):
            resp_dict = resp
        else:
            raise ValueError(f"不支持的响应类型: {type(resp)}")
        
        parts = resp_dict.get("parts", [])
        for part in parts:
            if part.get("type") == "text":
                text = part.get("text", "")
                if text:
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text
        
        return None

    def audit_git_repo(self, git_url: str, branch_name: str=None, prompt_file: str = "prompt_git.txt", result_file: str = None):
        """对git代码进行安全审计
        
        Args:
            git_url: git仓库地址
            branch_name: 分支名
            prompt_file: 审计提示词文件路径，默认为"prompt.txt"
            result_file: 审计结果保存文件路径，如果为None则自动生成
            
        Returns:
            审计结果字典，包含session_id、审计结果等信息
        """
        if branch_name is None:
            clone_cmd = f"git clone --depth 1 {git_url}"
        else:
            clone_cmd = f"git clone -b {branch_name} --depth 1 {git_url}"

        prompt_pre = f"""
你是一个经验丰富的信息安全专家，正在对Git项目({git_url})进行安全审查。

上下文信息：
- Git项目地址：{git_url}
- 分支名：{branch_name}
- 克隆命令：{clone_cmd}

!{clone_cmd}

请先执行克隆命令，然后对代码进行安全审查，识别潜在的安全漏洞和风险。

"""
            
        session_title = f"安全审计-{git_url}#{branch_name or 'default'}"
        new_session = self.create_session(session_title)
        print(f"    创建会话: {new_session.id}")
        
        if os.path.exists(prompt_file):
            with open(prompt_file, "r", encoding="utf-8") as f:
                prompt = f.read()
        else:
            prompt = "请对当前代码工程进行全面的安全审计，识别潜在的安全漏洞和风险。"
        
        resp = self.send_prompt(new_session.id, prompt_pre + prompt)
        audit_result = self.parse_response(resp)
        self.send_prompt(new_session.id, "审查完毕，请删除克隆的代码目录。")
        
        audit_data = {
            "git_url": git_url,
            "branch_name": branch_name,
            "session_id": new_session.id,
            "session_title": session_title,
            "audit_result": audit_result,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        result_dir = "audit_results"
        os.makedirs(result_dir, exist_ok=True)
        
        if result_file is None:
            repo_name = os.path.basename(git_url).replace(".git", "")
            safe_branch = (branch_name or "default").replace("/", "_").replace("\\", "_")
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            result_file = f"audit_result_{repo_name}_{safe_branch}_{timestamp}.json"
        else:
            result_file = os.path.basename(result_file)
        
        result_path = os.path.join(result_dir, result_file)
        
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(audit_data, f, ensure_ascii=False, indent=2)
        
        print(f"    审计结果已保存到: {result_path}")
        
        return audit_data


def process_single_git(agent, git_url, completed_file, completed_lock, stats, max_retries=2):
    """处理单个git仓库的审计任务
    
    Args:
        agent: OpencodeAgent实例
        git_url: git仓库地址
        completed_file: 已完成任务记录文件路径
        completed_lock: 文件写入锁
        stats: 统计信息字典
        max_retries: 最大重试次数
        
    Returns:
        处理结果字典
    """
    thread_id = threading.current_thread().ident
    start_time = time.time()
    result = {
        "git_url": git_url,
        "status": "unknown",
        "error": None,
        "duration": 0,
        "thread_id": thread_id
    }
    
    try:
        with stats["lock"]:
            stats["in_progress"] += 1
            current = stats["completed"] + stats["failed"] + stats["in_progress"]
            total = stats["total"]
            print(f"[线程-{thread_id}] [{current}/{total}] 开始处理: {git_url}")
        
        for attempt in range(1, max_retries + 1):
            try:
                audit_result = agent.audit_git_repo(git_url)
                result["status"] = "success"
                result["session_id"] = audit_result.get("session_id")
                
                with completed_lock:
                    with open(completed_file, "a", encoding="utf-8") as f:
                        f.write(f"{git_url}\n")
                        f.flush()
                
                with stats["lock"]:
                    stats["completed"] += 1
                    stats["in_progress"] -= 1
                    current = stats["completed"] + stats["failed"]
                    total = stats["total"]
                    print(f"[线程-{thread_id}] [{current}/{total}] ✓ 完成: {git_url} (会话ID: {audit_result.get('session_id', 'N/A')})")
                
                break
            except Exception as e:
                if attempt < max_retries:
                    wait_time = attempt * 2
                    print(f"[线程-{thread_id}] ⚠ 第{attempt}次尝试失败，{wait_time}秒后重试: {git_url} - {e}")
                    time.sleep(wait_time)
                else:
                    raise
        
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        
        with stats["lock"]:
            stats["failed"] += 1
            stats["in_progress"] -= 1
            current = stats["completed"] + stats["failed"]
            total = stats["total"]
            print(f"[线程-{thread_id}] [{current}/{total}] ✗ 失败: {git_url} - {e}")
    
    finally:
        end_time = time.time()
        result["duration"] = end_time - start_time
        
        with stats["lock"]:
            stats["total_duration"] += result["duration"]
            if result["status"] == "success":
                stats["success_durations"].append(result["duration"])
            elif result["status"] == "failed":
                stats["failed_durations"].append(result["duration"])
    
    return result


def main():
    """主函数，从gits.txt加载目标并多线程处理"""
    max_workers = int(os.environ.get("MAX_WORKERS", "3"))
    
    agent = OpencodeAgent()
    
    gits_file = os.path.join(os.path.dirname(__file__), "gits.txt")
    completed_file = os.path.join(os.path.dirname(__file__), "gits_completed.txt")
    
    if not os.path.exists(gits_file):
        print(f"错误: 找不到文件 {gits_file}")
        return
    
    completed_gits = set()
    if os.path.exists(completed_file):
        with open(completed_file, "r", encoding="utf-8") as f:
            completed_gits = {line.strip() for line in f if line.strip()}
    
    with open(gits_file, "r", encoding="utf-8") as f:
        all_gits = [line.strip() for line in f if line.strip()]
    
    pending_gits = [git for git in all_gits if git not in completed_gits]
    
    if not pending_gits:
        print("所有目标已完成处理")
        return
    
    total = len(pending_gits)
    print(f"\n{'='*80}")
    print(f"配置信息:")
    print(f"  - 待处理目标数量: {total}")
    print(f"  - 已完成目标数量: {len(completed_gits)}")
    print(f"  - 线程池大小: {max_workers}")
    print(f"{'='*80}\n")
    
    stats = {
        "total": total,
        "completed": 0,
        "failed": 0,
        "in_progress": 0,
        "total_duration": 0.0,
        "success_durations": [],
        "failed_durations": [],
        "lock": threading.Lock()
    }
    
    completed_lock = threading.Lock()
    overall_start_time = time.time()
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_git = {
            executor.submit(process_single_git, agent, git_url, completed_file, completed_lock, stats): git_url
            for git_url in pending_gits
        }
        
        for future in as_completed(future_to_git):
            git_url = future_to_git[future]
            try:
                result = future.result(timeout=None)
                results.append(result)
            except Exception as e:
                print(f"✗ 获取结果异常: {git_url} - {e}")
                with stats["lock"]:
                    stats["failed"] += 1
                    if stats["in_progress"] > 0:
                        stats["in_progress"] -= 1
                results.append({
                    "git_url": git_url,
                    "status": "failed",
                    "error": f"Future异常: {str(e)}",
                    "duration": 0,
                    "thread_id": None
                })
    
    overall_end_time = time.time()
    overall_duration = overall_end_time - overall_start_time
    
    print(f"\n{'='*80}")
    print(f"处理完成统计:")
    print(f"  - 总任务数: {stats['total']}")
    print(f"  - 成功: {stats['completed']}")
    print(f"  - 失败: {stats['failed']}")
    print(f"  - 总耗时: {overall_duration:.2f}秒 ({overall_duration/60:.2f}分钟)")
    
    if stats["success_durations"]:
        avg_success = sum(stats["success_durations"]) / len(stats["success_durations"])
        print(f"  - 成功任务平均耗时: {avg_success:.2f}秒")
        print(f"  - 成功任务最短耗时: {min(stats['success_durations']):.2f}秒")
        print(f"  - 成功任务最长耗时: {max(stats['success_durations']):.2f}秒")
    
    if stats["failed_durations"]:
        avg_failed = sum(stats["failed_durations"]) / len(stats["failed_durations"])
        print(f"  - 失败任务平均耗时: {avg_failed:.2f}秒")
    
    if stats["completed"] > 0:
        throughput = stats["completed"] / overall_duration
        print(f"  - 处理速度: {throughput:.2f} 任务/秒")
    
    print(f"{'='*80}\n")
    
    failed_results = [r for r in results if r["status"] == "failed"]
    if failed_results:
        print(f"失败任务详情 ({len(failed_results)}个):")
        for r in failed_results:
            print(f"  - {r['git_url']}: {r['error']}")
        print()

if __name__ == "__main__":
    main()
