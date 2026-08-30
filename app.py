import streamlit as st
import extra_streamlit_components as stx
from supabase import create_client, Client
import google.generativeai as genai
from audio_recorder_streamlit import audio_recorder
import json
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
            st.rerun() # Atualiza a tela na hora, sem precisar de F5
        else:
            st.error("Senha incorreta!")
    st.stop()

# --- INTERFACE PRINCIPAL (UX) ---
st.title("📊 Seu Controle Financeiro")
mes_atual = datetime.now().strftime("%m/%Y")
CATEGORIAS = ["Alimentação", "Role", "Compras x", "Carro", "Seguro", "Viagem", "Outros"]

# Criando abas para organizar a UX
tab_lancamento, tab_fixos, tab_dashboard = st.tabs([
    "🎙️ Lançamento Rápido", 
    "⚙️ Fixos e Tetos", 
    "📈 Dashboard"
])

# ==========================================
# ABA 1: LANÇAMENTO VIA ÁUDIO / MANUAL
# ==========================================
with tab_lancamento:
    st.subheader("Registrar Nova Transação")
    st.caption("Clique no microfone para começar a falar. **Clique novamente para cortar/parar a gravação.**")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        audio_bytes = audio_recorder(text="Gravar Áudio", icon_size="2x")
    
    if audio_bytes:
        with col2:
            st.audio(audio_bytes, format="audio/wav")
            if st.button("Processar Áudio com IA 🧠", use_container_width=True):
                with st.spinner("Analisando seu gasto..."):
                    try:
                        prompt = """
                        Extraia os dados. Retorne APENAS um JSON:
                        {"valor": float, "categoria": "Uma das categorias", "descricao": "resumo", "metodo_pagamento": "cartão/dinheiro"}
                        Categorias permitidas: Alimentação, Role, Compras x, Carro, Seguro, Viagem, Outros.
                        """
                        resposta = model.generate_content([prompt, {"mime_type": "audio/wav", "data": audio_bytes}])
                        texto_limpo = resposta.text.replace("```json", "").replace("```", "").strip()
                        st.session_state['novo_gasto'] = json.loads(texto_limpo)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro na IA: {e}")

    # Formulário Editável de Entrada (Carrega os dados da IA ou permite digitar do zero)
    with st.expander("📝 Editar Lançamento ou Inserir Manualmente", expanded=True):
        gasto = st.session_state.get('novo_gasto', {})
        
        with st.form("form_transacao"):
            c1, c2 = st.columns(2)
            valor = c1.number_input("Valor (R$)", value=float(gasto.get('valor', 0.0)), step=10.0)
            
            cat_sugerida = gasto.get('categoria', 'Outros')
            index_cat = CATEGORIAS.index(cat_sugerida) if cat_sugerida in CATEGORIAS else 6
            categoria = c2.selectbox("Categoria", CATEGORIAS, index=index_cat)
            
            descricao = st.text_input("Descrição (Ex: Mercadinho do Zé)", value=gasto.get('descricao', ''))
            pagamento = st.selectbox("Forma de Pagamento", ["Nubank", "Bradesco", "Itaú", "Dinheiro", "Outro"], 
                                     index=0 if "nubank" in str(gasto.get('metodo_pagamento', '')).lower() else 4)
            
            if st.form_submit_button("💾 Salvar Transação", use_container_width=True):
                supabase.table('transacoes').insert({
                    "tipo": "Gasto", "valor": valor, "categoria": categoria, 
                    "descricao": descricao, "metodo_pagamento": pagamento, "mes_referencia": mes_atual
                }).execute()
                st.success("✅ Salvo com sucesso!")
                if 'novo_gasto' in st.session_state:
                    del st.session_state['novo_gasto']

# ==========================================
# ABA 2: EDITAR FIXOS E TETOS
# ==========================================
with tab_fixos:
    st.subheader("Gerenciar Entradas e Saídas Fixas")
    st.write("Atualize seus ganhos (ex: Artefact, vô) e gastos recorrentes (ex: Seguro, Carro Maria).")
    
    col_ganhos, col_gastos = st.columns(2)
    
    with col_ganhos:
        st.markdown("### 💰 Ganhos Fixos")
        with st.form("form_ganhos_fixos"):
            desc_ganho = st.text_input("Fonte de Renda (ex: Artefact)")
            valor_ganho = st.number_input("Valor Recebido (R$)", min_value=0.0, step=100.0)
            if st.form_submit_button("Adicionar Ganho"):
                supabase.table('transacoes').insert({
                    "tipo": "Ganho", "valor": valor_ganho, "categoria": "Fixo", 
                    "descricao": desc_ganho, "mes_referencia": mes_atual
                }).execute()
                st.success("Ganho fixo registrado!")

    with col_gastos:
        st.markdown("### 💸 Gastos Fixos")
        with st.form("form_gastos_fixos"):
            desc_gasto = st.text_input("Despesa (ex: Seguro, Carla)")
            valor_gasto = st.number_input("Valor da Despesa (R$)", min_value=0.0, step=50.0)
            if st.form_submit_button("Adicionar Gasto Fixo"):
                supabase.table('transacoes').insert({
                    "tipo": "Gasto", "valor": valor_gasto, "categoria": "Fixo", 
                    "descricao": desc_gasto, "mes_referencia": mes_atual
                }).execute()
                st.success("Gasto fixo registrado!")
                
    st.divider()
    st.markdown("### 🎯 Definir Tetos Mensais")
    with st.form("form_tetos"):
        c1, c2 = st.columns(2)
        cat_teto = c1.selectbox("Categoria para o Teto", CATEGORIAS)
        valor_teto = c2.number_input("Valor Máximo (R$)", min_value=0.0, step=50.0)
        if st.form_submit_button("Salvar Teto"):
            # Lógica para salvar na tabela orcamentos
            supabase.table('orcamentos').upsert({
                "mes_referencia": mes_atual, "categoria": cat_teto, "valor_teto": valor_teto
            }).execute()
            st.success(f"Teto de {cat_teto} atualizado!")

# ==========================================
# ABA 3: DASHBOARD DE RESULTADOS
# ==========================================
with tab_dashboard:
    st.subheader(f"Resumo de {mes_atual}")
    
    # Puxar dados reais do banco (exemplo simplificado de visualização)
    try:
        response = supabase.table('transacoes').select("*").eq('mes_referencia', mes_atual).execute()
        dados = response.data
        
        ganhos_totais = sum(d['valor'] for d in dados if d['tipo'] == 'Ganho')
        gastos_totais = sum(d['valor'] for d in dados if d['tipo'] == 'Gasto')
        saldo = ganhos_totais - gastos_totais
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ganhos do Mês", f"R$ {ganhos_totais:.2f}")
        c2.metric("Gastos do Mês", f"R$ {gastos_totais:.2f}")
        c3.metric("Saldo Atual", f"R$ {saldo:.2f}")
        
        st.write("**Últimas Transações Registradas:**")
        st.dataframe(dados, use_container_width=True)
    except Exception as e:
        st.info("Adicione algumas transações para ver o dashboard!")
