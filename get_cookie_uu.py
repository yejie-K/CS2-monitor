from playwright.sync_api import sync_playwright

def manual_login_youpin():
    with sync_playwright() as p:
        # 启动有头浏览器
        #browser = p.chromium.launch(headless=False)
        browser = p.chromium.launch(channel="msedge", headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("正在打开悠悠有品登录页...")
        # 悠悠有品没有单独的登录页，通常在首页点击登录
        page.goto("https://www.youpin898.com/")
        
        print("\n" + "="*50)
        print("请在弹出的浏览器中点击右上角【登录】，并完成扫码/验证。")
        print("登录成功后，确保你能看到个人头像。")
        print("👉 确认登录完成后，请回到这里按【回车键 (Enter)】...")
        print("="*50 + "\n")
        
        input(">>> 登录完成后，点这里按回车：")

        # 保存 Cookie
        context.storage_state(path="uu_auth.json")
        print("\n✅ 登录状态已保存至 uu_auth.json！")
        browser.close()

if __name__ == "__main__":
    manual_login_youpin()