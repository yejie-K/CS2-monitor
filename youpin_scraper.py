import pandas as pd
from playwright.sync_api import sync_playwright
import os
import time
import re
from datetime import datetime

# ================= 配置区 =================
INPUT_FILE = "task.xlsx"       
COOKIE_FILE = "uu_auth.json"
# =========================================

def get_target_skins():
    """
    解析 task.xlsx
    返回列表结构: [{"name": "饰品名", "use_arrow": True/False}, ...]
    """
    targets = []
    try:
        df = pd.read_excel(INPUT_FILE, header=None)
        
        # 1. 第一行目标：追加 "(久经沙场)"，并且需要下箭头选择
        row1_raw = df.iloc[0, 1:].dropna().astype(str).tolist()
        for t in row1_raw:
            clean_name = t.strip()
            if clean_name:
                targets.append({
                    "name": f"{clean_name} (久经沙场)",
                    "use_arrow": True  # 需要按箭头
                })
        
        # 2. 后四个目标（第二列）：保持原样，不需要下箭头
        col2_raw = df.iloc[2:6, 1].dropna().astype(str).tolist()
        for t in col2_raw:
            clean_name = t.strip()
            if clean_name:
                targets.append({
                    "name": clean_name,
                    "use_arrow": False # 不需要按箭头
                })
        
        print(f"📋 [任务加载] 共 {len(targets)} 个目标")
        return targets
    except Exception as e:
        print(f"❌ 读取 Excel 失败: {e}")
        return []

def run_scraper():
    target_items = get_target_skins() # 获取带有配置的目标列表
    if not target_items: return

    file_timestamp = datetime.now().strftime('%m%d(%H)')
    final_stats_map = {} 

    with sync_playwright() as p:
        print("🚀 [启动] V18 修复版：针对后四项移除多余下箭头操作")
        
        #browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        # 修改点：加上 channel="msedge"，让它使用电脑自带的 Edge 浏览器
        browser = p.chromium.launch(channel="msedge", headless=False, args=["--disable-blink-features=AutomationControlled"])
        if os.path.exists(COOKIE_FILE):
            context = browser.new_context(storage_state=COOKIE_FILE)
        else:
            context = browser.new_context()
            
        page = context.new_page()
        page.set_viewport_size({"width": 1920, "height": 1080})

        # ⚡️ 拦截图片/字体，提升速度
        page.route("**/*", lambda route: route.abort() 
                   if route.request.resource_type in ["image", "media", "font"] 
                   else route.continue_())

        # ============================================================
        # 👇 抓取函数
        # ============================================================
        def scrape_sale_prices():
            print("   📥 提取数据中...")
            # 无需滚动，直接等待表格
            try:
                page.wait_for_selector("tr.ant-table-row", timeout=3000)
            except: pass

            rows = page.locator("tr.ant-table-row").all()
            prices = []
            seen_hashes = set()

            for row in rows:
                try:
                    if not row.is_visible(): continue
                    full_text = row.inner_text().replace("\n", " ")
                    
                    h = hash(full_text)
                    if h in seen_hashes: continue
                    seen_hashes.add(h)

                    if "¥" not in full_text and "￥" not in full_text: continue
                    p = re.search(r'[¥￥]\s*([\d\.]+)', full_text)
                    if p:
                        prices.append(float(p.group(1)))
                except: continue
            return prices

        # ============================================================
        # 🔄 主循环
        # ============================================================
        for idx, item_data in enumerate(target_items):
            skin_name = item_data["name"]
            use_arrow = item_data["use_arrow"]
            
            print(f"\n[{idx+1}/{len(target_items)}] 正在处理: {skin_name}")
            
            try:
                page.goto("https://www.youpin898.com/market")
                
                # 交互逻辑
                try:
                    sb = page.wait_for_selector("input.ant-input, input[class*='search']", state="visible", timeout=10000)
                    sb.click()
                    sb.fill(skin_name) 
                    
                    page.wait_for_timeout(500) 
                    
                    # 关键修复：根据 use_arrow 决定是否按方向键
                    if use_arrow:
                        sb.press("ArrowDown") # 选中第一个联想词
                        page.wait_for_timeout(200)
                    
                    sb.press("Enter")     # 跳转
                    
                    try:
                        page.wait_for_selector("tr.ant-table-row", timeout=5000)
                    except:
                        print("   ⚠️ 表格未加载")
                        final_stats_map[skin_name] = None
                        continue

                except Exception as e:
                    print(f"   ❌ 交互失败: {e}")
                    final_stats_map[skin_name] = None
                    continue

                # 抓取
                prices = scrape_sale_prices()
                
                # 统计
                if prices:
                    stats = {
                        "最高": max(prices),
                        "最低": min(prices),
                        "均值": round(sum(prices) / len(prices), 2),
                        "中位数": sorted(prices)[len(prices) // 2]
                    }
                    print(f"   ✅ 最低: {stats['最低']} | 均值: {stats['均值']}")
                    final_stats_map[skin_name] = stats
                else:
                    print("   ⚠️ 无数据")
                    final_stats_map[skin_name] = None
            
            except Exception as e:
                print(f"   ❌ 异常: {e}")
                final_stats_map[skin_name] = None

        browser.close()

    # ==========================================
    # 💾 Excel 生成 (已修复重复行问题)
    # ==========================================
    output_filename = f"手套及其下级-uu {file_timestamp}.xlsx"
    print(f"\n📊 生成 Excel: {output_filename}")

    try:
        indicators = ["最高", "最低", "均值", "中位数"]
        data_dict = {}
        # 这里的循环也要改，从字典里取 name
        for item in target_items:
            skin = item["name"]
            stats = final_stats_map.get(skin)
            if stats:
                data_dict[skin] = [stats[k] for k in indicators]
            else:
                data_dict[skin] = ["-", "-", "-", "-"]

        df = pd.DataFrame(data_dict, index=indicators)

        with pd.ExcelWriter(output_filename, engine='xlsxwriter') as writer:
            # 1. 写入原始数据
            df.to_excel(writer, sheet_name="统计数据")
            
            workbook = writer.book
            worksheet = writer.sheets["统计数据"]
            yellow_fmt = workbook.add_format({'bg_color': '#FFFF00', 'bold': True})
            
            # 2. 计算正确的行号
            target_excel_row = 2 
            
            # 3. 遍历该行进行标黄
            for col_idx in range(df.shape[1] + 1):
                if col_idx == 0:
                    worksheet.write(target_excel_row, col_idx, "最低", yellow_fmt)
                else:
                    val = df.iloc[1, col_idx - 1]
                    worksheet.write(target_excel_row, col_idx, val, yellow_fmt)

        print("🎉 全部完成！")

    except Exception as e:
        print(f"❌ Excel 失败: {e}")

# 封装供主程序调用
def main_task():
    run_scraper()

if __name__ == "__main__":
    main_task()