import os
import time
import requests
from seleniumbase import SB

# ================= 配置区域 =================
LOGIN_URL = "https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl"
DASHBOARD_URL = "https://dash.zampto.net"

# 续期服务的列表，请确保 ID 正确
RENEW_URLS = [
    "https://dash.zampto.net/server?id=5933"
]

# ================= 环境变量 =================
ZAMPTO_ACCOUNT = os.environ.get('ZAMPTO_ACCOUNT', '')
TG_BOT = os.environ.get('TG_BOT', '')
USE_PROXY = os.environ.get('USE_PROXY') == 'true'
# 格式: 名#值 (例如: PHPSESSID#61845hoju22fvcgeldnbllmhts)
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

def handle_cf_challenge(sb):
    """主动检测并尝试处理 Cloudflare 验证码"""
    cf_selectors = [
        'iframe[title*="Cloudflare"]', 
        'iframe[src*="challenge"]', 
        'div#turnstile-wrapper',
        '.check-wrapper'
    ]
    for selector in cf_selectors:
        if sb.is_element_visible(selector):
            print(" -> ⚠️ 发现 Cloudflare 验证拦截，正在尝试自动绕过...")
            try:
                sb.uc_gui_handle_captcha()
                time.sleep(10)
                return True
            except:
                pass
    return False

def process_account(sb, username, password):
    print(f"\n[+] 开始处理账号: {username}")
    account_report = [f"👤 账号: <b>{username}</b>"]
    
    try:
        sb.maximize_window()
        
        # ---------------- 1. 尝试使用 Cookie 直接进入控制台 ----------------
        if PTERODACTYL_COOKIE and '#' in PTERODACTYL_COOKIE:
            print(" -> 检测到 Cookie，尝试注入并跳过登录...")
            sb.uc_open_with_reconnect(DASHBOARD_URL, 4)
            c_name, c_value = PTERODACTYL_COOKIE.split('#')
            sb.add_cookie({"name": c_name.strip(), "value": c_value.strip()})
            sb.refresh_page()
            time.sleep(5)
            
        # ---------------- 2. 检查登录状态 ----------------
        if "auth.zampto.net" in sb.get_current_url() or "sign-in" in sb.get_current_url():
            print(" -> Cookie 无效，执行常规登录逻辑...")
            sb.uc_open_with_reconnect(LOGIN_URL, 4)
            handle_cf_challenge(sb)
            
            # 输入账号
            acc_input = 'input[name="identifier"], input[name="email"], input[type="email"]'
            sb.wait_for_element_present(acc_input, timeout=20)
            sb.type(acc_input, username)
            sb.click('button[type="submit"]')
            time.sleep(3)
            
            # 输入密码
            sb.wait_for_element_present('input[type="password"]', timeout=15)
            sb.type('input[type="password"]', password)
            sb.click('button[type="submit"]')
            print(" -> 已提交登录信息，等待跳转...")
            time.sleep(15)
            handle_cf_challenge(sb)

        # ---------------- 3. 处理授权页面 (如果有) ----------------
        if "auth.zampto.net" in sb.get_current_url() and sb.is_text_visible("Authorize"):
            print(" -> 发现授权确认页，点击 Authorize...")
            sb.click('button:contains("Authorize")')
            time.sleep(8)

        # ---------------- 4. 执行续期 ----------------
        if "dash.zampto.net" not in sb.get_current_url():
            sb.save_screenshot(f"{username}_login_error.png")
            return False, f"❌ 账号 {username} 登录失败，可能卡在 CF 验证码。"

        print(" ✅ 登录成功，进入续期环节...")
        for url in RENEW_URLS:
            server_id = url.split('=')[-1]
            print(f" -> 正在处理服务 ID: {server_id}")
            sb.uc_open_with_reconnect(url, 3)
            time.sleep(8)
            
            # 清理广告遮挡
            for btn in ['div:contains("Close")', 'button:contains("Hide")', 'span:contains("Close")']:
                if sb.is_element_visible(btn):
                    sb.js_click(btn)
            
            sb.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            renew_btn = 'button:contains("Renew Server")'
            
            if sb.is_element_visible(renew_btn):
                sb.js_click(renew_btn)
                print(" -> 已点击续期，等待验证码弹窗...")
                time.sleep(10)
                handle_cf_challenge(sb)
                time.sleep(15)
                
                shot = f"success_{username}_{server_id}.png"
                sb.save_screenshot(shot)
                send_telegram_photo(shot, f"✅ {username}\nID: {server_id} 续期操作完成")
                account_report.append(f" ✅ ID {server_id}: 成功")
            else:
                account_report.append(f" ℹ️ ID {server_id}: 无需续期")

        return True, "\n".join(account_report)

    except Exception as e:
        sb.save_screenshot(f"error_{username}.png")
        return False, f"❌ 运行崩溃: {str(e)[:100]}"

def main():
    if not ZAMPTO_ACCOUNT:
        print("未配置 ZAMPTO_ACCOUNT")
        return
        
    accounts = [line.strip() for line in ZAMPTO_ACCOUNT.split('\n') if line.strip()]
    
    # 针对 GitHub Actions 的推荐启动参数
    with SB(uc=True, proxy=LOCAL_PROXY, headless=True, ad_block=True) as sb:
        for acc in accounts:
            if ':' not in acc: continue
            u, p = acc.split(':', 1)
            _, report = process_account(sb, u, p)
            print(report)

if __name__ == "__main__":
    main()
