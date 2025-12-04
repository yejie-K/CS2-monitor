import pandas as pd
from playwright.sync_api import sync_playwright
import re
import json
import os
import time
from datetime import datetime
from urllib.parse import quote

# ================= 配置区 =================
INPUT_FILE = "task.xlsx"  # 你的任务文件
DB_FILE = "gun_keys.json" # ID缓存文件
# =========================================

def load_db():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except: pass

def get_target_skins():
    """解析 task.xlsx 获取目标饰品列表"""
    targets = []
    try:
        # 读取 Excel，不带表头，方便按行索引
        df = pd.read_excel(INPUT_FILE, header=None)
        
        # 1. 获取第一行（产出物）：强制追加 (久经沙场)
        row1_targets = df.iloc[0, 1:].dropna().astype(str).tolist()
        for t in row1_targets:
            name = t.strip()
            if name:
                # 【关键修改】如果没有写磨损，自动加上 (久经沙场)
                if "(久经沙场)" not in name:
                    name = f"{name} (久经沙场)"
                targets.append(name)
        
        # 2. 获取第3-6行的第二列（材料）：保持原样
        # (通常材料在Excel里已经写全了磨损，如果没有，你也可以在这里照样加)
        col2_targets = df.iloc[2:6, 1].dropna().astype(str).tolist()
        targets.extend([t.strip() for t in col2_targets if t.strip()])
        
        print(f"📋 已加载 {len(targets)} 个目标: {targets}")
        return targets
    except Exception as e:
        print(f"❌ 读取 {INPUT_FILE} 失败: {e}")
        return []

def run_scraper():
    target_skins = get_target_skins()
    if not target_skins: return

    file_timestamp = datetime.now().strftime('%m%d(%H)')
    db = load_db()
    
    # 用于存储最终统计结果的字典
    final_stats = {}

    with sync_playwright() as p:
        print("🚀 启动浏览器...")
        # 启动参数优化：使用 Edge，禁用自动化特征
        browser = p.chromium.launch(channel="msedge", headless=False, args=["--disable-blink-features=AutomationControlled"])
        
        try:
            context = browser.new_context(storage_state="buff_auth.json")
        except:
            print("⚠️ 未找到登录信息 buff_auth.json，将以未登录模式运行")
            context = browser.new_context()

        page = context.new_page()
        
        # === 优化点 1: 扩大资源屏蔽范围 (字体、媒体也屏蔽，提速明显) ===
        page.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff,woff2,ttf}", lambda route: route.abort())

        # 当前正在处理的临时价格列表
        current_prices = []

        # --- 数据拦截器 ---
        def handle_response(response):
            if "goods/sell_order" in response.url and response.status == 200:
                try:
                    data = response.json()
                    items = data.get('data', {}).get('items', [])
                    print(f"   ---> 📦 捕获数据: {len(items)} 条")
                    for item in items:
                        price = item.get('price')
                        if price:
                            current_prices.append(float(price))
                except: pass

        page.on("response", handle_response)

        # ================= 循环处理每个饰品 =================
        for idx, skin_name in enumerate(target_skins):
            print(f"\n[{idx+1}/{len(target_skins)}] 正在处理: {skin_name}")
            
            # 1. 获取 ID
            goods_id = db.get(skin_name)
            if not goods_id:
                print(f"   ⚠️ 本地无ID，执行搜索...")
                page.goto("https://buff.163.com/market/csgo#tab=selling")
                
                try:
                    search_input = page.locator("input[name='search']").first
                    search_input.wait_for(state="visible", timeout=5000)
                    
                    search_input.click()
                    search_input.clear()
                    search_input.fill(skin_name)
                    
                    time.sleep(1.0) # 稍微减少等待时间
                    page.keyboard.press("ArrowDown")
                    time.sleep(0.2)
                    page.keyboard.press("Enter")

                    page.wait_for_url(re.compile(r".*/goods/\d+"), timeout=8000)
                    
                    match = re.search(r"goods/(\d+)", page.url)
                    if match:
                        goods_id = match.group(1)
                        db[skin_name] = goods_id
                        save_db(db)
                        print(f"   ✅ 捕获成功 ID: {goods_id}")
                    else:
                        print("   ❌ 未发现ID，跳过")
                        final_stats[skin_name] = None
                        continue
                except Exception as e:
                    print(f"   ❌ 搜索失败: {e}")
                    final_stats[skin_name] = None
                    continue

            # 2. 抓取数据 (性能优化核心部分)
            current_prices = [] 
            base_url = f"https://buff.163.com/goods/{goods_id}"
            
            page_nums = [1, 2] 
            
            for p_num in page_nums:
                target_url = f"{base_url}?from=market#tab=selling&page_num={p_num}"
                
                try:
                    # === 优化点 2: 移除 reload，直接在 goto 时捕获请求 ===
                    with page.expect_response(lambda r: "goods/sell_order" in r.url and r.status == 200, timeout=6000):
                        page.goto(target_url)
                except:
                    pass
                
                # === 优化点 3: 智能跳过 ===
                if p_num == 1 and len(current_prices) == 0:
                    print("   ⚠️ 第一页无数据，跳过后续页")
                    break

                time.sleep(0.5)

            # 3. 计算统计指标
            if current_prices:
                stats = {
                    "最高": max(current_prices),
                    "最低": min(current_prices),
                    "均值": round(sum(current_prices) / len(current_prices), 2),
                    "中位数": sorted(current_prices)[len(current_prices) // 2]
                }
                print(f"   ✅ 统计完成: 最低 {stats['最低']}")
                final_stats[skin_name] = stats
            else:
                print("   ⚠️ 无在售数据")
                final_stats[skin_name] = {"最高": 0, "最低": 0, "均值": 0, "中位数": 0}

            time.sleep(0.5)

        browser.close()

    # ================= Excel 生成逻辑 =================
    output_filename = f"BUFF_数据_{file_timestamp}.xlsx"
    print(f"\n📊 正在生成: {output_filename}")

    try:
        data_for_df = {}
        indicators = ["最高", "最低", "均值", "中位数"]
        
        for skin in target_skins:
            stats = final_stats.get(skin)
            if stats:
                data_for_df[skin] = [stats[k] for k in indicators]
            else:
                data_for_df[skin] = ["-", "-", "-", "-"]

        df = pd.DataFrame(data_for_df, index=indicators)

        with pd.ExcelWriter(output_filename, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name="统计数据")
            
            workbook = writer.book
            worksheet = writer.sheets["统计数据"]
            yellow_fmt = workbook.add_format({'bg_color': '#FFFF00', 'bold': True})
            
            target_row_idx = 2 
            
            for col_idx, col_name in enumerate(df.columns):
                val = df.loc["最低", col_name]
                worksheet.write(target_row_idx, col_idx + 1, val, yellow_fmt)
            
            worksheet.write(target_row_idx, 0, "最低", yellow_fmt)

        print("✅ Excel 生成完毕!")

    except Exception as e:
        print(f"❌ Excel 生成失败: {e}")
        import traceback
        traceback.print_exc()

# 封装供主程序调用
def main_task():
    run_scraper()

if __name__ == "__main__":
    main_task()