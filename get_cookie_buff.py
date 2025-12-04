from playwright.sync_api import sync_playwright
import traceback

def manual_login_recorder():
    with sync_playwright() as p:
        print("🚀 正在启动浏览器 (Edge)...")
        # 【关键修改】加上 channel="msedge" 使用系统自带浏览器
        browser = p.chromium.launch(channel="msedge", headless=False)
        
        context = browser.new_context()
        page = context.new_page()

        print("正在打开 BUFF 登录页...")
        page.goto("https://buff.163.com/account/login")

        print("\n" + "="*50)
        print("请现在去浏览器窗口中，手动扫码或输入验证码登录。")
        print("等你登录成功，看到 BUFF 首页/个人中心后...")
        print("👉 请回到这里，按【回车键 (Enter)】继续...")
        print("="*50 + "\n")
        
        input(">>> 等你登录完后，点这里按回车：")

        context.storage_state(path="buff_auth.json")
        print("\n✅ 登录状态已保存至 buff_auth.json！")
        print("你可以关闭这个窗口了。")
        
        browser.close()

if __name__ == "__main__":
    try:
        manual_login_recorder()
    except Exception as e:
        print("\n" + "!"*50)
        print("❌ 发生错误，程序已停止：")
        print(e)
        print("\n详细报错信息：")
        traceback.print_exc()
        print("!"*50 + "\n")
        # 【关键修改】报错后暂停，防止闪退
        input(">>> 按回车键 (Enter) 退出...")