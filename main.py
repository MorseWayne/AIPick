import os
import asyncio
try:
    import readline # 用于在Unix系终端修复回车/退格键的输入问题
except ImportError:
    pass

from dotenv import load_dotenv

from src.agent import RecommendationAgent

async def main():
    # 尝试加载环境变量（如果没有，需要配置 .env 或者系统的环境变量）
    load_dotenv()
    
    if not os.getenv("OPENAI_API_KEY"):
        print("====== 系统配置未完成 ======")
        print("请在项目根目录创建 .env 文件，并填入您的 OPENAI_API_KEY。\n")
        print("例如：")
        print("OPENAI_API_KEY=sk-xxxx")
        print("OPENAI_BASE_URL=https://api.openai.com/v1")
        print("==============================")
        return

    agent = RecommendationAgent(mcp_url="http://10.10.131.118:18060/mcp")
    
    print("\n欢迎使用【AIPick】")
    print("您可以输入您的自然语言需求，例如：我想买一台5000左右的轻薄本写代码")
    
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
            print(f"\n[错误中断] 运行时报错: {e}")
            print("如果报错与反序列化相关，说明 MCP 服务的返回结构与默认的解析方式不符，请查看 src/agent.py 进行修整。")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError, EOFError):
        pass
