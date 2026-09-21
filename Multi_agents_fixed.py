
import os
import re
import sys
import time
import random
import warnings
import subprocess
import tempfile
from typing import TypedDict, List, Any

import streamlit as st

# ==============================================================================
# STREAMLIT SAYFA YAPILANDIRMASI (MUTLAKA EN BAŞTA OLMALI)
# ==============================================================================
st.set_page_config(page_title="Multi-Agent Python Coder", page_icon="🤖", layout="wide")

# Otomatik fonksiyon çağırma (AFC) ve deprecation uyarılarını gizle
warnings.filterwarnings("ignore")

# ==============================================================================
# 0. .ENV DOSYASI DESTEĞİ
# ==============================================================================
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END

# ==============================================================================
# 1. KONFİGÜRASYON VE API ANAHTARI AYARLARI
# ==============================================================================
# Eğer ortam değişkeninde API anahtarı yoksa st.secrets veya manuel tanım kullanılır
MY_API_KEY = os.getenv("GOOGLE_API_KEY")

MODEL_NAME = "gemini-3.6-flash"
FALLBACK_MODEL_NAME = "gemini-3.5-flash-lite"  # Ana model kota/hata verirse devreye girer

if MY_API_KEY:
    os.environ["GOOGLE_API_KEY"] = MY_API_KEY

# ==============================================================================
# 1B. LANGSMITH (İZLENEBİLİRLİK) AYARLARI
# ==============================================================================
_langsmith_key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
if _langsmith_key:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGCHAIN_PROJECT", "multi-agent-coder"))
    os.environ.setdefault("LANGCHAIN_API_KEY", _langsmith_key)

# ==============================================================================
# 2. MODEL VE VEKTÖR VERİTABANI (RAG) KURULUMU
# ==============================================================================
@st.cache_resource
def get_llm_models():
    primary = ChatGoogleGenerativeAI(model=MODEL_NAME)
    fallback = ChatGoogleGenerativeAI(model=FALLBACK_MODEL_NAME)
    return primary, fallback

llm, fallback_llm = get_llm_models()

_active_model = {"which": "primary"}

@st.cache_resource
def get_vector_db():
    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
    return Chroma(
        collection_name="agent_error_memory",
        embedding_function=embeddings,
        persist_directory="./rag_memory_db"
    )

vector_db = get_vector_db()

# Graph Durumu (State)
class AgentState(TypedDict):
    task: str          # Kullanıcının istediği görev
    plan: str          # Planner'ın hazırladığı mimari plan
    code: str          # Coder'ın yazdığı kod
    error: str         # Varsa test/hata mesajı
    rag_context: str   # RAG hafızasından gelen benzer hata ve çözümler
    iterations: int    # Deneme sayısı
    status: str        # "SUCCESS" veya "RETRY"

# ==============================================================================
# 3. TOOL / FUNCTION CALLING: SANDBOX KOD ÇALIŞTIRMA ARACI
# ==============================================================================
@tool
def run_python_sandbox(code: str) -> str:
    """Verilen Python kodunu izole bir alt süreçte gerçekten çalıştırır ve sonucu döndürür."""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            temp_path = f.name

        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode == 0:
            return f"BAŞARILI\nSTDOUT:\n{result.stdout}"
        else:
            return (
                f"HATA (returncode={result.returncode})\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )
    except subprocess.TimeoutExpired:
        return "HATA: Kod 15 saniye içinde tamamlanamadı (timeout - sonsuz döngü olabilir)."
    except Exception as e:
        return f"HATA: Sandbox çalıştırma sırasında beklenmeyen hata: {type(e).__name__}: {e}"
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

# ==============================================================================
# 4. RATE-LIMIT DESTEKLİ LLM ÇAĞRISI
# ==============================================================================
def is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc)
    return (
        "429" in msg
        or "RESOURCE_EXHAUSTED" in msg
        or "RateLimitError" in type(exc).__name__
        or "quota" in msg.lower()
    )

def is_daily_quota_error(exc: Exception) -> bool:
    msg = str(exc)
    return "PerDay" in msg or "per_day" in msg.lower()

def extract_retry_delay(exc: Exception, default: float = 10.0) -> float:
    match = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", str(exc))
    if match:
        return float(match.group(1))
    return default

