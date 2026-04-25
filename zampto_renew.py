import os
import time
import requests
from seleniumbase import SB

# ================= 配置区域 =================
LOGIN_URL = "https://auth.zampto.net/sign-in?app_id=bmhk6c8qdqxphlyscztgl"

RENEW_URLS = [
    "https://dash.zampto.net/server?id=5933"
]

# ================= 环境变量 =================
ZAMPTO_ACCOUNT = os.environ.get('ZAMPTO_ACCOUNT', '')
TG_BOT = os.environ.get('TG_BOT', '')
USE_PROXY = os.environ.get('USE_PROXY') == 'true'

# 使用 Xray 代理的默认本地 SOCKS5 端口
LOCAL_PROXY = "socks5://127.0.0.1:10808" if USE_PROXY else None

def send_telegram_msg(message):
    """发送 Telegram 纯文本通知"""
    if not TG_BOT:
        return
    try:
        token, chat_id = TG_BOT.split('#')
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"TG 通知发送失败: {e}")

def send_telegram_photo(photo_path, caption=""):
    """发送 Telegram 图片通知"""
    if not TG_BOT:
        return
    try:
        token, chat_id = TG_BOT.split('#')
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        with open(photo_path, 'rb') as f:
            payload = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
            requests.post(url, data=payload, files={"photo": f}, timeout=20)
    except Exception as e:
        print(f"TG 图片发送失败: {e}")

