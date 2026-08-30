import streamlit as st
import extra_streamlit_components as stx
from supabase import create_client, Client
import google.generativeai as genai
from audio_recorder_streamlit import audio_recorder
import json
import pandas as pd
from datetime import datetime

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Controle Financeiro", page_icon="💰", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)
supabase: Client = init_supabase()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- LOGIN AUTOMÁTICO ---
cookie_manager = stx.CookieManager(key="cookie_manager")
auth_status = cookie_manager.get(cookie="auth_status")

if auth_status != "logado":
    st.title("🔒 Acesso Restrito")
    senha_digitada = st.text_input("Digite sua senha", type="password")
    if st.button("Entrar"):
        if senha_digitada == APP_PASSWORD:
            cookie_manager.set("auth_status", "logado", expires_at=datetime(2030, 1, 1))
            st.rerun()
        else:
            st.error("Senha incorreta!")
    st.stop()

# --- FUNÇÕES DE BANCO DE DADOS ---
def get_transacoes(mes_ref):
    res = supabase.table('transacoes').select("*").eq('mes_referencia', mes_ref).execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def deletar_transacao(id_transacao):
    supabase.table('transacoes').delete().eq('id', id_transacao).execute()
    st.rerun()

# --- INTERFACE PRINCIPAL ---
st.title("📊 Seu Controle Financeiro")
meses_disponiveis = ["08/2026", "09/2026", "10/2026", "11/2026", "12/2026"]
mes_atual = st.selectbox("Selecione o Mês de Referência:", meses_disponiveis, index=1)

CATEGORIAS = ["Alimentação", "Role", "Compras x", "Carro", "Seguro", "Viagem", "Fixo", "Outros"]

# Criação das 4 Abas
tab_lancamento, tab_fixos, tab_dashboard, tab_historico = st.tabs([
    "🎙️ Lançamento Rápido", 
    "⚙️ Fixos e Tetos", 
    "📈 Dashboard",
    "📜 Histórico Completo"
])

# ==========================================
# ABA 1: LANÇAMENTO (ÁUDIO + MANUAL)
# ==========================================
with tab_lancamento:
    st.subheader("Registrar Novo Gasto/Ganho")
    st.info("🎙️ **Grave um áudio:** (Ex: 'Gastei 20 reais em alimentação no seu Zé no Nubank'). O Gemini vai preencher o formulário abaixo para você confirmar.")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        audio_bytes = audio_recorder(text="Gravar Áudio", icon_size="2x")
    
    if audio_bytes:
        with col2:
            st.audio(audio_bytes, format="audio/wav")
            if st.button("Transcrever e Preencher com IA 🧠", use_container_width=True):
                with st.spinner("O Gemini está analisando seu áudio..."):
                    try:
                        prompt = """
                        Extraia os dados financeiros do áudio. Retorne APENAS um JSON válido.
                        Formato: {"valor": float, "categoria": "string", "descricao": "string", "metodo_pagamento": "string"}
                        Categorias permitidas: Alimentação, Role, Compras x, Carro, Seguro, Viagem, Outros.
                        """
                        resposta = model.generate_content([prompt, {"mime_type": "audio/wav", "data": audio_bytes}])
                        texto_limpo = resposta.text.replace("```json", "").replace("
