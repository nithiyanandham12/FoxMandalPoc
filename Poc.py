import streamlit as st
from PyPDF2 import PdfReader
import docx2txt
import requests
from deep_translator import MyMemoryTranslator
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
import pypandoc  # NEW
from dotenv import load_dotenv 

load_dotenv()



# CONFIG
API_KEY = os.getenv("API_KEY")
PROJECT_ID = os.getenv("PROJECT_ID")

Prompt1='''You are a senior legal associate preparing a professional Title Report for a land parcel based on the input text provided below.

Generate the entire output in Markdown format, using tables wherever possible and adhering to the structure, language, and formatting standards followed by leading legal firms (e.g., Fox Mandal & Associates).

Ensure the tone is formal, precise, and legal in nature. The structure must be clear, easy to navigate, and all relevant data must be presented in organized, labeled tables.

📋 OUTPUT FORMAT REQUIREMENTS
Follow the structure below exactly. Use bold section titles, tables with borders (Markdown-style), bullet points where specified, and maintain uniform formatting throughout.

Header
Centered title: # Report On Title

Add a confidentiality note and client-specific info:


*Confidential | Not for Circulation*  
*Prepared exclusively for [Client Name]*  
I. DESCRIPTION OF THE LANDS
Use a Markdown table:

Survey No.	Extent	A-Kharab	Village	Taluk	District
II. LIST OF DOCUMENTS REVIEWED
Markdown table format:

Sl. No.	Document Description	Date / Document No.	Issuing Authority
III. DEVOLUTION OF TITLE
Begin with a timeline-style table:

Period	Title Holder(s)	Nature of Right / Document Basis
IV. ENCUMBRANCE CERTIFICATE
One separate table per time period (e.g., 2000–2010, 2011–2020, etc.):

Period	Document Description	Encumbrance Type	Remarks
V. OTHER OBSERVATIONS (Boundaries and Zoning Info)
Use a Markdown table format:

Direction	Boundary Details
East	
West	
North	
South	
VI. INDEPENDENT VERIFICATIONS
Bullet points only:

Verified Sub-Registrar records for document authenticity.

Checked Revenue Department land mutation and RTC extracts.

VII. LITIGATION SEARCH RESULTS
Bullet points:

Search conducted with [Advocate Name] on [Date].

No active litigation found / Pending civil suit in [Court Name].

VIII. SPECIAL CATEGORY LANDS
Use a simple table:

Category	Status
SC/ST	Yes/No
Minor	Yes/No
Inam	Yes/No
Grant Land	Yes/No
IX. OPINION AND RECOMMENDATION
Paragraph summary (formal legal tone).

Followed by a table listing owners and co-signatories:

Name of Owner / Co-signatory	Type of Right / Share
X. CONTACT DETAILS
Use standard formatting:


Prepared By: [Full Name]  
Designation: Legal Associate  
Firm: Fox Mandal & Associates  
Phone: [Phone Number]  
Email: [Email Address]  
✅ Instructions Summary

Ensure all section headings are bold (## Heading in Markdown).

Use tables for any data or list format.

Avoid plain text lists where tables can be applied.

Maintain a formal legal tone throughout.

'''

def extract_text_pages(file):
    text_by_page = {}
    if file.name.endswith(".pdf"):
        reader = PdfReader(file)
        for i, page in enumerate(reader.pages):
            content = page.extract_text()
            if content:
                text_by_page[f"Page {i + 1}"] = content
    elif file.name.endswith(".docx"):
        full_text = docx2txt.process(file)
        text_by_page["Page 1"] = full_text
    elif file.name.endswith(".txt"):
        text_by_page["Page 1"] = file.read().decode("utf-8")
    else:
        text_by_page["Error"] = "Unsupported file type."
    return text_by_page


# Add this import
from googletrans import Translator

# Replace this function
def translate_pages(pages_dict):
    translated = {}
    translator = Translator()
    for page, text in pages_dict.items():
        try:
            translated[page] = translator.translate(text, src='kn', dest='en').text
        except Exception as e:
            translated[page] = f"[Translation failed: {str(e)}]"
    return translated