class _DailyQuotaExceeded(Exception):
    def __init__(self, model_label: str, original: Exception, note: str = ""):
        self.model_label = model_label
        self.original = original
        self.note = note
        super().__init__(f"{model_label} kullanılamıyor: {note or str(original)}")

def _invoke_with_backoff(client: Any, model_label: str, messages: List[BaseMessage], max_retries: int) -> Any:
    attempt = 0
    while True:
        try:
            return client.invoke(messages)
        except Exception as e:
            if not is_rate_limit_error(e):
                raise

            if is_daily_quota_error(e):
                raise _DailyQuotaExceeded(model_label, e) from e

            attempt += 1
            if attempt > max_retries:
                raise _DailyQuotaExceeded(
                    model_label, e,
                    note=f"{max_retries} deneme sonrasında rate-limit hatası devam etti."
                ) from e

            wait_time = extract_retry_delay(e) + random.uniform(0.5, 2.0)
            wait_time = wait_time * (1.5 ** (attempt - 1))
            time.sleep(wait_time)

def safe_invoke(messages: List[BaseMessage], max_retries: int = 5, tools: list = None) -> Any:
    primary_client = llm.bind_tools(tools) if tools else llm
    fallback_client = fallback_llm.bind_tools(tools) if tools else fallback_llm

    if _active_model["which"] == "fallback":
        try:
            return _invoke_with_backoff(fallback_client, FALLBACK_MODEL_NAME, messages, max_retries)
        except _DailyQuotaExceeded as e:
            raise RuntimeError(f"🚫 Hem ana model ({MODEL_NAME}) hem de yedek model ({FALLBACK_MODEL_NAME}) kullanılamıyor. Son hata: {e}") from e.original

    try:
        return _invoke_with_backoff(primary_client, MODEL_NAME, messages, max_retries)
    except _DailyQuotaExceeded as primary_error:
        _active_model["which"] = "fallback"
        try:
            return _invoke_with_backoff(fallback_client, FALLBACK_MODEL_NAME, messages, max_retries)
        except _DailyQuotaExceeded as fallback_error:
            raise RuntimeError(
                f"🚫 Hem ana model ({MODEL_NAME}) hem de yedek model ({FALLBACK_MODEL_NAME}) kullanılamıyor.\n"
                f"Ana model hatası: {primary_error.original}\n"
                f"Yedek model hatası: {fallback_error.original}"
            ) from fallback_error.original

# ==============================================================================
# 5. RAG BELLEK FONKSİYONLARI
# ==============================================================================
def query_memory(query_text: str) -> str:
    try:
        results = vector_db.similarity_search(query_text, k=2)
        if results:
            context = "\n---\n".join([doc.page_content for doc in results])
            return f"\nGEÇMİŞ HATA TECRÜBELERİ (RAG MEMORY):\n{context}\n"
    except Exception as e:
        pass
    return ""

def save_error_to_memory(task: str, code: str, error: str):
    try:
        doc_content = f"Görev: {task}\nHatalı Kod:\n{code}\nAlınan Hata: {error}"
        doc = Document(page_content=doc_content, metadata={"type": "error_log"})
        vector_db.add_documents([doc])
    except Exception as e:
        pass

# ==============================================================================
# 6. MULTI-AGENT DÜĞÜMLERİ (NODES)
# ==============================================================================
def planner_agent(state: AgentState) -> dict:
    task = state["task"]
    prompt = f"""
    Aşağıdaki görev için adım adım bir Python uygulama planı (mimari) oluştur:
    GÖREV: {task}

    Lütfen kod yazma, sadece mantıksal adımları ve dikkat edilmesi gereken uç durumları (edge-cases) listele.
    Özellikle Python'da bool tipinin int alt sınıfı olduğunu ve type(x) is bool veya not isinstance(x, bool) kontrolü yapılması gerektiğini unutma.
    """
    response = safe_invoke([
        SystemMessage(content="Sen uzman bir yazılım mimarısın."),
        HumanMessage(content=prompt)
    ])
    return {"plan": str(response.content)}

