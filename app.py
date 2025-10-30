import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import time
import re
import pandas as pd
import io
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from datetime import datetime
import json
import os
import contextlib

# Google 서비스 계정 키 로드
SERVICE_ACCOUNT_FILE = "service_account_key.json"

# Google Sheets ID
GOOGLE_SHEETS_ID = "1ghPP5RLJdQyGBJ-hUVp-P-Iq6qbhaFPVcGIl0DRpweA"
GOOGLE_SHEETS_RANGE = "시트1!A1:Z1000"  # 시트1의 A1부터 Z1000까지

def load_service_account():
    """서비스 계정 키 파일 로드"""
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        try:
            with open(SERVICE_ACCOUNT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            return None
    return None


def load_google_sheets_data(credentials):
    """Google Sheets에서 데이터를 읽어서 pandas DataFrame으로 반환"""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound, APIError
        
        # 인증 범위 설정
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive.readonly'
        ]
        
        # 서비스 계정 인증 정보 생성
        creds = Credentials.from_service_account_info(credentials, scopes=scopes)
        client = gspread.authorize(creds)
        
        # 시트 열기
        sheet = client.open_by_key(GOOGLE_SHEETS_ID)
        
        # 사용 가능한 워크시트 목록 확인
        available_worksheets = [ws.title for ws in sheet.worksheets()]
        
        # 시트 이름 찾기 (여러 가능한 이름 시도)
        worksheet = None
        possible_sheet_names = ["시트1", "Sheet1", "요금자료", available_worksheets[0] if available_worksheets else None]
        
        for sheet_name in possible_sheet_names:
            if sheet_name is None:
                continue
            try:
                worksheet = sheet.worksheet(sheet_name)
                break
            except WorksheetNotFound:
                continue
        
        if worksheet is None:
            error_msg = f"시트를 찾을 수 없습니다. 사용 가능한 시트: {', '.join(available_worksheets)}"
            return None, error_msg
        
        # 모든 데이터 가져오기
        all_values = worksheet.get_all_values()
        
        if not all_values or len(all_values) < 2:
            return None, "시트에 데이터가 없습니다."
        
        # 첫 번째 행은 비어있고, 두 번째 행이 헤더
        # 헤더는 2번째 행 (인덱스 1), 데이터는 3번째 행부터
        headers = all_values[1]  # 2번째 행이 헤더
        data_rows = all_values[2:]  # 3번째 행부터가 데이터
        
        # 빈 행 제거
        data_rows = [row for row in data_rows if any(cell.strip() for cell in row)]
        
        if not data_rows:
            return None, "데이터 행이 없습니다."
        
        # pandas DataFrame 생성
        df = pd.DataFrame(data_rows, columns=headers)
        
        # 빈 열 제거
        df = df.dropna(axis=1, how='all')
        
        return df, None
        
    except ImportError as e:
        return None, f"gspread 라이브러리가 설치되지 않았습니다: {str(e)}\n\npip install gspread google-auth를 실행해주세요."
    except SpreadsheetNotFound:
        return None, f"스프레드시트를 찾을 수 없습니다. 시트 ID를 확인해주세요: {GOOGLE_SHEETS_ID}"
    except APIError as e:
        error_msg = str(e)
        if "PERMISSION_DENIED" in error_msg or "insufficient authentication" in error_msg.lower():
            return None, f"권한 오류: 서비스 계정에 시트 접근 권한이 없습니다.\n\n서비스 계정 이메일({credentials.get('client_email', '')})에 시트 공유 권한을 부여해주세요."
        return None, f"Google API 오류: {error_msg}"
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return None, f"Google Sheets 읽기 오류:\n{str(e)}\n\n상세 오류:\n{error_detail[-500:]}"  # 마지막 500자만 표시

def search_address(address, dong=None, ho=None):
    """주소 검색 자동화 - Selenium 구현 위임"""
    return search_address_selenium(address, dong, ho)

def _unused_playwright_impl():
    # Legacy Playwright implementation disabled
    pass

