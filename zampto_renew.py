import os
import time
import requests
from seleniumbase import SB

# ================= 配置区域 =================
LOGIN_URL = "https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl"
DASHBOARD_URL = "https://dash.zampto.net"

RENEW_URLS = [
    "https://dash.zampto.net/server?id=5933"
]

# ================= 环境变量 =================
ZAMPTO_ACCOUNT = os.environ.get('ZAMPTO_ACCOUNT', '')
TG_BOT = os.environ.get('TG_BOT', '')
USE_PROXY = os.environ.get('USE_PROXY') == 'true'
# 从 Secret 获取 Cookie (格式: remember_web_xxx#value_xxx)
PTERODACTYL_COOKIE = os.environ.get('PTERODACTYL_COOKIE', '')

LOCAL_PROXY = "socks5://127.0.0.1:10808" if USE_PROXY else None

def send_telegram_msg(message):
    if not TG_BOT: return
    try:
        token, chat_id = TG_BOT.split('#')
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"TG 通知发送失败: {e}")

def send_telegram_photo(photo_path, caption=""):
    if not TG_BOT: return
    try:
        token, chat_id = TG_BOT.split('#')
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        with open(photo_path, 'rb') as f:
            payload = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
            requests.post(url, data=payload, files={"photo": f}, timeout=20)
    except Exception as e:
        print(f"TG 图片发送失败: {e}")

def handle_cf(sb):
    """专门处理 Cloudflare 验证码的逻辑"""
    cf_selector = 'iframe[title*="Cloudflare"], iframe[src*="challenge"], div#turnstile-wrapper'
    if sb.is_element_visible(cf_selector):
        print(" -> ⚠️ 检测到 Cloudflare 验证码，尝试破解...")
        try:
            sb.uc_gui_handle_captcha() # 使用 SB 增强版处理函数
            time.sleep(10)
        except:
            sb.uc_click(cf_selector)
            time.sleep(5)

def process_account(sb, username, password):
    print(f"\n[+] 开始处理账号: {username}")
    account_report = [f"👤 账号: <b>{username}</b>"]
    
    try:
        sb.maximize_window()
        
        # ---------------- 1. 尝试 Cookie 登录 (跳过 CF) ----------------
        if PTERODACTYL_COOKIE and '#' in PTERODACTYL_COOKIE:
            print(" -> 检测到 Cookie 配置，尝试注入...")
            c_name, c_value = PTERODACTYL_COOKIE.split('#')
            sb.uc_open_with_reconnect(DASHBOARD_URL, 4)
            sb.add_cookie({"name": c_name.strip(), "value": c_value.strip()})
            sb.refresh_page()
            time.sleep(5)
            
        # ---------------- 2. 正常登录逻辑 ----------------
        if "auth.zampto.net" in sb.get_current_url() or "sign-in" in sb.get_current_url():
            print(" -> Cookie 失效或未配置，进入常规登录流程...")
            sb.uc_open_with_reconnect(LOGIN_URL, 4)
            handle_cf(sb)
            
            account_input = 'input[name="identifier"], input[name="email"], input[type="email"]'
            sb.wait_for_element_visible(account_input, timeout=20)
            sb.type(account_input, username)
            sb.click('button[type="submit"]')
            time.sleep(3)
            
            sb.wait_for_element_visible('input[type="password"]', timeout=15)
            sb.type('input[type="password"]', password)
            sb.click('button[type="submit"]')
            print(" -> 已点击登录，等待跳转...")
            time.sleep(15)
            handle_cf(sb) # 登录后可能还有一次 CF

        # ---------------- 3. 检查是否进入控制台 ----------------
        if "dash.zampto.net" not in sb.get_current_url():
            # 如果还在登录页或者授权页，可能需要点击一个“Authorize”按钮
            if sb.is_text_visible("Authorize"):
                sb.click('button:contains("Authorize")')
                time.sleep(10)

        if "dash.zampto.net" not in sb.get_current_url():
            sb.save_screenshot(f"{username}_failed.png")
            return False, f"❌ 账号 {username} 登录失败，被 CF 拦截或凭据错误。"

        print(" ✅ 登录成功！开始续期流程...")

        # ---------------- 4. 续期操作 ----------------
        for url in RENEW_URLS:
            server_id = url.split('=')[-1]
            sb.uc_open_with_reconnect(url, 3)
            time.sleep(8)
            
            # 清理干扰弹窗
            for _ in range(2):
                for btn in ['div:contains("Close")', 'button:contains("Hide")', '.modal-close']:
                    if sb.is_element_visible(btn): sb.js_click(btn)
                time.sleep(2)

            sb.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            renew_btn = 'button:contains("Renew Server")'
            
            if sb.is_element_visible(renew_btn):
                sb.js_click(renew_btn)
                print(f" -> [服务 {server_id}] 已点击续期，等待验证码...")
                time.sleep(10)
                handle_cf(sb)
                time.sleep(20)
                
                shot = f"{username}_{server_id}.png"
                sb.save_screenshot(shot)
                send_telegram_photo(shot, f"✅ {username} - ID {server_id} 续期成功")
                account_report.append(f" ✅ ID {server_id}: 成功")
            else:
                account_report.append(f" ℹ️ ID {server_id}: 未找到按钮")

        return True, "\n".join(account_report)

    except Exception as e:
        sb.save_screenshot(f"{username}_error.png")
        return False, f"❌ 崩溃: {str(e)[:50]}"

def main():
    if not ZAMPTO_ACCOUNT: return
    accounts = [line.strip() for line in ZAMPTO_ACCOUNT.split('\n') if line.strip()]
    
    # 使用增强版启动参数
    with SB(uc=True, proxy=LOCAL_PROXY, headless=True, ad_block=True) as sb:
        for acc in accounts:
            if ':' not in acc: continue
            u, p = acc.split(':', 1)
            _, report = process_account(sb, u, p)
            print(report)

if __name__ == "__main__":
    main()