def coder_agent(state: AgentState) -> dict:
    current_iteration = state.get("iterations", 0) + 1
    task = state["task"]
    plan = state.get("plan", "")
    error = state.get("error", "")
    code = state.get("code", "")
    rag_context = query_memory(f"{task} {error}")

    if error:
        prompt = f"""
        Yazdığın Python kodunda hata oluştu!
        GÖREV: {task}
        MİMARİ PLAN: {plan}
        HATALI KOD:\n{code}
        ALINAN HATA MESAJI:\n{error}
        {rag_context}
        Lütfen hatayı düzelt. SADECE çalışan Python kodunu ```python ... ``` bloğu içinde döndür.
        """
    else:
        prompt = f"""
        Şu görev için temiz, verimli Python kodu yaz:
        GÖREV: {task}
        MİMARİ PLAN: {plan}
        {rag_context}
        SADECE Python kodunu ```python ... ``` bloğu içinde ver.
        """

    system_msg = SystemMessage(content=(
        "Sen uzman bir Python geliştiricisisin. 'run_python_sandbox' adında bir aracın var. "
        "Kodunu finalize etmeden önce bu aracı kullanarak test et. Son cevabında SADECE nihai Python kodunu "
        "```python ... ``` bloğu içinde ver."
    ))

    messages: List[BaseMessage] = [system_msg, HumanMessage(content=prompt)]
    tools = [run_python_sandbox]

    response = safe_invoke(messages, tools=tools)

    loop_count = 0
    while getattr(response, "tool_calls", None) and loop_count < 3:
        messages.append(response)
        for tool_call in response.tool_calls:
            if tool_call["name"] == "run_python_sandbox":
                tool_result = run_python_sandbox.invoke(tool_call["args"])
            else:
                tool_result = f"Bilinmeyen araç: {tool_call['name']}"
            messages.append(ToolMessage(content=tool_result, tool_call_id=tool_call["id"]))

        response = safe_invoke(messages, tools=tools)
        loop_count += 1

    raw_content = response.content
    if isinstance(raw_content, list):
        code_str = "".join([chunk.get("text", str(chunk)) if isinstance(chunk, dict) else str(chunk) for chunk in raw_content])
    else:
        code_str = str(raw_content)

    return {
        "code": code_str,
        "rag_context": rag_context,
        "iterations": current_iteration,
    }

def tester_agent(state: AgentState) -> dict:
    raw_code = state.get("code", "")
    if not isinstance(raw_code, str):
        raw_code = str(raw_code)

    code_match = re.search(r"```python\s*(.*?)\s*```", raw_code, re.DOTALL)
    clean_code = code_match.group(1).strip() if code_match else raw_code.replace("```", "").strip()

    tool_output = run_python_sandbox.invoke({"code": clean_code})

    if tool_output.startswith("BAŞARILI"):
        return {
            "code": clean_code,
            "error": "",
            "status": "SUCCESS",
        }
    else:
        error_msg = tool_output
        save_error_to_memory(state["task"], clean_code, error_msg)
        return {
            "code": clean_code,
            "error": error_msg,
            "status": "RETRY",
        }

def refactor_agent(state: AgentState) -> dict:
    code = state["code"]
    prompt = f"""
    Aşağıdaki çalışan Python kodunu incele:
    1. PEP-8 kurallarına tam uyumlu hale getir.
    2. Tip ipuçları (Type Hints) ve açıklayıcı Docstring ekle.
    3. Kodun mantığını VE 'assert' ifadelerini kesinlikle bozma.
    KOD:\n{code}
    SADECE nihai Python kodunu ```python ... ``` bloğu içinde döndür.
    """

    response = safe_invoke([
        SystemMessage(content="Sen PEP-8 ve kod kalitesi konusunda uzman bir Python Refactoring ajanısın."),
        HumanMessage(content=prompt)
    ])

    raw_content = response.content
    refactored_code = "".join([chunk.get("text", str(chunk)) if isinstance(chunk, dict) else str(chunk) for chunk in raw_content]) if isinstance(raw_content, list) else str(raw_content)

    code_match = re.search(r"```python\s*(.*?)\s*```", refactored_code, re.DOTALL)
    final_code = code_match.group(1).strip() if code_match else refactored_code.replace("```", "").strip()

    verify_output = run_python_sandbox.invoke({"code": final_code})
    if verify_output.startswith("BAŞARILI"):
        return {"code": final_code}
    else:
        return {"code": code}