def search_address_selenium(address, dong=None, ho=None):
    """주소 검색 자동화 (Selenium)"""
    try:
        chrome_options = webdriver.ChromeOptions()
        # 기본은 브라우저 표시(HEADFUL). 환경변수로 전환 가능
        headful = os.getenv("SELENIUM_HEADFUL", "1") == "1"
        if not headful:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1280,900")
        chrome_options.add_argument("--lang=ko-KR")
        chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        wait = WebDriverWait(driver, 15)

        url = "https://www.bworld.co.kr/myb/product/join/address/svcAveSearch.do"
        driver.get(url)
        
        # 문서 로드 대기(최대 10초)
        try:
            WebDriverWait(driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
        except Exception:
            pass
        
        # 잠재적 팝업/배너 닫기 시도 (무시 가능)
        try:
            for sel in [
                'a.modal_close.modal_confirm_btn',
                'button.close',
                '.btn-close',
            ]:
                with contextlib.suppress(Exception):
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    if el.is_displayed():
                        el.click()
                        time.sleep(0.5)
        except Exception:
            pass
        
        # 입력창 찾기: 메인 → 모든 iframe 재귀 순회
        input_selectors = [
            "#inpNameStreet",              # 페이지 공식 주소 입력 필드
            "input[name='keyword']",
            "input#keyword",
            "#keyword",
            "input[placeholder*='주소']",
            "input[placeholder*='지번']",
            "input[placeholder*='도로명']",
            "input[type='search']",
            "input[type='text']",
        ]
        input_el = None

        def find_visible_input(scope_driver):
            for sel in input_selectors:
                try:
                    el = scope_driver.find_element(By.CSS_SELECTOR, sel)
                    if el and el.is_displayed():
                        return el
                except Exception:
                    continue
            return None

        def find_input_recursively(scope_driver, depth=0, max_depth=3):
            el = find_visible_input(scope_driver)
            if el:
                return el
            if depth >= max_depth:
                return None
            frames = scope_driver.find_elements(By.TAG_NAME, 'iframe')
            for frame in frames:
                try:
                    scope_driver.switch_to.frame(frame)
                    found = find_input_recursively(scope_driver, depth + 1, max_depth)
                    if found:
                        return found
                except Exception:
                    pass
                finally:
                    scope_driver.switch_to.default_content()
            return None

        # 1) 기본 문서/프레임 전체에서 검색
        input_el = find_input_recursively(driver)

        # 2) 못 찾으면 visibility 대기 후 재시도
        if input_el is None:
            # 가시성 기준이 안 맞았을 수 있어 존재 기준 + 가시성 대기
            try:
                for sel in input_selectors:
                    try:
                        input_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
                        if input_el:
                            break
                    except Exception:
                        continue
            except Exception:
                pass
        
        if input_el is None:
            screenshot_path = "error_page.png"
            driver.save_screenshot(screenshot_path)
            driver.quit()
            return {"status": "error", "message": "주소 입력창을 찾을 수 없습니다.", "screenshot": screenshot_path}
        
        # 입력 요소 인터랙션 강화: 스크롤/클릭/JS 대체
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", input_el)
        except Exception:
            pass
        
        try:
            wait.until(EC.element_to_be_clickable((By.XPATH, "(//input[@name='keyword']|//*[@id='keyword']|//input[@type='text'])[1]")))
        except Exception:
            pass
        
        interacted = False
        try:
            input_el.clear()
        except Exception:
            pass
        try:
            ActionChains(driver).move_to_element(input_el).pause(0.1).click().perform()
            input_el.send_keys(address)
            interacted = True
        except Exception:
            pass
        
        if not interacted:
            # JS로 값 설정 및 input 이벤트 발생
            try:
                driver.execute_script(
                    "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
                    input_el,
                    address,
                )
                interacted = True
            except Exception:
                pass
        
        # 제출: 전용 조회 버튼(#btnNameSearchStreet) → 기타 버튼 → 엔터 → 폼 submit 순차 시도
        submitted = False
        submit_selectors = [
            "#btnNameSearchStreet",
            "button.btn-search",
            "button[type='submit']",
            ".btn-search",
            "input[type='submit']",
            "#searchBtn",
            "a.btn-search"
        ]
        if interacted:
            for sel in submit_selectors:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, sel)
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                        btn.click()
                        submitted = True
                        break
                except Exception:
                    continue
            
            if not submitted:
                try:
                    ActionChains(driver).move_to_element(input_el).send_keys(Keys.ENTER).perform()
                    submitted = True
                except Exception:
                    pass
            
            if not submitted:
                try:
                    form = input_el.find_element(By.XPATH, "ancestor::form")
                    driver.execute_script("arguments[0].submit();", form)
                    submitted = True
                except Exception:
                    pass
        
        time.sleep(2)

        results = []
        first_clickable = None
        result_selectors = [
            ".result-list li",
            ".search-result li",
            ".addr-list li",
            "ul.list-result li",
            ".result-item",
            "li[class*='item']"
        ]
        # 우선 라디오 결과(주소 선택) 우선 탐색
        try:
            radios = driver.find_elements(By.CSS_SELECTOR, ".adress_search_result-item input[type='radio']")
            if radios:
                # 첫 번째 라디오의 label 클릭
                first_radio = radios[0]
                radio_id = first_radio.get_attribute("id") or "radio_01"
                try:
                    lbl = driver.find_element(By.CSS_SELECTOR, f"label[for='{radio_id}']")
                    with contextlib.suppress(Exception):
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", lbl)
                    try:
                        lbl.click()
                    except Exception:
                        with contextlib.suppress(Exception):
                            driver.execute_script("arguments[0].click();", lbl)
                    time.sleep(1.0)
                    first_clickable = lbl
                except Exception:
                    pass
        except Exception:
            pass
        for sel in result_selectors:
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    for e in elems:
                        txt = e.text.strip()
                        if txt:
                            results.append(txt)
                            if not first_clickable:
                                first_clickable = e
                    if results:
                        break
            except Exception:
                continue

        selected_result = None
        if first_clickable:
            try:
                with contextlib.suppress(Exception):
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", first_clickable)
                try:
                    first_clickable.click()
                except Exception:
                    with contextlib.suppress(Exception):
                        driver.execute_script("arguments[0].click();", first_clickable)
                time.sleep(2)
                info_selectors = [
                    ".result-detail",
                    ".selected-address",
                    "div[class*='detail']",
                    "div[class*='result']",
                    "table",
                    ".info-table",
                    ".address-info"
                ]
                details = []
                for sel in info_selectors:
                    try:
                        for de in driver.find_elements(By.CSS_SELECTOR, sel):
                            t = de.text.strip()
                            if t and len(t) > 10:
                                details.append(t)
                        if details:
                            break
                    except Exception:
                        continue
                if details:
                    selected_result = "\n".join(details)
                else:
                    try:
                        body_text = driver.find_element(By.TAG_NAME, "body").text
                        selected_result = body_text[:500]
                    except Exception:
                        pass
            except Exception:
                pass

        # 서비스조회 라디오/버튼 처리 및 동/호 선택 (유사 매칭)
        def fuzzy_match(target_text, option_text):
            try:
                if not target_text or not option_text:
                    return False
                t = target_text.strip()
                o = option_text.strip()
                if t == o or t in o or o in t:
                    return True
                import re as _re
                t_digits = ''.join(_re.findall(r'\d+', t))
                o_digits = ''.join(_re.findall(r'\d+', o))
                if t_digits and t_digits == o_digits:
                    return True
                t_nums = set(_re.findall(r'\d+', t))
                o_nums = set(_re.findall(r'\d+', o))
                return bool(t_nums and o_nums and (t_nums & o_nums))
            except Exception:
                return False

        def similarity_score(target_text, option_element):
            try:
                import re as _re
                otext = (option_element.text or "").strip()
                oval = option_element.get_attribute('data-value') or ""
                t = (target_text or "").strip()
                # exact on data-value
                if oval and oval == t:
                    return 0
                # digits-based distance
                tnums = _re.findall(r'\d+', t)
                onums_text = _re.findall(r'\d+', otext)
                onums_val = _re.findall(r'\d+', oval)
                if tnums:
                    tnum = int(tnums[0])
                    cands = []
                    if onums_text:
                        cands.append(int(onums_text[0]))
                    if onums_val:
                        cands.append(int(onums_val[0]))
                    if cands:
                        return min(abs(tnum - c) for c in cands)
                # fallback: inclusion/length diff
                if t and (t in otext or otext in t or t in oval or oval in t):
                    return 1
                return max(len(t), 1)
            except Exception:
                return 9999

        # 라디오 선택
        try:
            for sel in ["label[for='radio_01']", "#radio_01", "input[type='radio'][id='radio_01']"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    if el.is_displayed():
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                        except Exception:
                            pass
                        try:
                            el.click()
                        except Exception:
                            with contextlib.suppress(Exception):
                                driver.execute_script("arguments[0].click();", el)
                        break
                except Exception:
                    continue
        except Exception:
            pass

        # 서비스조회 버튼 클릭
        try:
            svc_clicked = False
            for tag in ["button", "a"]:
                if svc_clicked:
                    break
                try:
                    for el in driver.find_elements(By.TAG_NAME, tag):
                        with contextlib.suppress(Exception):
                            txt = el.text.strip()
                            if txt and ("서비스조회" in txt):
                                try:
                                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                                except Exception:
                                    pass
                                try:
                                    el.click()
                                except Exception:
                                    with contextlib.suppress(Exception):
                                        driver.execute_script("arguments[0].click();", el)
                                svc_clicked = True
                                break
                except Exception:
                    pass
            if not svc_clicked:
                with contextlib.suppress(Exception):
                    el = driver.find_element(By.CSS_SELECTOR, "div.butn_wrap.event_pop_butn")
                    el.click()
            time.sleep(1)
        except Exception:
            pass

        # 팝업 확인 닫기 (존재 시)
        try:
            with contextlib.suppress(Exception):
                c = driver.find_element(By.CSS_SELECTOR, 'a.modal_close.modal_confirm_btn')
                if c.is_displayed():
                    c.click()
                    time.sleep(0.5)
        except Exception:
            pass

        matched_dong_text = None
        matched_ho_text = None

        # 동 선택
        if dong:
            try:
                with contextlib.suppress(Exception):
                    btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button#input_Id3')))
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    btn.click()
                    time.sleep(0.5)
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'ul#dongSelectList')))
                time.sleep(0.3)
                options = driver.find_elements(By.CSS_SELECTOR, 'ul#dongSelectList li button')
                chosen = None
                # 선택 가능한 항목들의 "중간값" 선택
                if options:
                    try:
                        selectable = [o for o in options if o.is_displayed() and o.is_enabled()] or options
                        mid_idx = len(selectable) // 2
                        chosen = selectable[mid_idx]
                    except Exception:
                        chosen = options[len(options)//2]
                if chosen:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", chosen)
                    except Exception:
                        pass
                    try:
                        chosen.click()
                    except Exception:
                        with contextlib.suppress(Exception):
                            driver.execute_script("arguments[0].click();", chosen)
                    time.sleep(0.5)
            except Exception:
                pass

        # 호 선택
        if ho:
            try:
                with contextlib.suppress(Exception):
                    btn = driver.find_element(By.CSS_SELECTOR, 'button#input_Id4')
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                        btn.click()
                        time.sleep(0.4)
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'ul#hoSelectList')))
                time.sleep(0.3)
                options = driver.find_elements(By.CSS_SELECTOR, 'ul#hoSelectList li button')
                chosen = None
                # 선택 가능한 항목들의 "중간값" 선택
                if options:
                    try:
                        selectable = [o for o in options if o.is_displayed() and o.is_enabled()] or options
                        mid_idx = len(selectable) // 2
                        chosen = selectable[mid_idx]
                    except Exception:
                        chosen = options[len(options)//2]
                if chosen:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", chosen)
                    except Exception:
                        pass
                    try:
                        chosen.click()
                    except Exception:
                        with contextlib.suppress(Exception):
                            driver.execute_script("arguments[0].click();", chosen)
                    time.sleep(0.5)
            except Exception:
                pass

        # 최종 서비스 조회 버튼(있다면) 한 번 더 시도
        try:
            with contextlib.suppress(Exception):
                btn = driver.find_element(By.CSS_SELECTOR, 'button#GA_CY_MENU_C00000001')
                if btn.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    btn.click()
                    time.sleep(1.0)
        except Exception:
            pass

        screenshot_path = "search_result.png"
        try:
            driver.save_screenshot(screenshot_path)
        except Exception:
            screenshot_path = None

        # 브라우저 유지 옵션 (요청 시 창 띄워 보기)
        keep_browser = os.getenv("SELENIUM_KEEP_BROWSER", "0") == "1"
        if not keep_browser:
            driver.quit()
        return {
            "status": "success",
            "message": f"주소 검색이 완료되었습니다. {len(results)}개의 결과를 찾았습니다." + ("\n첫 번째 항목이 자동으로 선택되었습니다." if selected_result else ""),
            "results": results,
            "selected_result": selected_result,
            "service_result": None,
            "screenshot": screenshot_path
        }
    except Exception as e:
        try:
            screenshot_path = "error_page.png"
            try:
                driver.save_screenshot(screenshot_path)
            except Exception:
                screenshot_path = None
            driver.quit()
        except Exception:
            pass
        return {"status": "error", "message": f"브라우저 실행 중 오류 발생: {str(e)}"}

# 기존 호출을 Selenium 구현으로 교체
search_address = search_address_selenium
def process_excel_data(excel_file):
    """엑ល 파일을 읽어서 데이터프레임 반환"""
    try:
        # 엑셀 파일 읽기
        df = pd.read_excel(excel_file, engine='openpyxl')
        return df
    except Exception as e:
        return None, f"엑셀 파일 읽기 오류: {str(e)}"


def get_price_info(filtered_df):
    """필터링된 데이터프레임에서 요금 정보 추출"""
    try:
        # '월요금'과 '지원금' 컬럼 찾기
        price_columns = [col for col in filtered_df.columns if '월요금' in str(col) or '요금' in str(col)]
        support_columns = [col for col in filtered_df.columns if '지원금' in str(col)]
        
        row_data = filtered_df.iloc[0]  # 첫 번째 매칭되는 행
        price = row_data[price_columns[0]] if price_columns else "정보 없음"
        support = row_data[support_columns[0]] if support_columns else "정보 없음"
        
        return price, support
    except Exception as e:
        return "정보 없음", "정보 없음"


def send_contact_email(name, phone, email, message, recipient_email, smtp_email=None, smtp_password=None):
    """연락처 정보를 이메일로 전송하는 함수"""
    try:
        # 이메일 설정이 없으면 기본 Gmail 사용
        if not smtp_email or not smtp_password:
            return {
                "status": "error",
                "message": "이메일 설정이 필요합니다. 사이드바에서 SMTP 설정을 확인해주세요."
            }
        
        # 이메일 내용 구성
        msg = MIMEMultipart('alternative')
        msg['From'] = smtp_email
        msg['To'] = recipient_email
        
        # 제목을 UTF-8로 인코딩
        subject = Header(f"[SK 인터넷] 새로운 상담 문의 - {name}님", 'utf-8')
        msg['Subject'] = subject
        
        # HTML 형식의 이메일 본문
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #0066cc;">📞 새로운 상담 문의</h2>
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px 0;">
                <p><strong>📅 접수 시간:</strong> {datetime.now().strftime('%Y년 %m월 %d일 %H:%M:%S')}</p>
                <p><strong>👤 이름:</strong> {name}</p>
                <p><strong>📱 전화번호:</strong> {phone}</p>
                <p><strong>📧 이메일:</strong> {email}</p>
            </div>
            <div style="margin: 20px 0;">
                <h3 style="color: #0066cc;">📝 문의 내용:</h3>
                <p style="background-color: #ffffff; padding: 15px; border-left: 4px solid #0066cc;">
                    {message.replace(chr(10), '<br>')}
                </p>
            </div>
            <hr style="border: 1px solid #e0e0e0; margin: 20px 0;">
            <p style="color: #666; font-size: 12px;">
                이 메일은 SK 인터넷 설계 페이지를 통해 자동 발송되었습니다.<br>
                고객의 개인정보 수집 및 이용에 동의한 내용입니다.
            </p>
        </body>
        </html>
        """
        
        # HTML 본문을 UTF-8로 명시적으로 인코딩
        html_part = MIMEText(body, 'html', 'utf-8')
        msg.attach(html_part)
        
        # Gmail SMTP 서버를 통해 이메일 전송
        server = None
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_email, smtp_password)
            
            # UTF-8로 인코딩된 이메일 전송
            server.sendmail(smtp_email, recipient_email, msg.as_bytes())
            
            return {
                "status": "success",
                "message": "연락처가 성공적으로 전송되었습니다!"
            }
        finally:
            if server:
                try:
                    server.quit()
                except:
                    pass
                    
    except smtplib.SMTPAuthenticationError:
        return {
            "status": "error",
            "message": "이메일 인증에 실패했습니다. SMTP 설정을 확인해주세요."
        }
    except UnicodeEncodeError as e:
        return {
            "status": "error",
            "message": f"한글 인코딩 오류가 발생했습니다: {str(e)}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"이메일 전송 중 오류가 발생했습니다: {str(e)}"
        }


def main():
    st.set_page_config(
        page_title="SK 인터넷 요금 설계표",
        page_icon="📡",
        layout="wide"
    )
    
    # 서비스 계정 키 로드
    SERVICE_ACCOUNT_CREDENTIALS = load_service_account()
    
    # 사이드바 - Google Sheets 데이터 로드 및 이메일 설정
    with st.sidebar:
        st.header("📂 데이터 관리")
        
        # Google Sheets에서 자동으로 데이터 로드
        if SERVICE_ACCOUNT_CREDENTIALS:
            st.info("📊 Google Sheets에서 자동으로 데이터를 불러옵니다.")
            
            # 데이터가 없으면 자동으로 로드
            if 'excel_data' not in st.session_state:
                with st.spinner("Google Sheets에서 데이터를 가져오는 중..."):
                    df, error = load_google_sheets_data(SERVICE_ACCOUNT_CREDENTIALS)
                    if df is not None and error is None:
                        st.session_state.excel_data = df
                        st.session_state.uploaded_file_name = "Google Sheets (시트1)"
                        st.success("✅ Google Sheets에서 데이터를 성공적으로 불러왔습니다!")
                        st.info(f"📊 총 {len(df)}개의 행을 불러왔습니다.")
                    else:
                        st.error(f"❌ {error if error else '데이터를 불러올 수 없습니다.'}")
                        st.session_state.excel_data = None
            
            # 데이터가 있는 경우 표시 및 새로고침 버튼
            if 'excel_data' in st.session_state and st.session_state.excel_data is not None:
                st.success(f"✅ Google Sheets (시트1) 사용 중")
                st.info(f"📊 {len(st.session_state.excel_data)}개의 행")
                if st.button("🔄 Google Sheets 새로고침"):
                    with st.spinner("Google Sheets에서 데이터를 가져오는 중..."):
                        df, error = load_google_sheets_data(SERVICE_ACCOUNT_CREDENTIALS)
                        if df is not None and error is None:
                            st.session_state.excel_data = df
                            st.session_state.uploaded_file_name = "Google Sheets (시트1)"
                            st.success("✅ 데이터를 새로고침했습니다!")
                            st.info(f"📊 총 {len(df)}개의 행을 불러왔습니다.")
                            st.rerun()
                        else:
                            st.error(f"❌ {error if error else '데이터를 불러올 수 없습니다.'}")
            
            # 접근 권한 안내
            with st.expander("ℹ️ Google Sheets 접근 권한 안내", expanded=False):
                st.success("✅ 서비스 계정 권한이 설정되었습니다!")
                st.markdown(f"""
                **서비스 계정 이메일:**
                ```
                {SERVICE_ACCOUNT_CREDENTIALS.get('client_email', 'ai-coding@huhsame-project-1.iam.gserviceaccount.com')}
                ```
                
                **Google Sheets 링크:**
                [시트 열기](https://docs.google.com/spreadsheets/d/{GOOGLE_SHEETS_ID}/edit)
                """)
        else:
            st.warning("⚠️ Google Sheets를 사용하려면 서비스 계정 키가 필요합니다.")
            st.markdown("---")
            st.header("📂 엑셀 파일 업로드 (대체 옵션)")
        uploaded_file = st.file_uploader(
            "요금 설계용 엑셀 파일 업로드",
            type=['xlsx', 'xls'],
            help="상품 정보가 포함된 엑셀 파일을 업로드해주세요"
        )
        
        if uploaded_file is not None:
            # 엑셀 데이터 읽기 (header=1 사용)
            if 'excel_data' not in st.session_state or st.session_state.uploaded_file_name != uploaded_file.name:
                with st.spinner("엑셀 파일을 읽는 중..."):
                    try:
                        # header=1로 두 번째 행을 헤더로 사용
                        df = pd.read_excel(uploaded_file, header=1, engine='openpyxl')
                        st.session_state.excel_data = df
                        st.session_state.uploaded_file_name = uploaded_file.name
                        st.success(f"✅ {uploaded_file.name} 업로드 완료!")
                    except Exception as e:
                        st.error(f"엑셀 파일 읽기 오류: {str(e)}")
                        st.session_state.excel_data = None
            else:
                st.success(f"✅ {uploaded_file.name} 사용 중")
                
        # 데이터 초기화 버튼
        if st.button("🗑️ 데이터 초기화"):
            for key in ['excel_data', 'uploaded_file_name', 'selections']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
        
        st.markdown("---")
        
        # Google 서비스 계정 상태 표시
        st.header("🔐 Google 서비스 계정")
        if SERVICE_ACCOUNT_CREDENTIALS:
            st.success("✅ 서비스 계정 키가 로드되었습니다!")
            with st.expander("서비스 계정 정보", expanded=False):
                st.json({
                    "project_id": SERVICE_ACCOUNT_CREDENTIALS.get("project_id"),
                    "client_email": SERVICE_ACCOUNT_CREDENTIALS.get("client_email"),
                    "client_id": SERVICE_ACCOUNT_CREDENTIALS.get("client_id")
                })
        else:
            st.warning("⚠️ 서비스 계정 키 파일을 찾을 수 없습니다.")
            st.caption("service_account_key.json 파일이 필요합니다.")
        
        st.markdown("---")
        
        # 이메일 설정
        st.header("📧 이메일 설정")
        st.info("📬 수신 이메일: **beckshop7@gmail.com**")
        st.markdown("상담 신청 내용을 받으려면 Gmail 앱 비밀번호를 설정해주세요.")
        
        with st.expander("🔧 Gmail 앱 비밀번호 설정 방법", expanded=False):
            st.markdown("""
            **Gmail 앱 비밀번호 생성 방법:**
            
            1. **Gmail 계정 로그인**
               - beckshop7@gmail.com 계정에 로그인
            
            2. **Google 계정 관리 페이지 이동**
               - [myaccount.google.com](https://myaccount.google.com) 접속
            
            3. **보안 탭 선택**
               - 왼쪽 메뉴에서 "보안" 클릭
            
            4. **2단계 인증 활성화** (아직 안 했다면)
               - "Google에 로그인" 섹션에서 "2단계 인증" 클릭
               - 화면 안내에 따라 설정
            
            5. **앱 비밀번호 생성**
               - "보안" 페이지에서 "앱 비밀번호" 검색
               - "앱 비밀번호" 클릭
               - 앱 선택: "메일", 기기 선택: "기타(맞춤 이름)"
               - 이름 입력 (예: "SK 인터넷 상담")
               - "생성" 클릭
               - **16자리 비밀번호 복사** (공백 제거)
            
            6. **아래 입력란에 붙여넣기**
            """)
        
        smtp_password = st.text_input(
            "Gmail 앱 비밀번호 (16자리)",
            type="password",
            placeholder="16자리 앱 비밀번호 입력",
            help="Gmail 앱 비밀번호를 입력하세요 (공백 없이)"
        )
        
        # 고정된 이메일 주소
        FIXED_EMAIL = "beckshop7@gmail.com"
        
        # 세션 상태에 저장
        if smtp_password:
            st.session_state.smtp_email = FIXED_EMAIL
            st.session_state.smtp_password = smtp_password.replace(" ", "")  # 공백 제거
            st.session_state.recipient_email = FIXED_EMAIL
            st.success("✅ 이메일 설정 완료! 이제 상담 신청을 받을 수 있습니다.")
        elif 'smtp_password' in st.session_state:
            st.success("✅ 이메일 설정이 활성화되어 있습니다.")
        else:
            st.warning("⚠️ 상담 신청을 받으려면 Gmail 앱 비밀번호를 입력해주세요.")
    
    # 메인 콘텐츠
    st.title("📡 SK 인터넷 설계 안내 페이지")
    st.markdown("안녕하세요! SK인터넷 찾아주셔서 감사합니다. 요금안내 및 설치가능 지역 조회를 선택하시면 안내드리겠습니다. 😊")
    st.markdown("결과 조회 후 상담을 원하시면 채팅창에 전화번호를 남겨주시거나 전화주시기 바랍니다.")
    st.markdown("사이드바에서 Google Sheets 데이터가 자동으로 로드되며, 상품 조건을 선택하면 선택 결과를 요약해 보여드립니다.")
    
    # 두 개의 컬럼으로 구성: 요금 설계와 주소 조회
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.markdown("### 💰 요금 설계")
        
        if 'excel_data' in st.session_state and st.session_state.excel_data is not None:
            df = st.session_state.excel_data
            
            st.subheader("요금 설계 선택")
            
            # 헤더 분류: 1-3번째는 드롭다운, 4-5번째는 표기만
            columns = list(df.columns)
            dropdown_cols = columns[:3] if len(columns) >= 3 else columns
            display_cols = columns[3:5] if len(columns) >= 5 else []
            
            selections = {}
            filtered_df = df.copy()
            
            # 1-3번째 헤더를 드롭다운으로
            for col in dropdown_cols:
                options = filtered_df[col].dropna().unique().tolist()
                if options:
                    selected = st.selectbox(f"{col} 선택", options, key=f"select_{col}")
                    selections[col] = selected
                    filtered_df = filtered_df[filtered_df[col] == selected]
            
            # 선택된 조건으로 데이터 필터링
            if selections:
                # 조건에 맞는 행 찾기
                final_df = filtered_df.copy()
                
                if not final_df.empty:
                    # 첫 번째 매칭되는 행
                    result_row = final_df.iloc[0]
                    
                    # 요금 정보 추출 (월요금, 지원금)
                    price, support = get_price_info(final_df)
                    
                    st.markdown("---")
                    st.markdown("### 📋 설계 항목")
                    
                    # 선택된 항목 표시 (1-3번째)
                    st.markdown("#### 선택된 상품 정보:")
                    for col, value in selections.items():
                        st.markdown(f"- **{col}**: {value}")
                    
                    # 4-5번째 항목 표시 (값만)
                    if display_cols:
                        st.markdown("#### 추가 정보:")
                        for col in display_cols:
                            value = result_row.get(col, "정보 없음")
                            st.markdown(f"- **{col}**: {value}")
                    
                    # 비고 항목 표시
                    note_col = None
                    for col in df.columns:
                        if '비고' in str(col) or 'NOTE' in str(col).upper() or '메모' in str(col):
                            note_col = col
                            break
                    
                    if note_col and note_col in result_row:
                        note_value = result_row.get(note_col, "")
                        if note_value and pd.notna(note_value):
                            st.markdown("---")
                            st.markdown("#### 📝 비고:")
                            st.info(str(note_value))
                    
                    st.markdown("---")
                    st.markdown("#### 💰 요금 정보:")
                    st.caption("💡 **안내**: 3년약정 기준, 부가세포함, 와이파이 포함 가격입니다")
                    
                    col_price1, col_price2 = st.columns(2)
                    with col_price1:
                        st.metric("📊 월요금", f"{price:,}원" if isinstance(price, (int, float)) else str(price))
                    with col_price2:
                        st.metric("🎁 지원금", f"{support:,}원" if isinstance(support, (int, float)) else str(support))
                    
                    st.success("✅ 요금 설계가 완료되었습니다!")
                else:
                    st.warning("⚠️ 선택하신 조건에 맞는 상품을 찾을 수 없습니다.")
            else:
                st.info("💡 각 항목을 선택해주세요.")
        else:
            st.info("👈 먼저 사이드바에서 Google Sheets 데이터가 로드되길 기다려주세요.")
    
    with col_right:
        st.markdown("### 📍 설치 가능지역 조회")
        
        # 주소 입력 섹션
        col1, col2 = st.columns([4, 1])
        
        with col1:
            address_input = st.text_input(
                "검색할 주소를 입력하세요",
                placeholder="예: 강남구 테헤란로 152",
                key="address"
            )
        
        with col2:
            # 검색 버튼 스타일 (연한 파란색, 작은 크기)
            st.markdown("""
            <style>
            .stButton>button {
                background-color: #87CEEB !important;
                color: white !important;
                border: none !important;
                padding: 0.4rem 1rem !important;
                font-size: 0.9rem !important;
            }
            </style>
            """, unsafe_allow_html=True)
            search_button = st.button("🔍 검색")
        
        # 동 호수 입력 필드
        st.markdown("#### 📝 상세 주소 입력 (선택사항) - 아파트 거주시에만 작성해주세요")
        col3, col4 = st.columns(2)
        
        with col3:
            dong_input = st.text_input(
                "동 (예: 201)",
                placeholder="예: 201",
                key="dong"
            )
        
        with col4:
            ho_input = st.text_input(
                "호수 (예: 101)",
                placeholder="예: 101",
                key="ho"
            )
        
        # 검색 전 안내 메시지
        if address_input and not search_button:
            st.warning("⚠️ **조회 시간 안내**: 주소를 입력하신 후 **검색 버튼을 눌러주세요**. 조회 시간이 10~20초 정도 소요될 수 있습니다. 잠시만 기다려주세요.")
        
        # 검색 결과 표시
        if search_button and address_input:
            st.info("검색 버튼을 눌러주고 잠시만 기다려주세요. 다른 화면이 뜨면 자동으로 꺼지니 기다려주세요~")
            with st.spinner("주소를 검색하는 중입니다..."):
                result = search_address(address_input, dong_input, ho_input)
                
                if result["status"] == "success":
                    st.success(result["message"])
                    
                    if "service_result" in result and result["service_result"]:
                        st.markdown("### 🌐 서비스 가능지역 조회 결과")
                        st.info("📋 아래 화면을 참고하세요")
                        with st.container():
                            st.code(result["service_result"], language=None)
                    
                    # 스크린샷이 있다면 표시
                    if "screenshot" in result and result["screenshot"]:
                        try:
                            st.image(result["screenshot"], caption="검색 결과 스크린샷", width='stretch')
                        except:
                            st.info("검색 결과를 저장했습니다.")
                else:
                    st.error(result["message"])
                    if "screenshot" in result and result["screenshot"]:
                        st.image(result["screenshot"], caption="에러 스크린샷", width='stretch')
                    if "page_preview" in result:
                        with st.expander("페이지 구조 미리보기"):
                            st.code(result["page_preview"])
        
        # 사용법 안내
        with st.expander("📖 사용법"):
            st.markdown("""
            ### 사용 방법
            1. 검색할 주소를 입력하세요 (지번, 도로명, 건물명 가능)
            2. 검색 버튼을 클릭하세요
            3. 자동으로 SK브로드밴드 사이트에서 주소를 검색합니다
            
            ### 지원 기능
            - 주소 자동 입력
            - 검색 버튼 자동 클릭
            - 검색 결과 스크린샷 저장
            """)
        
        # 예시 주소
        st.markdown("### 💡 예시 주소")
        example_addresses = [
            "강남구 테헤란로 152",
            "서울시 종로구 세종대로 1",
            "강원도 춘천시 퇴계로 24"
        ]
        
        for addr in example_addresses:
            if st.button(f"📍 {addr}", key=addr):
                with st.spinner("주소를 검색하는 중입니다..."):
                    result = search_address(addr, None, None)
                    if result["status"] == "success":
                        st.success(result["message"])
                        
                        # 서비스조회 결과만 표시 (인터넷 & BTV)
                        if "service_result" in result and result["service_result"]:
                            st.markdown("### 🌐 서비스 가능지역 조회 결과")
                            st.info("📋 아래 화면을 참고하세요")
                            with st.container():
                                st.code(result["service_result"], language=None)
                        
                        if "screenshot" in result and result["screenshot"]:
                            try:
                                st.image(result["screenshot"], caption="검색 결과 스크린샷", width='stretch')
                            except:
                                st.info("검색 결과를 저장했습니다.")
                    else:
                        st.error(result["message"])
                        if "screenshot" in result and result["screenshot"]:
                            st.image(result["screenshot"], caption="에러 스크린샷", width='stretch')
    
    # 연락처 남기기 섹션
    st.markdown("---")
    st.markdown("## 📞 상담 신청")
    st.markdown("상담을 원하시면 아래 정보를 입력해주세요. 빠른 시일 내에 연락드리겠습니다.")
    
    with st.form("contact_form", clear_on_submit=True):
        col_contact1, col_contact2 = st.columns(2)
        
        with col_contact1:
            contact_name = st.text_input(
                "이름 *",
                placeholder="홍길동",
                help="실명을 입력해주세요"
            )
            
            contact_phone = st.text_input(
                "전화번호 *",
                placeholder="010-1234-5678",
                help="연락 가능한 전화번호를 입력해주세요"
            )
        
        with col_contact2:
            contact_email = st.text_input(
                "이메일",
                placeholder="example@email.com",
                help="이메일 주소 (선택사항)"
            )
            
            contact_time = st.selectbox(
                "통화 가능 시간",
                ["오전 (09:00-12:00)", "오후 (12:00-18:00)", "저녁 (18:00-21:00)", "언제든지"],
                help="통화 가능한 시간대를 선택해주세요"
            )
        
        contact_message = st.text_area(
            "문의 내용",
            placeholder="상담받고 싶은 내용을 자유롭게 작성해주세요",
            height=100,
            help="궁금하신 사항이나 요청사항을 입력해주세요"
        )
        
        # 개인정보 수집 동의
        st.markdown("---")
        st.markdown("### 📋 개인정보 수집 및 이용 동의")
        
        with st.expander("개인정보 수집 및 이용 동의서 전문 보기"):
            st.markdown("""
            **[개인정보 수집 및 이용 동의]**
            
            **1. 수집하는 개인정보 항목**
            - 필수항목: 이름, 전화번호
            - 선택항목: 이메일, 통화 가능 시간, 문의 내용
            
            **2. 개인정보의 수집 및 이용 목적**
            - SK 인터넷 서비스 상담 및 안내
            - 고객 문의 응대 및 서비스 제공
            
            **3. 개인정보의 보유 및 이용 기간**
            - 수집일로부터 6개월
            - 상담 완료 후 별도 요청 시 즉시 파기
            
            **4. 동의를 거부할 권리**
            - 귀하는 개인정보 수집 및 이용에 대한 동의를 거부할 권리가 있습니다.
            - 다만, 동의를 거부할 경우 상담 서비스 이용이 제한될 수 있습니다.
            """)
        
        privacy_consent = st.checkbox(
            "✅ 위 개인정보 수집 및 이용에 동의합니다. (필수)",
            help="개인정보 수집 및 이용에 동의해주셔야 상담 신청이 가능합니다."
        )
        
        # 제출 버튼
        submit_button = st.form_submit_button("📤 상담 신청하기", use_container_width=True)
        
        if submit_button:
            # 입력값 검증
            if not contact_name or not contact_phone:
                st.error("❌ 이름과 전화번호는 필수 입력 항목입니다.")
            elif not privacy_consent:
                st.error("❌ 개인정보 수집 및 이용에 동의해주셔야 상담 신청이 가능합니다.")
            else:
                # 이메일 설정 확인
                if 'smtp_email' not in st.session_state or 'smtp_password' not in st.session_state or 'recipient_email' not in st.session_state:
                    st.error("❌ 이메일 설정이 필요합니다. 사이드바에서 SMTP 설정을 완료해주세요.")
                else:
                    # 문의 내용 구성
                    full_message = f"""
통화 가능 시간: {contact_time}

문의 내용:
{contact_message if contact_message else '(문의 내용 없음)'}
                    """
                    
                    # 이메일 전송
                    with st.spinner("상담 신청을 처리하는 중입니다..."):
                        result = send_contact_email(
                            name=contact_name,
                            phone=contact_phone,
                            email=contact_email if contact_email else "미입력",
                            message=full_message,
                            recipient_email=st.session_state.recipient_email,
                            smtp_email=st.session_state.smtp_email,
                            smtp_password=st.session_state.smtp_password
                        )
                        
                        if result["status"] == "success":
                            st.success("✅ " + result["message"])
                            st.balloons()
                            st.info("담당자가 확인 후 빠른 시일 내에 연락드리겠습니다. 감사합니다! 😊")
                        else:
                            st.error("❌ " + result["message"])


if __name__ == "__main__":
    main()
