import os
import shutil
# 導入 PDF 與 Word 解析套件
import pypdf
from docx import Document
# 導入 Google GenAI SDK
from google import genai

# 初始化 Gemini 客戶端（執行時會自動偵測環境變數中的 GEMINI_API_KEY）
client = genai.Client()

SOURCE_DIR = "./unread_files"
TARGET_DIR = "./classified_knowledge_base"

CATEGORIES = [
    "01_Teaching_Materials",      # 課程、教材、資管教學
    "02_Research_Projects",       # 論文、研究、AI工作流、RAG架構
    "03_Corporate_Governance",    # 董事會、股東、資本額、公司治理
    "04_Financial_Invoices",      # 發票、收據、報帳經費
    "05_Unclassified"             # 無法判定的其他檔案
]

def extract_text_from_pdf(file_path: str) -> str:
    """從 PDF 檔案中提取所有文字特徵"""
    text = ""
    try:
        reader = pypdf.PdfReader(file_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    except Exception as e:
        print(f"❌ 讀取 PDF 失敗 ({os.path.basename(file_path)}): {e}")
    return text

def extract_text_from_docx(file_path: str) -> str:
    """從 Word (.docx) 檔案中提取所有文字特徵"""
    text = ""
    try:
        doc = Document(file_path)
        for paragraph in doc.paragraphs:
            if paragraph.text:
                text += paragraph.text + "\n"
    except Exception as e:
        print(f"❌ 讀取 Word 失敗 ({os.path.basename(file_path)}): {e}")
    return text

def ask_gemini_to_classify(file_content: str) -> str:
    """將提取出的文本內容丟給 Gemini 進行語意分析與歸類"""
    # 為了節省 Token 並避免文本過長，限制只抓取檔案前 4000 個字進行特徵分析
    preview_content = file_content[:4000]
    
    prompt = f"""
    你是一個高效率的檔案管理專家。請分析以下文件的內容，並從規定的分類列表中，選擇一個最適合該文件的分類名稱。
    
    【規定的分類列表】:
    {", ".join(CATEGORIES)}
    
    【注意事宜】:
    1. 只能回傳列表中的其中一個分類名稱，絕對不要包含任何解釋、標點符號或額外文字。
    2. 如果無法確定，請分類為 "05_Unclassified"。
    
    【待分析文件內容摘要】:
    {preview_content}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        result = response.text.strip()
        return result if result in CATEGORIES else "05_Unclassified"
    except Exception as e:
        print(f"🤖 Gemini API 呼叫失敗: {e}")
        return "05_Unclassified"

def analyze_and_classify_all_formats():
    if not os.path.exists(SOURCE_DIR):
        print(f"請先建立來源資料夾 '{SOURCE_DIR}'。")
        return

    files = [f for f in os.listdir(SOURCE_DIR) if os.path.isfile(os.path.join(SOURCE_DIR, f))]
    
    for file_name in files:
        file_path = os.path.join(SOURCE_DIR, file_name)
        file_extension = os.path.splitext(file_name)[1].lower()
        file_content = ""
        
        # 根據不同的擴充副檔名，導入不同的特徵提取模組
        if file_extension == '.txt':
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
            except UnicodeDecodeError:
                # 處理可能的編碼問題
                with open(file_path, 'r', encoding='big5', errors='ignore') as f:
                    file_content = f.read()
        elif file_extension == '.pdf':
            print(f"📄 正在解析 PDF 檔案文字: {file_name}...")
            file_content = extract_text_from_pdf(file_path)
        elif file_extension == '.docx':
            print(f"📝 正在解析 Word 檔案文字: {file_name}...")
            file_content = extract_text_from_docx(file_path)
        else:
            print(f"⏭️ 不支援的檔案格式（略過）: {file_name}")
            continue

        # 如果成功提取到文字，就交給 AI 處理
        if file_content.strip():
            print(f"🧠 正在透過 Gemini AI 分析語意...")
            matched_folder = ask_gemini_to_classify(file_content)
            
            dest_folder_path = os.path.join(TARGET_DIR, matched_folder)
            if not os.path.exists(dest_folder_path):
                os.makedirs(dest_folder_path)
                
            shutil.move(file_path, os.path.join(dest_folder_path, file_name))
            print(f"🎯 歸類完成: [{file_name}] -> 移至 [{matched_folder}]\n")
        else:
            print(f"⚠️ 無法從檔案 [{file_name}] 中提取有效文字，跳過分類。\n")

if __name__ == "__main__":
    print("=== 啟動多格式 AI 智慧檔案歸類系統 ===")
    analyze_and_classify_all_formats()
    print("=== 分類程序結束 ===")