def chunk_pages(translated_dict, chunk_size=15):
    pages = list(translated_dict.items())
    return [dict(pages[i:i + chunk_size]) for i in range(0, len(pages), chunk_size)]



def get_ibm_access_token(api_key):
    url = "https://iam.cloud.ibm.com/identity/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
        "apikey": api_key
    }
    response = requests.post(url, headers=headers, data=data)
    return response.json()["access_token"]


def send_chunk_to_watsonx(chunk_text, access_token):
    url = "https://us-south.ml.cloud.ibm.com/ml/v1/text/generation?version=2024-01-15"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    prompt = "<|start_of_role|>system<|end_of_role|>You are Granite, an AI language model developed by IBM in 2024. You are a cautious assistant. You carefully follow instructions. You are helpful and harmless and you follow ethical guidelines and promote positive behavior.<|end_of_text|>\n<|start_of_role|>assistant<|end_of_role|>"
    
    payload = {
        "input": Prompt1 + chunk_text,
        "parameters": {
            "decoding_method": "greedy",
            "max_new_tokens": 8100,
            "min_new_tokens": 0,
            "stop_sequences": [],
            "repetition_penalty": 1
        },
        "model_id": "meta-llama/llama-3-3-70b-instruct",
        "project_id": PROJECT_ID
    }

    response = requests.post(url, headers=headers, json=payload)

    try:
        result = response.json()
        return result["results"][0]["generated_text"]
    except Exception as e:
        return f"[Watsonx response error: {str(e)} - Raw: {response.text}]"
    



# ✅ NEW FUNCTION: Markdown to Word
import pypandoc
pypandoc.download_pandoc()

def save_to_word_from_markdown(markdown_text, upload_file_name):
    import pypandoc
    pypandoc.download_pandoc()  # ✅ Automatically downloads and sets up pandoc

    base_name = os.path.splitext(upload_file_name)[0]
    file_name = f"{base_name} AI Summary.docx"
    output_path = os.path.join(os.getcwd(), file_name)

    pypandoc.convert_text(markdown_text, 'docx', format='md', outputfile=output_path)
    return output_path



# 🔥 Streamlit UI Starts
st.set_page_config(page_title="FOX MADEL POC", layout="wide")
st.title("📄 FOX MANDEL POC")

uploaded_file = st.file_uploader("📄 Upload OCR Output File (.pdf, .txt, .docx)", type=["pdf", "txt", "docx"])

if uploaded_file:
    with st.spinner("📄 Extracting text by page..."):
        raw_pages = extract_text_pages(uploaded_file)

    with st.spinner("🌐 Translating all pages to English..."):
        translated_pages = translate_pages(raw_pages)

    try:
        with st.spinner("🔐 Getting IBM token..."):
            token = get_ibm_access_token(API_KEY)

        chunks = chunk_pages(translated_pages, chunk_size=90)
        watsonx_outputs = []

        for i, chunk in enumerate(chunks):
            chunk_text = "\n".join(chunk.values())
            with st.spinner(f"🤖 Sending Chunk {i + 1} of {len(chunks)} to Watsonx..."):
                result = send_chunk_to_watsonx(chunk_text, token)
                watsonx_outputs.append(result)

        final_output = "\n\n".join(watsonx_outputs)
        st.subheader("📝 Consolidated Watsonx Output")
        st.write(final_output)

        # Save to Word from Markdown
        if "word_generated" not in st.session_state:
            with st.spinner("🧾 Generating Word document from Markdown..."):
                word_path = save_to_word_from_markdown(final_output, uploaded_file.name)
                st.session_state.word_generated = True
                st.session_state.word_path = word_path

        if "word_path" in st.session_state:
            with open(st.session_state.word_path, "rb") as f:
                st.download_button("📥 Download Word Document", f, file_name=os.path.basename(st.session_state.word_path))

    except Exception as e:
        st.error(f"❌ Error: {e}")