import streamlit as st
import extra_streamlit_components as stx
from supabase import create_client, Client
import google.generativeai as genai
from audio_recorder_streamlit import audio_recorder
import json
from datetime import datetime

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Controle Financeiro", page_icon="💰")

# Puxando as senhas do cofre do Streamlit
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]

# Conectando no Supabase
@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)
supabase: Client = init_supabase()

# Conectando no Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- CENTRAL DE COOKIES E LOGIN ---
@st.cache_resource(experimental_allow_widgets=True)
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()
auth_status = cookie_manager.get(cookie="auth_status")

# Se o cookie não disser "logado", mostra a tela de senha e trava o resto
if auth_status != "logado":
    st.title("🔒 Acesso Restrito")
    st.write("Digite sua senha para acessar o controle financeiro.")
    senha_digitada = st.text_input("Senha", type="password")
    
    if st.button("Entrar"):
        if senha_digitada == APP_PASSWORD:
            # Salva o cookie para durar até o ano 2030 (só loga uma vez)
            cookie_manager.set("auth_status", "logado", expires_at=datetime(2030, 1, 1))
            st.success("Login aprovado! Se a tela não recarregar, aperte F5.")
        else:
            st.error("Senha incorreta!")
    st.stop() # Para o app aqui se não tiver senha

# --- APLICATIVO PRINCIPAL ---
st.title("💸 Lançamento Rápido")

# Categorias da sua planilha
CATEGORIAS = ["Alimentação", "Role", "Compras x", "Carro", "Seguro", "Viagem", "Outros"]

st.write("🎙️ **Grave um áudio:** *'Gastei 20ão de alimentação no Seu Zé no cartão Nubank'*")

# Botão de gravação de áudio
audio_bytes = audio_recorder(text="Clique no microfone para gravar", icon_size="2x")

if audio_bytes:
    st.audio(audio_bytes, format="audio/wav")
    
    if st.button("Processar Áudio com IA 🧠"):
        with st.spinner("O Gemini está ouvindo e analisando seu gasto..."):
            try:
                # O Prompt diz pro Gemini exatamente como se comportar
                prompt = """
                Você é um assistente financeiro. Ouça o áudio e extraia os dados do gasto.
                Retorne APENAS um JSON válido com as seguintes chaves:
                - valor: número decimal (ex: 20.00)
                - categoria: escolha UMA entre (Alimentação, Role, Compras x, Carro, Seguro, Viagem, Outros)
                - descricao: resumo curto (ex: Mercadinho Seu Zé)
                - metodo_pagamento: cartão (Nubank, Bradesco) ou dinheiro. Tente deduzir.
                Não inclua nenhuma outra palavra além do JSON.
                """
                
                # Manda o áudio em bytes direto pro Gemini
                resposta = model.generate_content([
                    prompt, 
                    {"mime_type": "audio/wav", "data": audio_bytes}
                ])
                
                # Limpa a resposta pra garantir que é um JSON lido pelo Python
                texto_limpo = resposta.text.replace("```json", "").replace("```", "").strip()
                dados_gasto = json.loads(texto_limpo)
                
                # Salva o resultado na memória temporária da tela
                st.session_state['novo_gasto'] = dados_gasto
                st.success("Áudio processado com sucesso!")
                
            except Exception as e:
                st.error(f"Erro ao processar com Gemini: {e}")

# Exibe o formulário com os dados preenchidos pela IA para você apenas confirmar
if 'novo_gasto' in st.session_state:
    gasto = st.session_state['novo_gasto']
    st.divider()
    st.subheader("Confirme os dados extraídos:")
    
    with st.form("form_confirmacao"):
        valor = st.number_input("Valor (R$)", value=float(gasto.get('valor', 0.0)))
        
        cat_sugerida = gasto.get('categoria', 'Outros')
        index_cat = CATEGORIAS.index(cat_sugerida) if cat_sugerida in CATEGORIAS else 6
        categoria = st.selectbox("Categoria", CATEGORIAS, index=index_cat)
        
        descricao = st.text_input("Descrição", value=gasto.get('descricao', ''))
        pagamento = st.text_input("Pagamento (ex: Nubank, Bradesco)", value=gasto.get('metodo_pagamento', ''))
        
        # Mês de referência pegando automático
        mes_atual = datetime.now().strftime("%m/%Y")
        mes_ref = st.text_input("Mês de Referência", value=mes_atual)
        
        salvar = st.form_submit_button("💾 Salvar Gasto")
        
        if salvar:
            # Monta o pacote pra mandar pro Supabase
            payload = {
                "tipo": "Gasto",
                "valor": valor,
                "categoria": categoria,
                "descricao": descricao,
                "metodo_pagamento": pagamento,
                "mes_referencia": mes_ref
            }
            
            # Dá o comando de Insert
            supabase.table('transacoes').insert(payload).execute()
            st.success("✅ Gasto registrado no Supabase com sucesso!")
            del st.session_state['novo_gasto'] # Limpa a tela pra um novo gasto