def process_account(sb, username, password):
    """处理单个账号及其下的所有服务续期"""
    print(f"\n[+] 开始处理账号: {username}")
    account_report = [f"👤 账号: <b>{username}</b>"]
    
    # 锁定真正 CF 验证码的特征选择器
    cf_selector = 'iframe[title*="Cloudflare"], iframe[src*="challenge"], iframe[src*="turnstile"]'
    
    try:
        # ---------------- 1. 登录 ----------------
        print(" -> 正在访问登录页面...")
        sb.maximize_window()
        sb.uc_open_with_reconnect(LOGIN_URL, 4)
        time.sleep(5) 
        
        print(" -> 填写账号...")
        account_input = 'input[name="identifier"], input[name="email"], input[type="email"], input[type="text"]'
        sb.wait_for_element_visible(account_input, timeout=15)
        sb.type(account_input, username)
        
        print(" -> 点击第一步的继续按钮...")
        sb.click('button[type="submit"], button:contains("Sign in"), button.cl-formButtonPrimary')
        time.sleep(5)
        
        print(" -> 填写密码...")
        sb.wait_for_element_visible('input[type="password"]', timeout=15)
        sb.type('input[type="password"]', password)
        time.sleep(1)
        
        print(" -> 点击继续按钮，触发验证码...")
        submit_btn = 'button[type="submit"], button:contains("Continue"), button:contains("继续"), button:contains("Sign in")'
        try:
            sb.click(submit_btn)
        except:
            pass
            
        print(" -> 傻等 12 秒，让 Cloudflare 验证码充分加载...")
        time.sleep(12)
        
        print(" -> 准备执行多重拟人点击...")
        try:
            sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", sb.find_element(submit_btn))
        except:
            pass
        time.sleep(2)
        
        try:
            sb.uc_gui_click_captcha()
        except:
            pass
        time.sleep(2)
        
        try:
            if sb.is_element_visible(cf_selector):
                sb.uc_click(cf_selector)
            else:
                sb.uc_click('iframe')
        except:
            pass
            
        print(" -> 登录验证码已点击，静候 25 秒等待系统验证并跳转...")
        time.sleep(25)
        
        if "dash.zampto.net" not in sb.get_current_url():
             sb.save_screenshot(f"{username}_login_failed.png")
             return False, f"❌ 账号 <b>{username}</b> 登录失败，未能成功跳转到控制台。"

        print(" -> 登录成功！")

        # ---------------- 2. 依次处理多个服务 ----------------
        for idx, url in enumerate(RENEW_URLS):
            server_id = url.split('=')[-1]
            print(f"\n -> [服务 {server_id}] 正在打开面板...")
            
            sb.uc_open_with_reconnect(url, 3)
            time.sleep(8) 
            
            # 【全新精准扫雷模式】：对付 Google 问卷及悬浮广告
            print(" -> 等待并检查可能出现的悬浮广告 (最多检查 3 次)...")
            for i in range(3):
                time.sleep(3) # 给广告充足的加载和弹出动画时间
                try:
                    ad_closed = False
                    # 遍历可能的 Close 按钮形式
                    for target in ['div:contains("Close")', 'span:contains("Close")', 'a:contains("Close")', 'button:contains("Hide")']:
                        if sb.is_element_visible(target):
                            print(f"    [+] 第 {i+1} 次发现干扰广告，正在点击右上角 Close...")
                            sb.js_click(target)  # 使用 js_click 确保点击生效
                            time.sleep(2)
                            ad_closed = True
                            break # 关掉一个后，跳出当前 target 循环，进入下一次全盘检查
                    
                    if not ad_closed:
                        print("    [+] 页面干净，未检测到新的悬浮广告。")
                        break # 如果这一轮没找到任何广告，说明清理干净了，安全退出循环
                except Exception as e:
                    pass
            
            print(" -> 向下滚动页面，寻找续期按钮...")
            sb.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # 处理全屏跳转广告 (Vignette)
            if "google_vignette" in sb.get_current_url():
                print(f" -> [服务 {server_id}] 拦截到全屏网址跳转广告，尝试刷新跳过...")
                sb.refresh()
                time.sleep(8)
                sb.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            try:
                renew_btn = 'button:contains("Renew Server"), a:contains("Renew Server")'
                
                if sb.is_element_visible(renew_btn):
                    sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", sb.find_element(renew_btn))
                    time.sleep(1)
                    
                    # 依然使用 js_click，无视任何残存的微小透明遮挡
                    sb.js_click(renew_btn)
                    print(f" -> [服务 {server_id}] 已强制点击续期按钮，正在加载弹窗验证码...")
                    time.sleep(8) 
                    
                    try:
                        if sb.is_element_visible(cf_selector):
                            sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", sb.find_element(cf_selector))
                    except:
                        pass
                    time.sleep(2)
                    
                    try:
                        sb.uc_gui_click_captcha()
                    except:
                        pass
                    time.sleep(2)
                    
                    try:
                        if sb.is_element_visible(cf_selector):
                            sb.uc_click(cf_selector)
                        else:
                            sb.uc_click('iframe')
                    except:
                        pass
                    
                    print(f" -> [服务 {server_id}] 弹窗验证码已点击，等待 25 秒让系统自动跳转完成续期...")
                    time.sleep(25) 
                    
                    screenshot_name = f"{username}_server_{server_id}_done.png"
                    sb.save_screenshot(screenshot_name)
                    print(f" -> [服务 {server_id}] 截图已保存，正在发送至 Telegram...")
                    
                    caption_msg = f"✅ <b>Zampto 续期成功</b>\n账号: {username}\n服务 ID: {server_id}"
                    send_telegram_photo(screenshot_name, caption_msg)
                    
                    account_report.append(f"  ✅ ID {server_id}: 续期成功！(已发送截图)")
                else:
                    sb.save_screenshot(f"{username}_server_{server_id}_no_btn.png")
                    account_report.append(f"  ℹ️ ID {server_id}: 未找到续期按钮 (可能暂无需续期)")
            except Exception as e:
                account_report.append(f"  ❌ ID {server_id}: 处理出错")
                print(f" -> [服务 {server_id}] 错误: {e}")

        return True, "\n".join(account_report)

    except Exception as e:
        error_shot = f"{username}_fatal_error.png"
        sb.save_screenshot(error_shot)
        send_telegram_photo(error_shot, f"❌ <b>Zampto 崩溃告警</b>\n账号: {username}\n查看截图诊断问题。")
        return False, f"❌ 账号 <b>{username}</b> 流程崩溃: {str(e)[:100]}"

def main():
    if not ZAMPTO_ACCOUNT:
        print("错误: 未配置 ZAMPTO_ACCOUNT 环境变量")
        return

    accounts = [line.strip() for line in ZAMPTO_ACCOUNT.split('\n') if line.strip()]
    final_reports = ["<b>Zampto 自动化续期汇总</b>"]

    with SB(uc=True, proxy=LOCAL_PROXY, headless=False) as sb:
        for acc in accounts:
            if ':' not in acc: continue
            user, pwd = acc.split(':', 1)
            success, report = process_account(sb, user, pwd)
            final_reports.append(report)
            time.sleep(5)

    full_msg = "\n\n".join(final_reports)
    print(full_msg.replace("<b>", "").replace("</b>", ""))
    send_telegram_msg(full_msg)

if __name__ == "__main__":
    main()
