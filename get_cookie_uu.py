from playwright.sync_api import sync_playwright
import traceback

def manual_login_youpin():
    with sync_playwright() as p:
        print("🚀 正在启动浏览器 (Edge)...")
        # 【关键修改】加上 channel="msedge"
        browser = p.chromium.launch(channel="msedge", headless=False)
        
        context = browser.new_context()
        page = context.new_page()

        print("正在打开悠悠有品登录页...")
        page.goto("https://www.youpin898.com/")
        
        print("\n" + "="*50)
        print("请在弹出的浏览器中点击右上角【登录】，并完成扫码/验证。")
        print("登录成功后，确保你能看到个人头像。")
        print("👉 确认登录完成后，请回到这里按【回车键 (Enter)】...")
        print("="*50 + "\n")
        
        input(">>> 登录完成后，点这里按回车：")

        context.storage_state(path="uu_auth.json")
        print("\n✅ 登录状态已保存至 uu_auth.json！")
        browser.close()

if __name__ == "__main__":
    try:
        manual_login_youpin()
    except Exception as e:
        print("\n" + "!"*50)
        print("❌ 发生错误，程序已停止：")
        print(e)
        print("\n详细报错信息：")
        traceback.print_exc()
        print("!"*50 + "\n")
        input(">>> 按回车键 (Enter) 退出...")