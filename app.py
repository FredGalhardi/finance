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
    try:
        # Tenta buscar os dados
        res = supabase.table('transacoes').select("*").eq('mes_referencia', mes_ref).execute()
        if res.data:
            return pd.DataFrame(res.data)
        else:
            return pd.DataFrame()
    except Exception as e:
        # Imprime o erro real do Supabase na tela do app, furando o bloqueio do Streamlit
        st.error(f"🚨 ERRO REAL DO SUPABASE: {e}")
        return pd.DataFrame()

def deletar_transacao(id_transacao):
    try:
        supabase.table('transacoes').delete().eq('id', id_transacao).execute()
        st.rerun()
    except Exception as e:
        st.error(f"🚨 ERRO AO DELETAR: {e}")

# --- INTERFACE PRINCIPAL ---
st.title("📊 Seu Controle Financeiro")
meses_disponiveis = ["08/2026", "09/2026", "10/2026", "11/2026", "12/2026"]
mes_atual = st.selectbox("Selecione o Mês de Referência:", meses_disponiveis, index=1)

CATEGORIAS = ["Alimentação", "Role", "Compras x", "Carro", "Seguro", "Viagem", "Fixo", "Outros"]

tab_lancamento, tab_fixos, tab_dashboard, tab_historico = st.tabs([
    "🎙️ Lançamento Rápido", 
    "⚙️ Fixos e Tetos", 
    "📈 Dashboard",
    "📜 Histórico Completo"
])

