import os
# 设置 Playwright 环境变量，避免某些系统下报错
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

import pandas as pd
import time
import json
import glob
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr  # <---【关键新增】引入标准地址格式化工具
from datetime import datetime
import traceback

# 导入你的爬虫模块
import buff_scraper
import youpin_scraper

# ================= 文件路径配置 =================
TASK_FILE = "task.xlsx"
HISTORY_FILE = "price_history.json"
CONFIG_FILE = "config.txt"
# ===============================================

def load_email_config():
    """读取 config.txt 中的邮箱配置"""
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    key, val = line.strip().split("=", 1)
                    config[key.strip()] = val.strip()
    return config

def get_item_categories():
    """读取 task.xlsx 分组: A类(产出) vs B类(材料)"""
    try:
        df = pd.read_excel(TASK_FILE, header=None)
        # A类: 第一行 (自动加磨损后缀)
        row1 = df.iloc[0, 1:].dropna().astype(str).tolist()
        group_a = [f"{t.strip()} (久经沙场)" for t in row1 if t.strip()]
        # B类: 3-6行 (保持原样)
        col2 = df.iloc[2:6, 1].dropna().astype(str).tolist()
        group_b = [t.strip() for t in col2 if t.strip()]
        return group_a, group_b
    except Exception as e:
        print(f"❌ 读取任务文件失败: {e}")
        return [], []

def get_latest_file(prefix):
    """获取最新的数据文件"""
    files = glob.glob(f"{prefix}*.xlsx")
    if not files: return None
    return max(files, key=os.path.getctime)

