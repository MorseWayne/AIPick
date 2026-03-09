import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler
try:
    import readline # 用于在Unix系终端修复回车/退格键的输入问题
except ImportError:
    pass

from dotenv import load_dotenv

from src.agent import RecommendationAgent

def setup_logging():
    """配置全局日志系统，将日志保存到指定文件中，保持控制台整洁"""
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 文件日志记录器
    file_handler = RotatingFileHandler(
        "logs/aipick.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
    )
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # 降低第三方库的日志噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("mcp").setLevel(logging.WARNING)

async def main():
    setup_logging()
    # 尝试加载环境变量
    load_dotenv()
    
    # 解析 mcp_url 并自动将其 Host 注入免代理白名单，防止网络代理劫持内网请求
    from urllib.parse import urlparse
    mcp_url = os.getenv("XHS_MCP_URL", "http://10.10.131.118:18060/mcp")
    parsed_host = urlparse(mcp_url).hostname or ""
    
    no_proxy_list = os.environ.get("NO_PROXY", os.environ.get("no_proxy", ""))
    lan_ips = ["127.0.0.1", "localhost", parsed_host]
    extended_no_proxy = ",".join(filter(bool, [no_proxy_list] + lan_ips))
    os.environ["NO_PROXY"] = extended_no_proxy
    os.environ["no_proxy"] = extended_no_proxy
    
    if not os.getenv("OPENAI_API_KEY"):
        print("====== 系统配置未完成 ======")
        print("请在项目根目录创建 .env 文件，并填入您的 OPENAI_API_KEY。\n")
        print("例如：")
        print("OPENAI_API_KEY=sk-xxxx")
        print("OPENAI_BASE_URL=https://api.openai.com/v1")
        print("==============================")
        return
        
    mcp_url = os.getenv("XHS_MCP_URL", "http://10.10.131.118:18060/mcp")
    agent = RecommendationAgent(mcp_url=mcp_url)
    
    print("\n欢迎使用【AIPick】")
    print("您可以输入您的自然语言需求，例如：我想买适用用中年女性的护肤品，目的是抗衰老，祛斑，体质是油性皮肤，容易长痘，看看买什么合适")
    
    while True:
        try:
            query = input("\n> 请出题 (输入 'q' 退出): ")
        except (KeyboardInterrupt, EOFError):
            print("\n\n再见！")
            break

        if query.strip().lower() in ['q', 'quit', 'exit']:
            print("\n再见！")
            break
        if not query.strip():
            continue
            
        try:
            await agent.run_pipeline(query)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n\n[当前任务已被手动中止，已返回主菜单]")
            continue
        except Exception as e:
            logging.getLogger().exception(f"[Pipeline Error] {e}")
            print(f"\n[错误中断] 运行时报错: {e}")
            if "TaskGroup" in str(e) or "ConnectError" in str(e):
                print(">>> 这通常是因为网络连接失败（如您的代理梯子阻挡了对内网IP的请求，或者被小红书接口拦截了）。相关的详细堆栈请查看 logs/aipick.log")
            print("如果报错与反序列化相关，说明 MCP 服务的返回结构与默认的解析方式不符，请查看 src/agent.py 进行修整。")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError, EOFError):
        pass