# ==========================================
# ABA 1: LANÇAMENTO AUTOMÁTICO VIA ÁUDIO
# ==========================================
with tab_lancamento:
    st.subheader("Registrar Novo Gasto/Ganho")
    st.info("🎙️ **Grave e salve direto:** Diga 'Gastei 20 reais no Zé' ou 'Recebi 500 do vô'. O app salva sozinho.")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        audio_bytes = audio_recorder(text="Gravar Áudio (Clique para iniciar/parar)", icon_size="2x")
    
    if audio_bytes:
        with col2:
            st.audio(audio_bytes, format="audio/wav")
            if st.button("Transcrever e Salvar Direto 🚀", use_container_width=True, type="primary"):
                with st.spinner("Ouvindo e lançando na base..."):
                    try:
                        prompt = """
                        Você é um assistente financeiro. Extraia os dados do áudio e retorne APENAS um JSON válido.
                        Formato obrigatório:
                        {
                            "tipo": "Gasto" ou "Ganho", 
                            "valor": número float (ex: 20.0), 
                            "categoria": "Alimentação", "Role", "Compras x", "Carro", "Seguro", "Viagem", "Fixo" ou "Outros", 
                            "descricao": "resumo curto", 
                            "metodo_pagamento": "Nubank", "Bradesco", "Itaú" ou "Dinheiro"
                        }
                        Se for algo que o usuário pagou/gastou, defina tipo como "Gasto". Se recebeu/ganhou, defina como "Ganho".
                        Não escreva nenhuma palavra fora das chaves do JSON.
                        """
                        resposta = model.generate_content([prompt, {"mime_type": "audio/wav", "data": audio_bytes}])
                        texto_limpo = resposta.text.replace("```json", "").replace("```", "").strip()
                        dados = json.loads(texto_limpo)
                        
                        dados["mes_referencia"] = mes_atual
                        supabase.table('transacoes').insert(dados).execute()
                        
                        st.success(f"✅ Salvo direto: {dados['tipo']} de R$ {dados['valor']:.2f} em {dados['categoria']}!")
                    except Exception as e:
                        st.error(f"Erro ao processar ou salvar o áudio: {e}")

    st.divider()
    
    with st.expander("📝 Inserir Manualmente (Backup)", expanded=False):
        with st.form("form_transacao_manual"):
            c1, c2 = st.columns(2)
            tipo_m = c1.radio("Tipo da Transação", ["Gasto", "Ganho"], index=0)
            valor_m = c2.number_input("Valor (R$)", min_value=0.0, step=10.0)
            categoria_m = c1.selectbox("Categoria", CATEGORIAS)
            pagamento_m = c2.selectbox("Forma de Pagamento", ["Nubank", "Bradesco", "Itaú", "Dinheiro", "Outro"])
            descricao_m = st.text_input("Descrição (Ex: Mercadinho do Zé)")
            
            if st.form_submit_button("💾 Salvar Manualmente", use_container_width=True):
                try:
                    supabase.table('transacoes').insert({
                        "tipo": tipo_m, "valor": valor_m, "categoria": categoria_m, 
                        "descricao": descricao_m, "metodo_pagamento": pagamento_m, "mes_referencia": mes_atual
                    }).execute()
                    st.success("✅ Lançamento manual salvo com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

# ==========================================
# ABA 2: FIXOS E TETOS
# ==========================================
with tab_fixos:
    df_mes = get_transacoes(mes_atual)
    
    st.subheader(f"Gerenciamento de Fixos - {mes_atual}")
    col_ganhos, col_gastos = st.columns(2)
    
    with col_ganhos:
        st.markdown("### 💰 Ganhos Fixos Atuais")
        if not df_mes.empty and 'tipo' in df_mes.columns:
            df_ganhos_fixos = df_mes[(df_mes['tipo'] == 'Ganho') & (df_mes['categoria'] == 'Fixo')]
            if not df_ganhos_fixos.empty:
                st.dataframe(df_ganhos_fixos[['descricao', 'valor']], hide_index=True, use_container_width=True)
                id_deletar = st.selectbox("Excluir Ganho (Selecione o ID):", [""] + df_ganhos_fixos['id'].tolist(), key="del_g1")
                if id_deletar and st.button("🗑️ Excluir Ganho", key="btn_del_g1"):
                    deletar_transacao(id_deletar)
            else:
                st.info("Nenhum ganho fixo lançado.")
        else:
            st.info("Nenhum ganho fixo lançado.")
                
        with st.form("form_ganhos_fixos"):
            desc_ganho = st.text_input("Nova Fonte (ex: Artefact)")
            valor_ganho = st.number_input("Valor Recebido (R$)", min_value=0.0, step=100.0)
            if st.form_submit_button("Adicionar Ganho Fixo"):
                try:
                    supabase.table('transacoes').insert({
                        "tipo": "Ganho", "valor": valor_ganho, "categoria": "Fixo", 
                        "descricao": desc_ganho, "mes_referencia": mes_atual
                    }).execute()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao adicionar: {e}")

    with col_gastos:
        st.markdown("### 💸 Gastos Fixos Atuais")
        if not df_mes.empty and 'tipo' in df_mes.columns:
            df_gastos_fixos = df_mes[(df_mes['tipo'] == 'Gasto') & (df_mes['categoria'] == 'Fixo')]
            if not df_gastos_fixos.empty:
                st.dataframe(df_gastos_fixos[['descricao', 'valor']], hide_index=True, use_container_width=True)
                id_deletar2 = st.selectbox("Excluir Gasto (Selecione o ID):", [""] + df_gastos_fixos['id'].tolist(), key="del_g2")
                if id_deletar2 and st.button("🗑️ Excluir Gasto", key="btn_del_g2"):
                    deletar_transacao(id_deletar2)
            else:
                st.info("Nenhum gasto fixo lançado.")
        else:
            st.info("Nenhum gasto fixo lançado.")
                
        with st.form("form_gastos_fixos"):
            desc_gasto = st.text_input("Nova Despesa (ex: Seguro, Carla)")
            valor_gasto = st.number_input("Valor da Despesa (R$)", min_value=0.0, step=50.0)
            if st.form_submit_button("Adicionar Gasto Fixo"):
                try:
                    supabase.table('transacoes').insert({
                        "tipo": "Gasto", "valor": valor_gasto, "categoria": "Fixo", 
                        "descricao": desc_gasto, "mes_referencia": mes_atual
                    }).execute()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao adicionar: {e}")

# ==========================================
# ABA 3: DASHBOARD
# ==========================================
with tab_dashboard:
    st.subheader(f"Visão Geral - {mes_atual}")
    df_mes = get_transacoes(mes_atual)
    
    if not df_mes.empty and 'valor' in df_mes.columns and not df_mes[df_mes['valor'] > 0].empty:
        ganhos_totais = df_mes[df_mes['tipo'] == 'Ganho']['valor'].sum()
        gastos_totais = df_mes[df_mes['tipo'] == 'Gasto']['valor'].sum()
        saldo = ganhos_totais - gastos_totais
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ganhos Totais", f"R$ {ganhos_totais:,.2f}")
        c2.metric("Gastos Totais", f"R$ {gastos_totais:,.2f}")
        c3.metric("Saldo do Mês", f"R$ {saldo:,.2f}")
        
        st.divider()
        st.markdown("### Gastos por Categoria")
        gastos_df = df_mes[df_mes['tipo'] == 'Gasto']
        if not gastos_df.empty:
            gastos_agrupados = gastos_df.groupby('categoria')['valor'].sum().reset_index()
            st.bar_chart(gastos_agrupados, x="categoria", y="valor", use_container_width=True)
    else:
        st.info("Ainda não há dados financeiros registrados para gerar o dashboard deste mês.")

# ==========================================
# ABA 4: HISTÓRICO COMPLETO
# ==========================================
with tab_historico:
    st.subheader("Todos os Lançamentos")
    df_mes = get_transacoes(mes_atual)
    
    if not df_mes.empty and 'valor' in df_mes.columns and not df_mes[df_mes['valor'] > 0].empty:
        st.dataframe(
            df_mes[['id', 'data_transacao', 'tipo', 'categoria', 'descricao', 'valor', 'metodo_pagamento']], 
            use_container_width=True, hide_index=True
        )
        
        st.divider()
        st.markdown("### Excluir Registro Específico")
        id_excluir_hist = st.selectbox("Selecione o ID do registro que deseja apagar (Cuidado!):", [""] + df_mes['id'].tolist())
        if id_excluir_hist and st.button("🚨 Apagar Permanentemente", type="primary"):
            deletar_transacao(id_excluir_hist)
    else:
        st.info("Nenhuma transação registrada neste mês.")
