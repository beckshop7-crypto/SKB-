import streamlit as st
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time
import re
import pandas as pd
import io
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from datetime import datetime

def search_address(address, dong=None, ho=None):
    """주소 검색을 자동화하는 함수"""
    try:
        # Chrome 드라이버 설정
        options = webdriver.ChromeOptions()
        # options.add_argument('--headless')  # 디버깅을 위해 주석 처리
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # SK브로드밴드 주소 검색 페이지 접속
        url = "https://www.bworld.co.kr/myb/product/join/address/svcAveSearch.do"
        driver.get(url)
        
        # 페이지 로딩 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        time.sleep(2)  # 추가 대기 시간
        
        # 주소 입력창 찾기 및 입력
        try:
            # 주소 입력창 찾기 (여러 가능한 셀렉터 시도)
            input_selectors = [
                "input[name='keyword']",
                "input[type='text'][placeholder*='주소']",
                "input[type='text']",
                "input[placeholder*='지번, 도로명, 건물명']",
                "#keyword",
                ".keyword",
                "input.input-search",
                "#addrInput",
                "input#keyword",
                "input.keyword"
            ]
            
            input_element = None
            found_selector = None
            for selector in input_selectors:
                try:
                    input_element = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if input_element:
                        found_selector = selector
                        break
                except:
                    continue
            
            # 입력창을 찾지 못한 경우 모든 input 요소 나열
            if not input_element:
                try:
                    all_inputs = driver.find_elements(By.TAG_NAME, "input")
                    error_msg = f"주소 입력창을 찾을 수 없습니다. 페이지에 {len(all_inputs)}개의 input 요소가 있습니다."
                    if len(all_inputs) > 0:
                        error_msg += "\n찾은 input 요소들:"
                        for inp in all_inputs[:5]:  # 처음 5개만
                            try:
                                error_msg += f"\n- type={inp.get_attribute('type')}, id={inp.get_attribute('id')}, name={inp.get_attribute('name')}, placeholder={inp.get_attribute('placeholder')}"
                            except:
                                pass
                    
                    screenshot_path = "error_page.png"
                    driver.save_screenshot(screenshot_path)
                    
                    return {
                        "status": "error",
                        "message": error_msg,
                        "screenshot": screenshot_path
                    }
                except:
                    pass
            
            if input_element:
                # 주소 입력
                input_element.clear()
                input_element.send_keys(address)
                time.sleep(0.5)
                
                # Enter 키 전송 또는 조회 버튼 클릭
                try:
                    # 조회 버튼 찾기
                    submit_selectors = [
                        "button.btn-search",
                        "button[type='submit']",
                        ".btn-search",
                        "input[type='submit']",
                        "#searchBtn",
                        "a.btn-search"
                    ]
                    
                    for selector in submit_selectors:
                        try:
                            submit_button = driver.find_element(By.CSS_SELECTOR, selector)
                            submit_button.click()
                            break
                        except:
                            continue
                    else:
                        # 버튼을 찾지 못한 경우 Enter 키 사용
                        input_element.send_keys(Keys.RETURN)
                except Exception as e:
                    input_element.send_keys(Keys.RETURN)
                
                # 결과 대기
                time.sleep(2)
                
                # 검색 결과 추출
                results = []
                try:
                    # 검색 결과 리스트 찾기 (여러 가능한 셀렉터 시도)
                    result_selectors = [
                        ".result-list li",
                        ".search-result li",
                        ".addr-list li",
                        "ul.list-result li",
                        ".result-item",
                        "div[class*='result']",
                        "li[class*='item']"
                    ]
                    
                    first_result_element = None
                    for selector in result_selectors:
                        try:
                            elements = driver.find_elements(By.CSS_SELECTOR, selector)
                            if elements:
                                for elem in elements:
                                    text = elem.text.strip()
                                    if text and len(text) > 0:
                                        results.append(text)
                                        if not first_result_element:
                                            first_result_element = elem
                                if results:
                                    break
                        except:
                            continue
                    
                    # 첫 번째 결과 항목 클릭
                    selected_result = None
                    if first_result_element and len(results) > 0:
                        try:
                            # 첫 번째 항목 클릭
                            first_result_element.click()
                            time.sleep(2)  # 결과 페이지 로딩 대기
                            
                            # 선택된 결과 페이지의 내용 추출
                            try:
                                # 결과 페이지에서 주요 정보 추출
                                result_info = []
                                
                                # 여러 가능한 정보 셀렉터 시도
                                info_selectors = [
                                    ".result-detail",
                                    ".selected-address",
                                    "div[class*='detail']",
                                    "div[class*='result']",
                                    "table",
                                    ".info-table",
                                    ".address-info"
                                ]
                                
                                for info_selector in info_selectors:
                                    try:
                                        info_elements = driver.find_elements(By.CSS_SELECTOR, info_selector)
                                        for info_elem in info_elements:
                                            text = info_elem.text.strip()
                                            if text and len(text) > 10:  # 의미있는 텍스트만
                                                result_info.append(text)
                                        if result_info:
                                            break
                                    except:
                                        continue
                                
                                if result_info:
                                    selected_result = "\n".join(result_info)
                                else:
                                    # 전체 body 텍스트 가져오기
                                    body_text = driver.find_element(By.TAG_NAME, "body").text
                                    selected_result = body_text[:500]  # 처음 500자만
                            except Exception as e:
                                selected_result = f"결과 페이지 로딩 완료 (정보 추출 중 오류: {str(e)})"
                        except Exception as e:
                            selected_result = f"첫 번째 항목 클릭 중 오류: {str(e)}"
                    
                    # 서비스조회 버튼 클릭
                    service_result = None
                    if first_result_element and len(results) > 0:
                        try:
                            # 라디오 버튼 선택 (label[for="radio_01"])
                            radio_selectors = [
                                'label[for="radio_01"]',
                                'label[for=radio_01]',
                                '#radio_01',
                                'input[type="radio"][id="radio_01"]'
                            ]
                            
                            radio_element = None
                            for selector in radio_selectors:
                                try:
                                    radio_element = driver.find_element(By.CSS_SELECTOR, selector)
                                    if radio_element:
                                        radio_element.click()
                                        time.sleep(0.5)
                                        break
                                except:
                                    continue
                            
                            # 서비스조회 버튼 찾기 (div.butn_wrap.event_pop_butn)
                            service_btn_selectors = [
                                'div.butn_wrap.event_pop_butn',
                                'div.butn_wrap.event_pop_butn button',
                                'div.butn_wrap.event_pop_butn a',
                                '.butn_wrap.event_pop_butn',
                                "button:contains('서비스조회')",
                                "a:contains('서비스조회')",
                                "button.btn-service-search",
                                ".btn-search-service"
                            ]
                            
                            service_button = None
                            for selector in service_btn_selectors:
                                try:
                                    if ':contains(' in selector:
                                        # contains 셀렉터는 직접 구현
                                        buttons = driver.find_elements(By.TAG_NAME, "button")
                                        links = driver.find_elements(By.TAG_NAME, "a")
                                        for btn in buttons + links:
                                            if "서비스조회" in btn.text:
                                                service_button = btn
                                                break
                                    else:
                                        service_button = driver.find_element(By.CSS_SELECTOR, selector)
                                    if service_button:
                                        break
                                except:
                                    continue
                            
                            if service_button:
                                service_button.click()
                                time.sleep(2)  # 서비스조회 결과 대기
                                
                                # 팝업 확인 버튼 클릭 (존재하는 경우)
                                try:
                                    popup_confirm = driver.find_element(By.CSS_SELECTOR, 'div.butn_wrap a.modal_close.modal_confirm_btn')
                                    if popup_confirm:
                                        popup_confirm.click()
                                        time.sleep(1)
                                        
                                        # 동 선택 버튼 클릭 (button#input_Id3)
                                        try:
                                            # 동 선택 버튼 찾기 및 클릭
                                            dong_button = WebDriverWait(driver, 5).until(
                                                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button#input_Id3'))
                                            )
                                            dong_button.click()
                                            time.sleep(0.8)  # 드롭다운 열리기 대기
                                            
                                            # 동 입력값이 있으면 해당 값을 가진 버튼 선택, 없으면 첫 번째 선택
                                            if dong:
                                                # 드롭다운 리스트가 보일 때까지 대기
                                                WebDriverWait(driver, 10).until(
                                                    EC.presence_of_element_located((By.CSS_SELECTOR, 'ul#dongSelectList'))
                                                )
                                                time.sleep(0.5)  # 추가 대기
                                                
                                                # 모든 동 옵션 가져오기
                                                dong_options = driver.find_elements(By.CSS_SELECTOR, 'ul#dongSelectList li button')
                                                
                                                matched = False
                                                for option in dong_options:
                                                    try:
                                                        option_text = option.text.strip()
                                                        option_onclick = option.get_attribute('onclick')
                                                        
                                                        # 근사값 매칭 (유사한 정보도 매칭)
                                                        # 1. 텍스트가 정확히 일치
                                                        # 2. 포함 검사 (양방향)
                                                        # 3. 숫자 매칭
                                                        dong_digits = ''.join(re.findall(r'\d+', dong))
                                                        option_digits = ''.join(re.findall(r'\d+', option_text))
                                                        dong_numbers = re.findall(r'\d+', dong)
                                                        option_numbers = re.findall(r'\d+', option_text)
                                                        
                                                        if (option_text == dong or 
                                                            dong in option_text or 
                                                            option_text in dong or 
                                                            dong_digits == option_digits or
                                                            (dong_numbers and option_numbers and any(num in option_numbers for num in dong_numbers))):
                                                            # JavaScript로 클릭 (더 안정적)
                                                            driver.execute_script("arguments[0].click();", option)
                                                            matched = True
                                                            time.sleep(2)  # 호 데이터 로딩 대기
                                                            break
                                                    except:
                                                        continue
                                                
                                                if not matched:
                                                    # 매칭 실패 시 첫 번째 항목 선택
                                                    try:
                                                        first_dong_option = driver.find_element(By.CSS_SELECTOR, 'ul#dongSelectList li:first-child button')
                                                        driver.execute_script("arguments[0].click();", first_dong_option)
                                                        time.sleep(2)
                                                    except:
                                                        pass
                                            else:
                                                # 첫 번째 항목 선택
                                                try:
                                                    first_dong_option = driver.find_element(By.CSS_SELECTOR, 'ul#dongSelectList li:first-child button')
                                                    driver.execute_script("arguments[0].click();", first_dong_option)
                                                    time.sleep(2)
                                                except:
                                                    pass
                                        except Exception as e:
                                            pass  # 동 선택 실패 시 계속 진행
                                        
                                        # 호 선택 버튼 클릭 (button#input_Id4)
                                        try:
                                            ho_button = driver.find_element(By.CSS_SELECTOR, 'button#input_Id4')
                                            if ho_button:
                                                ho_button.click()
                                                time.sleep(0.8)  # 드롭다운 열리기 대기
                                                
                                                # 호수 입력값이 있으면 해당 값을 가진 버튼 선택, 없으면 첫 번째 선택
                                                if ho:
                                                    # 커스텀 셀렉트박스 처리
                                                    WebDriverWait(driver, 10).until(
                                                        EC.presence_of_element_located((By.CSS_SELECTOR, 'ul#hoSelectList'))
                                                    )
                                                    time.sleep(0.5)  # 추가 대기
                                                    
                                                    ho_options = driver.find_elements(By.CSS_SELECTOR, 'ul#hoSelectList li button')
                                                    
                                                    matched = False
                                                    for option in ho_options:
                                                        try:
                                                            option_text = option.text.strip()
                                                            option_data_value = option.get_attribute('data-value')
                                                            
                                                            # 근사값 매칭 (유사한 정보도 매칭)
                                                            # 1. 텍스트가 정확히 일치
                                                            # 2. 포함 검사 (양방향)
                                                            # 3. 숫자 매칭
                                                            ho_digits = ''.join(re.findall(r'\d+', ho))
                                                            option_digits = ''.join(re.findall(r'\d+', option_text))
                                                            ho_numbers = re.findall(r'\d+', ho)
                                                            option_numbers = re.findall(r'\d+', option_text)
                                                            
                                                            if (option_text == ho or 
                                                                ho in option_text or 
                                                                option_text in ho or 
                                                                ho_digits == option_digits or
                                                                (ho_numbers and option_numbers and any(num in option_numbers for num in ho_numbers))):
                                                                # JavaScript로 클릭 (더 안정적)
                                                                driver.execute_script("arguments[0].click();", option)
                                                                matched = True
                                                                time.sleep(1)
                                                                break
                                                        except:
                                                            continue
                                                    
                                                    if not matched:
                                                        # 매칭 실패 시 첫 번째 항목 선택
                                                        try:
                                                            first_ho_option = driver.find_element(By.CSS_SELECTOR, 'ul#hoSelectList li:first-child button')
                                                            driver.execute_script("arguments[0].click();", first_ho_option)
                                                            time.sleep(1)
                                                        except:
                                                            pass
                                                else:
                                                    # 첫 번째 항목 선택
                                                    try:
                                                        first_ho_option = driver.find_element(By.CSS_SELECTOR, 'ul#hoSelectList li:first-child button')
                                                        driver.execute_script("arguments[0].click();", first_ho_option)
                                                        time.sleep(1)
                                                    except:
                                                        pass
                                        except Exception as e:
                                            pass  # 호 선택 실패 시 계속 진행
                                        
                                        # 서비스 조회 버튼 클릭 (button#GA_CY_MENU_C00000001)
                                        try:
                                            service_query_btn = driver.find_element(By.CSS_SELECTOR, 'button#GA_CY_MENU_C00000001')
                                            if service_query_btn:
                                                service_query_btn.click()
                                                time.sleep(2)  # 서비스 조회 결과 대기
                                        except:
                                            pass
                                except:
                                    pass  # 팝업이 있다면 클릭, 없으면 무시
                                
                                # 서비스조회 결과 추출
                                try:
                                    service_info = []
                                    
                                    # 서비스 정보 셀렉터
                                    service_selectors = [
                                        ".service-result",
                                        ".service-info",
                                        ".result-table",
                                        "table",
                                        "div[class*='service']",
                                        "div[class*='result']",
                                        ".service-list",
                                        ".avail-service"
                                    ]
                                    
                                    for service_selector in service_selectors:
                                        try:
                                            service_elements = driver.find_elements(By.CSS_SELECTOR, service_selector)
                                            for service_elem in service_elements:
                                                text = service_elem.text.strip()
                                                if text and len(text) > 10:
                                                        service_info.append(text)
                                        except:
                                            continue
                                    
                                    if service_info:
                                        service_result = "\n".join(service_info)
                                    else:
                                        # 전체 페이지 텍스트 가져오기
                                        body_text = driver.find_element(By.TAG_NAME, "body").text
                                    
                                    # 인터넷과 BTV 관련 정보만 추출
                                    if body_text:
                                        internet_info = []
                                        btv_info = []
                                        lines = body_text.split('\n')
                                        
                                        for i, line in enumerate(lines):
                                            line = line.strip()
                                            # 인터넷 관련 정보 추출
                                            if '인터넷' in line or 'Internet' in line or '인터' in line:
                                                # 다음 몇 줄도 포함 (요금제 정보 등)
                                                context = [line]
                                                for j in range(1, 3):
                                                    if i + j < len(lines):
                                                        context.append(lines[i + j].strip())
                                                internet_info.append(' '.join(context[:100]))  # 최대 100자
                                            
                                            # BTV 관련 정보 추출
                                            if 'B tv' in line or 'BTV' in line or '비티비' in line or 'IPTV' in line:
                                                context = [line]
                                                for j in range(1, 3):
                                                    if i + j < len(lines):
                                                        context.append(lines[i + j].strip())
                                                btv_info.append(' '.join(context[:100]))
                                        
                                        # 결과 구성
                                        result_lines = []
                                        if internet_info:
                                            result_lines.append("📶 인터넷 서비스:")
                                            result_lines.extend(internet_info[:3])  # 최대 3개 항목
                                        if btv_info:
                                            result_lines.append("\n📺 B tv 서비스:")
                                            result_lines.extend(btv_info[:3])  # 최대 3개 항목
                                        
                                        if result_lines:
                                            service_result = '\n'.join(result_lines)
                                        else:
                                            service_result = "인터넷 및 BTV 서비스 정보를 찾을 수 없습니다."
                                    else:
                                        service_result = body_text[:1000] if body_text else "결과 없음"
                                except Exception as e:
                                    service_result = None  # 오류 발생 시 표시하지 않음
                            else:
                                service_result = None  # 버튼을 찾지 못한 경우 표시하지 않음
                        except Exception as e:
                            service_result = None  # 오류 발생 시 표시하지 않음
                    
                    # 결과를 찾지 못한 경우 페이지의 모든 텍스트 확인
                    if not results:
                        try:
                            # 페이지 스크린샷 저장
                            screenshot_path = "search_result.png"
                            driver.save_screenshot(screenshot_path)
                            
                            # 페이지 소스에서 검색 결과 유사 패턴 찾기
                            page_text = driver.find_element(By.TAG_NAME, "body").text
                            results.append(f"검색이 완료되었습니다. 총 {len(page_text)}개의 문자가 검색되었습니다.")
                        except Exception as e:
                            results.append(f"검색 완료 (상세 정보 추출 실패: {str(e)})")
                    
                except Exception as e:
                    results.append(f"검색 완료 (결과 파싱 오류: {str(e)})")
                
                # 스크린샷 저장 (선택된 결과 페이지)
                try:
                    screenshot_path = "search_result.png"
                    driver.save_screenshot(screenshot_path)
                except:
                    screenshot_path = None
                
                return {
                    "status": "success",
                    "message": f"주소 검색이 완료되었습니다. {len(results)}개의 결과를 찾았습니다." + 
                               (f"\n첫 번째 항목이 자동으로 선택되었습니다." if selected_result else "") +
                               (f"\n서비스조회가 완료되었습니다." if service_result else ""),
                    "results": results,
                    "selected_result": selected_result,
                    "service_result": service_result,
                    "screenshot": screenshot_path
                }
            else:
                return {
                    "status": "error",
                    "message": "주소 입력창을 찾을 수 없습니다."
                }
                
        except Exception as e:
            # 현재 페이지의 HTML 구조 확인용
            page_source = driver.page_source[:1000]
            return {
                "status": "error",
                "message": f"주소 검색 중 오류 발생: {str(e)}",
                "page_preview": page_source
            }
        finally:
            time.sleep(1)
            driver.quit()
            
    except Exception as e:
        return {
            "status": "error",
            "message": f"브라우저 실행 중 오류 발생: {str(e)}"
        }


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
    
    # 사이드바 - 엑셀 파일 업로드 및 이메일 설정
    with st.sidebar:
        st.header("📂 파일 관리")
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
                
        # 파일 초기화 버튼
        if st.button("🗑️ 파일 초기화"):
            for key in ['excel_data', 'uploaded_file_name', 'selections']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
        
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
    st.markdown("사이드바에서 엑셀 파일을 업로드한 후 상품 조건을 선택하면, 선택 결과를 요약해 보여드립니다.")
    
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
            st.info("👈 먼저 사이드바에서 엑셀 파일을 업로드해주세요.")
    
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
