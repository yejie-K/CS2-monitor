from playwright.sync_api import sync_playwright

def manual_login_recorder():
    with sync_playwright() as p:
        # 1. 启动浏览器 (必须是 headless=False，否则你看不见)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 2. 打开 BUFF 登录页
        print("正在打开 BUFF 登录页...")
        page.goto("https://buff.163.com/account/login")

        # 3. 【关键步骤】脚本在这里完全暂停，等待你操作
        print("\n" + "="*50)
        print("请现在去浏览器窗口中，手动扫码或输入验证码登录。")
        print("等你登录成功，看到 BUFF 首页/个人中心后...")
        print("👉 请回到这里，按【回车键 (Enter)】继续...")
        print("="*50 + "\n")
        
        # 这里的 input 就是在等你，你不按回车，脚本永远不动
        input(">>> 等你登录完后，点这里按回车：")

        # 4. 你按回车后，脚本保存当前的 Cookie
        context.storage_state(path="buff_auth.json")
        print("\n✅ 登录状态已保存至 buff_auth.json！")
        print("你可以关闭这个窗口，去运行抓取脚本了。")
        
        browser.close()

if __name__ == "__main__":
    manual_login_recorder()