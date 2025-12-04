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
        
        # 1. 获取第一行（忽略第一列）
        row1_targets = df.iloc[0, 1:].dropna().astype(str).tolist()
        targets.extend([t.strip() for t in row1_targets if t.strip()])
        
        # 2. 获取第3-6行的第二列
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
        # 启动参数优化
        #browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        # 修改点：加上 channel="msedge"，让它使用电脑自带的 Edge 浏览器
        browser = p.chromium.launch(channel="msedge", headless=False, args=["--disable-blink-features=AutomationControlled"])
        
        # 如果没有 buff_auth.json，这里会报错，请确保已登录并保存了状态
        # 如果第一次运行没状态，可以先把 storage_state 去掉手动登录一次
        try:
            context = browser.new_context(storage_state="buff_auth.json")
        except:
            print("⚠️ 未找到登录信息 buff_auth.json，将以未登录模式运行（可能无法查看价格）")
            context = browser.new_context()

        page = context.new_page()
        # 拦截图片，加快速度
        page.route("**/*.{png,jpg,jpeg,gif,webp}", lambda route: route.abort())

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
            
            # 1. 获取 ID (如果本地没有，则通过搜索栏交互获取)
            goods_id = db.get(skin_name)
            if not goods_id:
                print(f"   ⚠️ 本地无ID，正在执行：输入 -> 下箭头 -> 回车...")
                
                # 每次需要搜索 ID 时，强制回到市场首页，确保从“原来界面”开始
                # 这样可以保证搜索环境一致，且 wait_for_url 逻辑更准确
                page.goto("https://buff.163.com/market/csgo#tab=selling")
                
                try:
                    # 定位搜索框 (Buff 通用搜索框通常 name='search')
                    search_input = page.locator("input[name='search']").first
                    
                    # 确保搜索框可见
                    search_input.wait_for(state="visible", timeout=5000)
                    
                    # 清空并输入
                    search_input.click()
                    search_input.clear()
                    search_input.fill(skin_name)
                    
                    # === 关键逻辑修改开始 ===
                    # 1. 等待一下，让 Buff 后端返回联想词 (模拟人类反应)
                    time.sleep(1.5) 
                    
                    # 2. 按下方向键下 (选中第一个联想词)
                    page.keyboard.press("ArrowDown")
                    time.sleep(0.5) 
                    
                    # 3. 按下回车 (进入商品页)
                    page.keyboard.press("Enter")
                    # === 关键逻辑修改结束 ===

                    # 等待URL变化包含 goods id
                    # Buff 商品页 URL 格式通常是 .../goods/12345...
                    page.wait_for_url(re.compile(r".*/goods/\d+"), timeout=8000)
                    
                    match = re.search(r"goods/(\d+)", page.url)
                    if match:
                        goods_id = match.group(1)
                        db[skin_name] = goods_id
                        save_db(db)
                        print(f"   ✅ 捕获成功 ID: {goods_id}")
                    else:
                        print("   ❌ 跳转后未发现ID特征，跳过")
                        final_stats[skin_name] = None
                        continue
                except Exception as e:
                    print(f"   ❌ 搜索交互超时或失败: {e}")
                    final_stats[skin_name] = None
                    continue

            # 2. 抓取数据 (已知 ID 后直接拼接 URL，效率更高)
            current_prices = [] 
            base_url = f"https://buff.163.com/goods/{goods_id}"
            
            page_nums = [1, 2] 
            
            for p_num in page_nums:
                target_url = f"{base_url}?from=market#tab=selling&page_num={p_num}"
                page.goto(target_url)
                try:
                    with page.expect_response(lambda r: "goods/sell_order" in r.url and r.status == 200, timeout=5000):
                        if p_num == 1: page.reload()
                        else: pass 
                except:
                    pass
                time.sleep(0.5 + (0.2 * p_num))

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

            time.sleep(1)

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