def load_history():
    """加载历史价格"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_history(data):
    """保存当前价格"""
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def format_trend(current, last):
    """生成带涨跌幅的价格显示 (HTML格式)"""
    if last is None: return f"{current} (新)"
    if last == 0: return str(current)
    if current == 0: return "无货"
    
    diff = current - last
    pct = (diff / last) * 100
    
    # 涨价红色，降价绿色
    if diff > 0:
        return f"{current} <span style='color:red; font-size:0.9em;'>(+{pct:.1f}%)</span>"
    elif diff < 0:
        return f"{current} <span style='color:green; font-size:0.9em;'>({pct:.1f}%)</span>"
    else:
        return str(current)

def send_qq_email(df, config):
    """发送 QQ 邮件 (标准修复版)"""
    sender = config.get("SENDER_EMAIL")
    password = config.get("SENDER_PASS")
    receiver = config.get("RECEIVER_EMAIL")

    if not sender or not password or not receiver:
        print("⚠️ 邮箱配置不完整，跳过发送")
        return

    print("📧 正在发送 QQ 邮件...")
    
    # 生成 HTML 表格
    html_table = df.to_html(escape=False, index=False, border=1, justify="center")
    
    msg = MIMEMultipart()
    
    # ===【核心修复】使用 formataddr 生成完全符合 RFC 标准的头部 ===
    # 这解决了 "The 'From' header is missing or invalid" 问题
    msg['From'] = formataddr((Header("CS2监控", 'utf-8').encode(), sender))
    msg['To'] = formataddr((Header("Admin", 'utf-8').encode(), receiver))
    # ========================================================
    
    msg['Subject'] = Header(f"行情监控 {datetime.now().strftime('%H:%M')}", 'utf-8')

    body = f"""
    <h3>CS2 炼金策略监控报告</h3>
    <p><b>策略公式：</b> (A类价格 - B类最低价 × 5) / A类价格 > 15%</p>
    <p><b>数据说明：</b> 价格取 Buff 与 悠悠有品 中的最低值。</p>
    <hr>
    {html_table}
    <p style='font-size:12px; color:gray'>更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    """
    msg.attach(MIMEText(body, 'html', 'utf-8'))

    try:
        # QQ邮箱 SMTP 服务器
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(sender, password)
        server.sendmail(sender, [receiver], msg.as_string())
        server.quit()
        print("✅ 邮件发送成功！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

def job():
    print(f"\n⏰ === 新一轮任务: {datetime.now().strftime('%H:%M:%S')} ===")
    
    # 1. 运行爬虫模块
    try:
        print("🤖 运行 BUFF 抓取...")
        buff_scraper.main_task()
        print("🤖 运行 YouPin 抓取...")
        youpin_scraper.main_task()
    except Exception as e:
        print(f"❌ 爬虫运行出错: {e}")
        traceback.print_exc()
        return

    # 2. 获取最新文件
    f_buff = get_latest_file("BUFF_数据")
    f_uu = get_latest_file("手套及其下级-uu")  # 注意：youpin_scraper.py 里生成的那个名字
    
    # 如果没找到，尝试模糊匹配（兼容不同的命名）
    if not f_uu: 
        f_uu = get_latest_file("UU_数据")
    
    if not f_buff or not f_uu:
        print(f"❌ 未找到数据文件 (Buff: {f_buff}, UU: {f_uu})")
        return

    # 3. 计算逻辑
    print("🧮 正在计算策略与趋势...")
    try:
        df_buff = pd.read_excel(f_buff, index_col=0)
        df_uu = pd.read_excel(f_uu, index_col=0)

        # 确保有"最低"行
        if "最低" not in df_buff.index or "最低" not in df_uu.index:
            print("⚠️ 数据缺失'最低'行")
            return

        prices_buff = df_buff.loc["最低"]
        prices_uu = df_uu.loc["最低"]

        # 合并取最低价
        all_items = set(prices_buff.index).union(set(prices_uu.index))
        combined_prices = {}
        current_history = {} 

        for item in all_items:
            # 防止数据里有非数字
            try:
                p1 = float(prices_buff.get(item, 999999))
            except: p1 = 999999
            
            try:
                p2 = float(prices_uu.get(item, 999999))
            except: p2 = 999999
            
            real_min = min(p1, p2)
            if real_min == 999999: real_min = 0
            
            combined_prices[item] = real_min
            current_history[item] = real_min

        # 加载历史数据
        history = load_history()
        
        # 获取 A/B 分组
        group_a, group_b = get_item_categories()

        # 找出 B类（材料）中最便宜的一个作为基准
        b_prices = [combined_prices.get(b, 0) for b in group_b]
        valid_b = [p for p in b_prices if p > 0]
        min_b_cost = min(valid_b) if valid_b else 0

        report_data = []

        # --- A类 (产出) ---
        for a_item in group_a:
            curr_p = combined_prices.get(a_item, 0)
            trend_str = format_trend(curr_p, history.get(a_item))
            
            # 策略计算
            status = "普通"
            if curr_p > 0 and min_b_cost > 0:
                cost = min_b_cost * 5
                profit_rate = (curr_p - cost) / curr_p
                
                # 期望判定 > 15%
                if profit_rate > 0.15:
                    status = f"<b style='color:red'>🔥正期望 ({profit_rate:.1%})</b>"
                else:
                    status = f"利润率 {profit_rate:.1%}"
            
            report_data.append({
                "类型": "产出 (A)",
                "饰品名称": a_item.replace(" (久经沙场)", ""), # 简化名称显示
                "最低价(环比)": trend_str,
                "状态": status
            })

        # --- B类 (材料) ---
        for b_item in group_b:
            curr_p = combined_prices.get(b_item, 0)
            trend_str = format_trend(curr_p, history.get(b_item))
            
            is_best = (curr_p == min_b_cost and curr_p > 0)
            
            report_data.append({
                "类型": "材料 (B)",
                "饰品名称": b_item,
                "最低价(环比)": trend_str,
                "状态": "<b style='color:blue'>最佳材料</b>" if is_best else "-"
            })

        # 保存本次历史
        save_history(current_history)

        # 4. 发送邮件
        df_result = pd.DataFrame(report_data)
        email_config = load_email_config()
        send_qq_email(df_result, email_config)

    except Exception as e:
        print(f"❌ 计算流程出错: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    try:
        # 检查配置
        if not os.path.exists(CONFIG_FILE):
            print(f"⚠️ 请先配置 {CONFIG_FILE} 文件！")
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write("SENDER_EMAIL=\nSENDER_PASS=\nRECEIVER_EMAIL=")
        
        # 检查任务文件
        if not os.path.exists(TASK_FILE):
             print(f"❌ 严重错误：找不到 {TASK_FILE} 文件！请确保该文件在 exe 同级目录下。")
             # 如果没有，尝试从CSV生成一个避免立刻报错，但最好还是让用户检查
             # raise FileNotFoundError("任务文件丢失")

        print("🚀 监控程序已启动 (按 Ctrl+C 退出)...")
        
        # 立即运行一次
        job()
        
        # 定时循环
        while True:
            print("\n💤 挂机中... 1 小时后自动运行")
            time.sleep(3600)
            job()
            
    except Exception as e:
        print("\n" + "!"*50)
        print("❌ 程序发生严重错误，已停止运行：")
        print(e)
        print("\n详细报错信息：")
        traceback.print_exc()
        print("!"*50 + "\n")
        input(">>> 按回车键 (Enter) 退出程序...")