# ==============================================================================
# 7. AKIŞ VE GRAFİK YAPILANDIRMASI (LANGGRAPH)
# ==============================================================================
def should_continue(state: AgentState) -> str:
    if state.get("status") == "SUCCESS":
        return "refactor"
    if state.get("iterations", 0) >= 3:
        return "end"
    return "retry"

workflow = StateGraph(AgentState)
workflow.add_node("planner", planner_agent)
workflow.add_node("coder", coder_agent)
workflow.add_node("tester", tester_agent)
workflow.add_node("refactor", refactor_agent)

workflow.set_entry_point("planner")
workflow.add_edge("planner", "coder")
workflow.add_edge("coder", "tester")

workflow.add_conditional_edges(
    "tester",
    should_continue,
    {
        "refactor": "refactor",
        "retry": "coder",
        "end": END
    },
)

workflow.add_edge("refactor", END)
app = workflow.compile()

# ==============================================================================
# 8. STREAMLIT ARAYÜZÜ (GUI)
# ==============================================================================
st.title("🤖 Multi-Agent Otonom Python Kod Geliştirici")
st.caption("LangGraph + Gemini + RAG Error Memory + Izole Sandbox")

# Yan Menü (Sidebar)
with st.sidebar:
    st.header("⚙️ Sistem Durumu")
    st.info(f"**Ana Model:** {MODEL_NAME}\n\n**Yedek Model:** {FALLBACK_MODEL_NAME}")
    st.markdown("---")
    st.markdown("### 🛠️ Ajan Mimarisi")
    st.markdown("""
    1. **🧠 Planner:** Mimariyi planlar.
    2. **💻 Coder:** Kodu yazar & araçla dener.
    3. **🧪 Tester:** Sandbox içinde kodu test eder.
    4. **🎨 Refactor:** PEP-8 / Type hint ekler.
    """)

# Örnek Görev Şablonu
default_task = """Bir Python fonksiyonu yaz:
1. 'veri' adında bir liste alsın. Liste içinde sayılar, metinler ve float değerler olabilir.
2. Sadece sayı olanların (int ve float, bool haric) karelerini alsın.
3. Metin olanların (str) uzunluklarını hesaplasın.
4. Sonuçları tek bir listede toplasın.
5. DİKKAT: Fonksiyon sonunda 'assert' ile kontrol sağla!
   Input: [4, "Serdar", 2.5, "RAG", -3]
   Beklenen Output: [16, 6, 6.25, 3, 9] olmalı.
6. Sonucu print ile ekrana bas."""

task_input = st.text_area("İstediğiniz Python Görevini / Problemini Yazın:", value=default_task, height=200)

if st.button("🚀 Kodu Oluştur ve Test Et", type="primary"):
    if not task_input.strip():
        st.warning("Lütfen geçerli bir görev yazın.")
    else:
        initial_state = {
            "task": task_input,
            "plan": "",
            "code": "",
            "error": "",
            "rag_context": "",
            "iterations": 0,
            "status": "",
        }

        with st.spinner("🤖 Multi-Agent sistemi çalışıyor... Lütfen bekleyin."):
            try:
                results = app.invoke(initial_state)

                st.success("🎉 Kod başarıyla geliştirildi ve test edildi!")

                col1, col2 = st.columns(2)

                with col1:
                    st.subheader("📋 Mimari Plan (Planner)")
                    st.write(results.get("plan", "Plan oluşturulamadı."))

                with col2:
                    st.subheader("🎉 Nihai Python Kodu (Refactored)")
                    final_code = results.get("code", "# Kod üretilemedi")
                    st.code(final_code, language="python")

                # Kodu çalıştırma ve sandbox sonucunu görme
                st.subheader("🧪 Arayüz Üzerinden Canlı Sandbox Testi")
                sandbox_output = run_python_sandbox.invoke({"code": final_code})
                st.text_area("Sandbox Çıktısı (Stdout / Stderr):", value=sandbox_output, height=150)

            except Exception as e:
                st.error(f"❌ Bir hata oluştu: {e}")
