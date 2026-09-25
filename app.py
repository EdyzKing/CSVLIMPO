from pathlib import Path
from difflib import SequenceMatcher
import io
import re
import pandas as pd
import unicodedata
import streamlit as st

from data_cleaning import (
    normalizar_colunas_para_padrao,
    obter_mapeamento_colunas,
    padronizar_bairros,
    separar_registros_sem_bairro,
    separar_nomes_iniciados_por_numero,
    identificar_nomes_numericos,
    identificar_nomes_muito_curtos,
    identificar_nomes_de_teste,
    identificar_telefones_com_prefixos_bloqueados,
)
from tmd_calculation import (
    calcular_tmd_comparativo_dos_csvs,
    calcular_tmd_dos_csvs,
    corrigir_sessoes_com_logouts_manuais,
    diagnosticar_tmd,
    identificar_colaboradores_sem_logout,
)


# =============================
# CONFIGURAÇÃO DA PÁGINA
# =============================
st.set_page_config(
    page_title="CSV Data Cleaner",
    page_icon="🧹",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&display=swap');

    :root {
        --bg: #0b1020;
        --surface: #121a2e;
        --surface-2: #18223b;
        --border: rgba(148, 163, 184, 0.14);
        --text: #e6ebf5;
        --muted: #8b97b0;
        --primary: #5eead4;
        --primary-2: #22d3ee;
        --green: #4ade80;
        --yellow: #facc15;
        --red: #fb7185;
        --radius: 16px;
    }

    html, body, [class*="css"], [data-testid="stAppViewContainer"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
        color: var(--text);
    }
    [data-testid="stAppViewContainer"] {
        background:
          radial-gradient(900px 500px at 90% -10%, rgba(34,211,238,0.10), transparent 60%),
          radial-gradient(700px 400px at -10% 110%, rgba(94,234,212,0.08), transparent 60%),
          var(--bg);
    }
    [data-testid="stHeader"] { background: transparent; }
    .block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1200px; }

    h1, h2, h3, h4 { color: #f8fafc !important; letter-spacing: -0.02em; font-weight: 800 !important; }
    h2 { font-size: 1.6rem !important; }
    h3 { font-size: 1.15rem !important; }
    p, label, .stMarkdown { color: var(--text); }
    [data-testid="stCaptionContainer"] { color: var(--muted) !important; }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #080c18;
        border-right: 1px solid var(--border);
    }
    section[data-testid="stSidebar"] .stRadio > div { gap: 0.35rem; }
    section[data-testid="stSidebar"] .stRadio label {
        background: transparent;
        border: 1px solid transparent;
        border-radius: 12px;
        padding: 0.7rem 0.85rem !important;
        width: 100%;
        font-weight: 600;
        transition: all .15s ease;
    }
    section[data-testid="stSidebar"] .stRadio label:hover { background: var(--surface); }
    section[data-testid="stSidebar"] .stRadio label:has(input:checked) {
        background: var(--surface-2);
        border-color: rgba(94,234,212,0.35);
        color: #fff;
    }
    section[data-testid="stSidebar"] .stRadio label > div:first-child { display: none; }

    /* Hero */
    .hero {
        background: linear-gradient(135deg, var(--surface) 0%, var(--surface-2) 100%);
        border: 1px solid var(--border);
        border-radius: 22px;
        padding: 1.8rem 2rem;
        margin-bottom: 1.6rem;
        position: relative;
        overflow: hidden;
    }
    .hero::after {
        content: ""; position: absolute; right: -60px; top: -60px;
        width: 220px; height: 220px; border-radius: 50%;
        background: radial-gradient(circle, rgba(94,234,212,0.25), transparent 70%);
    }
    .hero .tag {
        display: inline-block; font-family: 'JetBrains Mono', monospace;
        font-size: .72rem; letter-spacing: .08em; text-transform: uppercase;
        color: var(--primary); background: rgba(94,234,212,0.1);
        border: 1px solid rgba(94,234,212,0.25);
        padding: .25rem .6rem; border-radius: 999px; margin-bottom: .8rem;
    }
    .hero h1 { font-size: 2rem !important; margin: 0 0 .3rem 0 !important; padding: 0 !important; }
    .hero p { color: var(--muted); margin: 0; font-size: 1rem; }

    .steps { display: flex; gap: .6rem; flex-wrap: wrap; margin-top: 1.1rem; }
    .step {
        background: rgba(8,12,24,0.5); border: 1px solid var(--border);
        border-radius: 999px; padding: .35rem .8rem; font-size: .82rem; color: var(--text);
    }
    .step b { color: var(--primary); margin-right: .35rem; }

    /* Buttons */
    .stButton > button, .stDownloadButton > button {
        border-radius: 12px; font-weight: 700; padding: .65rem 1.1rem;
        transition: transform .15s ease, box-shadow .15s ease, background .15s ease;
    }
    .stButton > button {
        border: none;
        background: linear-gradient(135deg, var(--primary), var(--primary-2));
        color: #04202a;
        box-shadow: 0 10px 24px -8px rgba(34,211,238,0.45);
    }
    .stButton > button:hover { transform: translateY(-1px); color: #04202a; }
    .stDownloadButton > button {
        background: var(--surface); color: var(--text);
        border: 1px solid var(--border);
        justify-content: flex-start;
    }
    .stDownloadButton > button:hover { border-color: rgba(94,234,212,0.5); color: #fff; }
    .stDownloadButton > button[kind="primary"] {
        background: linear-gradient(135deg, var(--primary), var(--primary-2));
        color: #04202a; border: none; justify-content: center; font-size: 1.02rem;
    }

    /* Uploader */
    [data-testid="stFileUploader"] section {
        background: var(--surface);
        border: 1.5px dashed rgba(94,234,212,0.35);
        border-radius: var(--radius);
        padding: 1.4rem;
    }
    [data-testid="stFileUploader"] section:hover { border-color: var(--primary); }

    /* Metrics */
    [data-testid="stMetric"] {
        background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--radius); padding: 1rem 1.2rem;
    }
    [data-testid="stMetricLabel"] { color: var(--muted) !important; }
    [data-testid="stMetricValue"] { color: #fff !important; font-weight: 800 !important; }

    /* Tables, expanders, inputs */
    [data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
    [data-testid="stExpander"] { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
    .stTextInput input, .stSelectbox div[data-baseweb="select"] > div, .stMultiSelect div[data-baseweb="select"] > div {
        background: var(--surface) !important; border-radius: 10px !important; border-color: var(--border) !important;
    }
    .stCheckbox label, .stToggle label { font-weight: 500; }

    .stAlert { border-radius: 12px; border: 1px solid var(--border); }
    hr { border-color: var(--border) !important; margin: 1.6rem 0 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def hero(tag, titulo, descricao, passos=None):
    passos_html = ""
    if passos:
        passos_html = '<div class="steps">' + "".join(
            f'<span class="step"><b>{i}</b>{p}</span>'
            for i, p in enumerate(passos, 1)
        ) + "</div>"
    st.markdown(
        f'<div class="hero"><span class="tag">{tag}</span>'
        f"<h1>{titulo}</h1><p>{descricao}</p>{passos_html}</div>",
        unsafe_allow_html=True,
    )



# ============================================================
# VALIDAÇÃO DE BAIRROS
# ============================================================

BAIRROS_PATH = Path("dados") / "bairros_validos.csv"


def normalizar_para_comparacao(valor):
    if pd.isna(valor) or valor is None:
        return ""

    texto = str(valor).strip()

    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )

    texto = texto.upper()

    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


@st.cache_data
def carregar_bairros_validos():

    if not BAIRROS_PATH.exists():
        return pd.DataFrame(columns=["Cidade", "Bairro"])

    try:
        base = pd.read_csv(
            BAIRROS_PATH,
            sep=";",
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig"
        )

    except UnicodeDecodeError:

        base = pd.read_csv(
            BAIRROS_PATH,
            sep=";",
            dtype=str,
            keep_default_na=False,
            encoding="latin1"
        )

    base.columns = [
        str(c).strip()
        for c in base.columns
    ]

    if (
        "Cidade" not in base.columns
        or "Bairro" not in base.columns
    ):
        return pd.DataFrame(
            columns=["Cidade", "Bairro"]
        )

    base["Cidade_cmp"] = base["Cidade"].apply(
        normalizar_para_comparacao
    )

    base["Bairro_cmp"] = base["Bairro"].apply(
        normalizar_para_comparacao
    )

    return base


def validar_bairros_por_cidade(dados):

    if "Bairro" not in dados.columns:
        return (
            dados.copy(),
            pd.DataFrame(columns=dados.columns)
        )

    validos = carregar_bairros_validos()

    if validos.empty:
        return (
            dados.copy(),
            pd.DataFrame(columns=dados.columns)
        )

    def melhor_correspondencia(valor, opcoes, limite):
        if not valor:
            return None

        melhor = max(
            (
                (SequenceMatcher(None, valor, chave).ratio(), original)
                for chave, original in opcoes
            ),
            default=(0, None)
        )

        if melhor[0] >= limite:
            return melhor[1]
        return None

    pares_por_cidade = {}
    cidades = []

    for registro in validos.itertuples(index=False):
        pares_por_cidade.setdefault(
            registro.Cidade_cmp,
            []
        ).append((registro.Bairro_cmp, registro.Bairro))

        if not any(
            chave == registro.Cidade_cmp
            for chave, _ in cidades
        ):
            cidades.append(
                (registro.Cidade_cmp, registro.Cidade)
            )

    dados_corrigidos = dados.copy()
    indices_invalidos = []

    for indice, registro in dados.iterrows():
        bairro_cmp = normalizar_para_comparacao(
            registro["Bairro"]
        )

        if not bairro_cmp:
            continue

        if "Cidade" in dados.columns:
            cidade_cmp = normalizar_para_comparacao(
                registro["Cidade"]
            )

            cidade_oficial = melhor_correspondencia(
                cidade_cmp,
                cidades,
                limite=0.86
            )

            if cidade_oficial is None:
                indices_invalidos.append(indice)
                continue

            cidade_chave = normalizar_para_comparacao(
                cidade_oficial
            )

            bairro_oficial = melhor_correspondencia(
                bairro_cmp,
                pares_por_cidade[cidade_chave],
                limite=0.78
            )

            if bairro_oficial is None:
                indices_invalidos.append(indice)
                continue

            dados_corrigidos.at[indice, "Cidade"] = cidade_oficial
            dados_corrigidos.at[indice, "Bairro"] = bairro_oficial
        else:
            bairros = [
                (registro.Bairro_cmp, registro.Bairro)
                for registro in validos.itertuples(index=False)
            ]

            bairro_oficial = melhor_correspondencia(
                bairro_cmp,
                bairros,
                limite=0.78
            )

            if bairro_oficial is None:
                indices_invalidos.append(indice)
                continue

            dados_corrigidos.at[indice, "Bairro"] = bairro_oficial

    registros_invalidos = dados.loc[indices_invalidos].copy()

    registros_validos = dados_corrigidos.drop(
        index=indices_invalidos
    ).copy()

    return (
        registros_validos,
        registros_invalidos
    )


# ============================================================
# UTILITÁRIO DE LEITURA CSV
# ============================================================

def detectar_separador_csv(conteudo):
    """Detecta o separador do CSV usando a contagem de delimitadores."""
    amostra = conteudo[:4096].decode("utf-8", errors="ignore")
    if amostra.count(";") >= amostra.count(","):
        return ";"
    return ","


def restaurar_nomes_originais(dados, mapeamento, colunas_originais=None):
    """Retorna os nomes originais depois do processamento interno."""
    renomear = {
        nome_padrao: nome_original
        for nome_padrao, nome_original in mapeamento.items()
        if nome_padrao in dados.columns
        and nome_original not in dados.columns
    }
    dados = dados.rename(columns=renomear)

    if colunas_originais:
        colunas_presentes = [
            coluna
            for coluna in colunas_originais
            if coluna in dados.columns
        ]
        colunas_extras = [
            coluna
            for coluna in dados.columns
            if coluna not in colunas_presentes
        ]
        dados = dados.reindex(
            columns=colunas_presentes + colunas_extras
        )

    return dados


# ============================================================
# CÁLCULO DE TMD
# ============================================================

def unificar_tmd_por_equipe(resultado_diario):
    if resultado_diario is None or resultado_diario.empty:
        return pd.DataFrame(columns=["Equipe", "TMD médio do período"])

    dados = resultado_diario.copy()
    dados["_segundos"] = pd.to_timedelta(
        dados["TMD"], errors="coerce"
    ).dt.total_seconds()
    resumo = (
        dados.dropna(subset=["_segundos"])
        .groupby("Equipe", as_index=False)["_segundos"]
        .sum()
    )

    def formatar(segundos):
        segundos = max(0, int(round(segundos)))
        horas, resto = divmod(segundos, 3600)
        minutos, segundos = divmod(resto, 60)
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

    resumo["TMD total do período"] = resumo["_segundos"].map(formatar)
    return resumo[["Equipe", "TMD total do período"]]


def formatar_logout_manual(valor):
    digitos = re.sub(r"\D", "", str(valor))[:14]
    partes = []
    limites = (2, 2, 4, 2, 2, 2)
    inicio = 0
    for limite in limites:
        parte = digitos[inicio:inicio + limite]
        if not parte:
            break
        partes.append(parte)
        inicio += limite

    if len(partes) <= 3:
        return "/".join(partes)
    data = "/".join(partes[:3])
    horario = ":".join(partes[3:])
    return f"{data} {horario}"


def aplicar_mascara_logout_manual(chave):
    st.session_state[chave] = formatar_logout_manual(
        st.session_state.get(chave, "")
    )


def renderizar_ajustes_logout(sem_logout_editor):
    st.subheader("Adicionar Logouts manualmente")
    st.warning(
        "Preencha os horários conhecidos e clique em recalcular. "
        "Use DD/MM/AAAA HH:MM:SS."
    )
    valores_manuais = []
    for indice, registro in sem_logout_editor.iterrows():
        col1, col2, col3, col4 = st.columns([2.4, 2.2, 1.8, 2.4])
        col1.text(registro["Agente"])
        col2.text(registro["Fila"])
        col3.text(registro["Login"])
        chave_logout = (
            "logout_manual_"
            f"{registro['Agente']}_{registro['Fila']}_{indice}"
        )
        valor = col4.text_input(
            "Logout manual",
            value=st.session_state.get(chave_logout, ""),
            placeholder="DD/MM/AAAA HH:MM:SS",
            key=chave_logout,
            on_change=aplicar_mascara_logout_manual,
            args=(chave_logout,),
            label_visibility="collapsed",
        )
        valores_manuais.append({
            "Agente": registro["Agente"],
            "Fila": registro["Fila"],
            "Login": registro["Login"],
            "Direção": registro["Direção"],
            "Status": registro["Status"],
            "Logout manual": valor,
        })
    return pd.DataFrame(valores_manuais)


def executar_tmd():
    hero(
        "Atendimento",
        "Cálculo automático de TMD",
        "Calcula o TMD das filas oficiais de Cobrança e Retenção.",
        ["Envie Sessões em Filas", "Envie Pausas", "Processe e revise"],
    )

    sessoes = st.file_uploader(
        "Selecionar Sessões em Filas",
        type=["csv"],
        key="arquivo_tmd_sessoes",
    )
    pausas = st.file_uploader(
        "Selecionar Pausas",
        type=["csv"],
        key="arquivo_tmd_pausas",
    )

    if sessoes is not None:
        st.success(f"Sessões em Filas carregadas: {sessoes.name}")
    if pausas is not None:
        st.success(f"Pausas carregadas: {pausas.name}")

    if sessoes is not None and pausas is not None:
        with st.expander("Verificação dos arquivos carregados"):
            try:
                diagnostico = diagnosticar_tmd(
                    sessoes.getvalue(), pausas.getvalue()
                )
                st.write(
                    f"Sessões lidas: {diagnostico['sessoes_lidas']} | "
                    f"Pausas lidas: {diagnostico['pausas_lidas']} | "
                    f"Sessões válidas: {diagnostico['intervalos_validos']}"
                )
                st.write("Filas encontradas:", diagnostico["filas"])
                st.write(
                    "Direções encontradas:",
                    diagnostico["direcoes_sessoes"],
                )
                st.dataframe(
                    diagnostico["amostra_sessoes"],
                    use_container_width=True,
                    hide_index=True,
                )
            except ValueError as erro:
                st.error(f"Não foi possível ler os arquivos: {erro}")

        try:
            sessoes_lidas = pd.read_csv(
                io.BytesIO(sessoes.getvalue()),
                sep=detectar_separador_csv(sessoes.getvalue()),
                dtype=str,
                keep_default_na=False,
            )
        except (ValueError, pd.errors.ParserError) as erro:
            st.error(f"Não foi possível preparar os Logouts manuais: {erro}")

    if st.button("Calcular TMD", type="primary", key="calcular_tmd"):
        if sessoes is None or pausas is None:
            st.warning("Selecione os dois arquivos CSV antes de calcular.")
        else:
            try:
                comparativo, sem_logout = (
                    calcular_tmd_comparativo_dos_csvs(
                        sessoes.getvalue(),
                        pausas.getvalue(),
                        None,
                    )
                )
                st.session_state["resultado_tmd_comparativo"] = comparativo
                st.session_state["colaboradores_sem_logout"] = sem_logout
                resultado_diario = comparativo.rename(
                    columns={"TMD corrigido": "TMD"}
                )[["Data", "Equipe", "TMD"]]
                st.session_state["resultado_tmd_diario"] = resultado_diario
                st.session_state["resultado_tmd"] = unificar_tmd_por_equipe(
                    resultado_diario
                )
                st.success("Processamento concluído.")
            except (ValueError, TypeError) as erro:
                st.error(f"Não foi possível calcular o TMD: {erro}")

    resultado = st.session_state.get("resultado_tmd")
    comparativo = st.session_state.get("resultado_tmd_comparativo")
    sem_logout = st.session_state.get("colaboradores_sem_logout")
    if resultado is not None:
        if resultado.empty:
            st.warning(
                "Nenhum resultado foi gerado. Verifique as colunas de data, "
                "Login, Logout, Tempo Logado e os nomes das filas."
            )
        else:
            st.subheader("Resultado do cálculo automático")
            st.dataframe(resultado, use_container_width=True, hide_index=True)
            resultado_diario = st.session_state.get("resultado_tmd_diario")
            if resultado_diario is not None:
                with st.expander("Ver resultado detalhado por dia"):
                    st.dataframe(
                        resultado_diario,
                        use_container_width=True,
                        hide_index=True,
                    )
            if comparativo is not None:
                st.subheader("Comparativo do cálculo")
                st.caption(
                    "Sem correção: filas e registros duplicados são somados. "
                    "Corrigido: sessões simultâneas e pausas duplicadas são unidas."
                )
                st.dataframe(
                    comparativo,
                    use_container_width=True,
                    hide_index=True,
                )
                st.download_button(
                    "Baixar comparativo TMD",
                    data=comparativo.to_csv(
                        sep=";", index=False, encoding="utf-8-sig"
                    ),
                    file_name="tmd_comparativo.csv",
                    mime="text/csv",
                    key="download_tmd_comparativo",
                )
            if sem_logout is not None and not sem_logout.empty:
                st.subheader("Correção manual para Cobrança e Retenção")
                st.warning(
                    f"{sem_logout['Agente'].nunique()} colaborador(es) "
                    "dos setores Cobrança/Retenção possuem Saída sem Logout."
                )
                st.dataframe(
                    sem_logout,
                    use_container_width=True,
                    hide_index=True,
                )
                ajustes_manuais = renderizar_ajustes_logout(
                    sem_logout.copy()
                )
                if st.button(
                    "Recalcular TMD com os Logouts informados",
                    type="primary",
                    key="recalcular_tmd_logouts",
                ):
                    try:
                        comparativo_atualizado, sem_logout_atualizado = (
                            calcular_tmd_comparativo_dos_csvs(
                                sessoes.getvalue(),
                                pausas.getvalue(),
                                ajustes_manuais,
                            )
                        )
                        sessoes_corrigidas = (
                            corrigir_sessoes_com_logouts_manuais(
                                sessoes.getvalue(),
                                ajustes_manuais,
                            )
                        )
                        st.session_state[
                            "sessoes_corrigidas_manualmente"
                        ] = sessoes_corrigidas
                        st.session_state[
                            "resultado_tmd_comparativo"
                        ] = comparativo_atualizado
                        st.session_state[
                            "colaboradores_sem_logout"
                        ] = sem_logout_atualizado
                        resultado_diario_atualizado = (
                            comparativo_atualizado.rename(
                                columns={"TMD corrigido": "TMD"}
                            )[["Data", "Equipe", "TMD"]]
                        )
                        st.session_state[
                            "resultado_tmd_diario"
                        ] = resultado_diario_atualizado
                        st.session_state["resultado_tmd"] = (
                            unificar_tmd_por_equipe(
                                resultado_diario_atualizado
                            )
                        )
                        st.success("TMD recalculado com os Logouts informados.")
                    except (ValueError, TypeError) as erro:
                        st.error(f"Não foi possível recalcular o TMD: {erro}")
                sessoes_corrigidas = st.session_state.get(
                    "sessoes_corrigidas_manualmente"
                )
                if sessoes_corrigidas is not None:
                    st.download_button(
                        "Baixar sessões corrigidas manualmente",
                        data=sessoes_corrigidas.to_csv(
                            sep=";", index=False, encoding="utf-8-sig"
                        ),
                        file_name="sessoes_corrigidas_manualmente.csv",
                        mime="text/csv",
                        key="download_sessoes_corrigidas",
                    )
                st.download_button(
                    "Baixar lista de colaboradores sem Logout",
                    data=sem_logout.to_csv(
                        sep=";", index=False, encoding="utf-8-sig"
                    ),
                    file_name="colaboradores_sem_logout.csv",
                    mime="text/csv",
                    key="download_sem_logout",
                )
            st.download_button(
                "Baixar resultado TMD",
                data=resultado.to_csv(
                    sep=";", index=False, encoding="utf-8-sig"
                ),
                file_name="tmd_diario.csv",
                mime="text/csv",
                key="download_tmd",
            )

    st.divider()




# ============================================================
# LIMPEZA DE BASE
# ============================================================

def executar_limpeza():
    hero(
        "Limpeza",
        "Limpeza de Base CSV",
        "Importe sua base, escolha as regras de limpeza e baixe o arquivo tratado.",
        ["Envie o CSV", "Escolha as regras", "Baixe o resultado"],
    )

    arquivo = st.file_uploader(
        "Selecione o arquivo CSV",
        type=["csv"],
        help=(
            "O sistema tenta automaticamente UTF-8 "
            "e, se necessário, Latin-1."
        ),
        key="arquivo_limpeza"
    )

    if arquivo is not None:

        try:

            conteudo = arquivo.getvalue()

            if not conteudo.strip():

                st.error(
                    "O arquivo CSV está vazio. "
                    "Envie um arquivo com cabeçalho e registros."
                )

                st.stop()

            separador = detectar_separador_csv(conteudo)

            try:

                dados_original = pd.read_csv(
                    io.BytesIO(conteudo),
                    sep=separador,
                    encoding="utf-8-sig",
                    dtype=str,
                    keep_default_na=False
                )

            except pd.errors.EmptyDataError:

                st.error(
                    "O arquivo CSV não possui colunas ou cabeçalho legível."
                )

                st.stop()

            except UnicodeDecodeError:

                dados_original = pd.read_csv(
                    io.BytesIO(conteudo),
                    sep=separador,
                    encoding="latin1",
                    dtype=str,
                    keep_default_na=False
                )

            dados_original.columns = dados_original.columns.str.strip()
            colunas_originais = list(dados_original.columns)
            dados_original = normalizar_colunas_para_padrao(
                dados_original
            )
            mapeamento_colunas_saida = obter_mapeamento_colunas(
                colunas_originais
            )

            st.success(
                "Arquivo carregado com sucesso!"
            )

            with st.expander(
                "📋 Colunas encontradas no arquivo"
            ):

                st.write(
                    ", ".join(
                        colunas_originais
                    )
                )

            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Registros",
                len(dados_original)
            )

            col2.metric(
                "Colunas",
                len(dados_original.columns)
            )

            col3.metric(
                "Arquivo",
                arquivo.name
            )

            st.subheader(
                "Regras de limpeza"
            )

            st.write(
                "Marque as operações que deseja aplicar:"
            )

            pode_validar_bairros = "Bairro" in dados_original.columns

            c1, c2 = st.columns(2)

            with c1:

                remover_sem_bairro = st.checkbox(
                    "Remover registros sem bairro",
                    value=True
                )

                remover_inicio_numero = st.checkbox(
                    "Remover nomes iniciados por número",
                    value=True
                )

                padronizar = st.checkbox(
                    "Padronizar bairros",
                    value=True
                )

                validar_bairros = st.checkbox(
                    "Validar bairros contra a base oficial "
                    "(Cidade + Bairro)",
                    value=False,
                    disabled=not pode_validar_bairros,
                    help=(
                        "Com Cidade, valida a combinação Cidade + Bairro. "
                        "Sem Cidade, valida apenas o Bairro."
                    )
                )

                if not pode_validar_bairros:
                    st.caption(
                        "Validação oficial indisponível: o arquivo não "
                        "possui a coluna Bairro."
                    )

            with c2:

                remover_numericos = st.checkbox(
                    "Remover nomes somente numéricos",
                    value=False
                )

                remover_curtos = st.checkbox(
                    "Remover nomes muito curtos (até 2 caracteres)",
                    value=False
                )

                remover_teste = st.checkbox(
                    "Remover nomes contendo TESTE/TEST",
                    value=False
                )

                remover_telefones_bloqueados = st.checkbox(
                    "Remover telefones com prefixos bloqueados",
                    value=False
                )

            st.info(
                "As opções da coluna à direita e a validação "
                "oficial são desativadas por padrão porque podem "
                "remover registros que talvez precisem apenas "
                "de revisão."
            )

            st.divider()

            if st.button(
                "🧹 PROCESSAR ARQUIVO",
                type="primary",
                use_container_width=True
            ):

                erros_colunas = []

                precisa_razao = (
                    remover_inicio_numero
                    or remover_numericos
                    or remover_curtos
                    or remover_teste
                )

                precisa_telefone = remover_telefones_bloqueados

                precisa_bairro = (
                    remover_sem_bairro
                    or padronizar
                    or validar_bairros
                )

                if (
                    precisa_razao
                    and "Razão social"
                    not in dados_original.columns
                ):

                    erros_colunas.append(
                        "• 'Razão social' é necessária "
                        "para as regras de limpeza de nomes."
                    )

                if (
                    precisa_bairro
                    and "Bairro"
                    not in dados_original.columns
                ):

                    erros_colunas.append(
                        "• 'Bairro' é necessária "
                        "para as regras de limpeza/padronização."
                    )

                if (
                    precisa_telefone
                    and "Telefone" not in dados_original.columns
                ):

                    erros_colunas.append(
                        "• 'Telefone' é necessária "
                        "para remover prefixos telefônicos bloqueados."
                    )

                if erros_colunas:

                    st.error(
                        "O arquivo não possui todas as colunas "
                        "necessárias para as opções selecionadas."
                    )

                    for erro in erros_colunas:
                        st.warning(erro)

                    st.info(
                        "Desmarque as opções relacionadas "
                        "às colunas ausentes e processe novamente."
                    )

                    st.stop()

                dados = dados_original.copy()

                # ============================
                # RELATÓRIOS
                # ============================

                removidos_sem_bairro = pd.DataFrame(
                    columns=dados.columns
                )

                removidos_inicio_numero = pd.DataFrame(
                    columns=dados.columns
                )

                removidos_numericos = pd.DataFrame(
                    columns=dados.columns
                )

                removidos_curtos = pd.DataFrame(
                    columns=dados.columns
                )

                removidos_teste = pd.DataFrame(
                    columns=dados.columns
                )

                removidos_telefones_bloqueados = pd.DataFrame(
                    columns=dados.columns
                )

                removidos_bairros_invalidos = pd.DataFrame(
                    columns=dados.columns
                )

                # ============================
                # 1 - SEM BAIRRO
                # ============================

                if remover_sem_bairro:

                    dados, removidos_sem_bairro = (
                        separar_registros_sem_bairro(
                            dados
                        )
                    )

                # ============================
                # 2 - BAIRROS OFICIAIS
                # ============================

                if validar_bairros:

                    (
                        dados,
                        removidos_bairros_invalidos
                    ) = validar_bairros_por_cidade(
                        dados
                    )

                # ============================
                # 3 - NOME INICIADO POR NÚMERO
                # ============================

                if remover_inicio_numero:

                    (
                        dados,
                        removidos_inicio_numero
                    ) = separar_nomes_iniciados_por_numero(
                        dados
                    )

                # ============================
                # 4 - SOMENTE NUMÉRICO
                # ============================

                if remover_numericos:

                    encontrados = (
                        identificar_nomes_numericos(
                            dados
                        )
                    )

                    removidos_numericos = (
                        encontrados.copy()
                    )

                    dados = dados.drop(
                        index=encontrados.index
                    )

                # ============================
                # 5 - MUITO CURTO
                # ============================

                if remover_curtos:

                    encontrados = (
                        identificar_nomes_muito_curtos(
                            dados
                        )
                    )

                    removidos_curtos = (
                        encontrados.copy()
                    )

                    dados = dados.drop(
                        index=encontrados.index
                    )

                # ============================
                # 6 - TESTE / TEST
                # ============================

                if remover_teste:

                    encontrados = (
                        identificar_nomes_de_teste(
                            dados
                        )
                    )

                    removidos_teste = (
                        encontrados.copy()
                    )

                    dados = dados.drop(
                        index=encontrados.index
                    )

                # ============================
                # 7 - TELEFONES COM PREFIXOS BLOQUEADOS
                # ============================

                if remover_telefones_bloqueados:

                    encontrados = (
                        identificar_telefones_com_prefixos_bloqueados(
                            dados
                        )
                    )

                    removidos_telefones_bloqueados = (
                        encontrados.copy()
                    )

                    dados = dados.drop(
                        index=encontrados.index
                    )

                # ============================
                # 8 - PADRONIZAR BAIRROS
                # ============================

                if padronizar:

                    dados = padronizar_bairros(
                        dados
                    )

                total_removidos = (
                    len(removidos_sem_bairro)
                    + len(removidos_bairros_invalidos)
                    + len(removidos_inicio_numero)
                    + len(removidos_numericos)
                    + len(removidos_curtos)
                    + len(removidos_teste)
                    + len(removidos_telefones_bloqueados)
                )

                dados = restaurar_nomes_originais(
                    dados,
                    mapeamento_colunas_saida,
                    colunas_originais
                )

                removidos_sem_bairro = restaurar_nomes_originais(
                    removidos_sem_bairro,
                    mapeamento_colunas_saida,
                    colunas_originais
                )
                removidos_bairros_invalidos = restaurar_nomes_originais(
                    removidos_bairros_invalidos,
                    mapeamento_colunas_saida,
                    colunas_originais
                )
                removidos_inicio_numero = restaurar_nomes_originais(
                    removidos_inicio_numero,
                    mapeamento_colunas_saida,
                    colunas_originais
                )
                removidos_numericos = restaurar_nomes_originais(
                    removidos_numericos,
                    mapeamento_colunas_saida,
                    colunas_originais
                )
                removidos_curtos = restaurar_nomes_originais(
                    removidos_curtos,
                    mapeamento_colunas_saida,
                    colunas_originais
                )
                removidos_teste = restaurar_nomes_originais(
                    removidos_teste,
                    mapeamento_colunas_saida,
                    colunas_originais
                )
                removidos_telefones_bloqueados = restaurar_nomes_originais(
                    removidos_telefones_bloqueados,
                    mapeamento_colunas_saida,
                    colunas_originais
                )

                st.session_state[
                    "dados_limpos"
                ] = dados

                st.session_state[
                    "relatorios"
                ] = {

                    "sem_bairro":
                        removidos_sem_bairro,

                    "bairros_invalidos":
                        removidos_bairros_invalidos,

                    "inicio_numero":
                        removidos_inicio_numero,

                    "numericos":
                        removidos_numericos,

                    "curtos":
                        removidos_curtos,

                    "teste":
                        removidos_teste,

                    "telefones_bloqueados":
                        removidos_telefones_bloqueados,
                }

                st.session_state[
                    "estatisticas"
                ] = {

                    "originais":
                        len(dados_original),

                    "sem_bairro":
                        len(removidos_sem_bairro),

                    "bairros_invalidos":
                        len(removidos_bairros_invalidos),

                    "inicio_numero":
                        len(removidos_inicio_numero),

                    "numericos":
                        len(removidos_numericos),

                    "curtos":
                        len(removidos_curtos),

                    "teste":
                        len(removidos_teste),

                    "telefones_bloqueados":
                        len(removidos_telefones_bloqueados),

                    "removidos":
                        total_removidos,

                    "finais":
                        len(dados),
                }

                st.success(
                    "Processamento concluído!"
                )

        except Exception as erro:

            st.error(
                f"Não foi possível processar o arquivo: {erro}"
            )




# ============================================================
# RESULTADO DA LIMPEZA
# ============================================================
def mostrar_resultado_limpeza():

    if (
        "dados_limpos" in st.session_state
    ):

        dados_limpos = (
            st.session_state["dados_limpos"]
        )

        stats = (
            st.session_state["estatisticas"]
        )

        relatorios = (
            st.session_state["relatorios"]
        )

        st.subheader("Resultado")

        m1, m2, m3 = st.columns(3)

        m1.metric(
            "Registros originais",
            stats["originais"]
        )

        m2.metric(
            "Registros removidos",
            stats["removidos"]
        )

        m3.metric(
            "Registros finais",
            stats["finais"]
        )

        st.write("### Detalhamento")

        detalhes = pd.DataFrame({

            "Regra": [

                "Sem bairro",

                "Bairro não encontrado na base oficial",

                "Nome iniciado por número",

                "Nome somente numérico",

                "Nome muito curto",

                "Nome contendo TESTE/TEST",

                "Telefone com prefixo bloqueado",

            ],

            "Registros encontrados/removidos": [

                stats["sem_bairro"],

                stats["bairros_invalidos"],

                stats["inicio_numero"],

                stats["numericos"],

                stats["curtos"],

                stats["teste"],

                stats["telefones_bloqueados"],

            ],
        })

        st.dataframe(
            detalhes,
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        st.write(
            "### ⬇️ Arquivos separados"
        )

        arquivos_relatorios = [

            (
                "sem_bairro",
                "📍 BAIXAR REGISTROS SEM BAIRRO",
                "registros_sem_bairro.csv"
            ),

            (
                "bairros_invalidos",
                "🏘️ BAIXAR BAIRROS NÃO ENCONTRADOS",
                "registros_bairros_invalidos.csv"
            ),

            (
                "inicio_numero",
                "🔢 BAIXAR NOMES INICIADOS POR NÚMERO",
                "registros_nomes_com_numero.csv"
            ),

            (
                "numericos",
                "🔢 BAIXAR NOMES SOMENTE NUMÉRICOS",
                "registros_nomes_numericos.csv"
            ),

            (
                "curtos",
                "✏️ BAIXAR NOMES MUITO CURTOS",
                "registros_nomes_muito_curtos.csv"
            ),

            (
                "teste",
                "🧪 BAIXAR NOMES COM TESTE/TEST",
                "registros_nomes_teste.csv"
            ),

            (
                "telefones_bloqueados",
                "📞 BAIXAR TELEFONES COM PREFIXO BLOQUEADO",
                "registros_telefones_prefixos_bloqueados.csv"
            ),
        ]

        for (
            chave,
            rotulo,
            nome_arquivo
        ) in arquivos_relatorios:

            df = relatorios[chave]

            if len(df) > 0:

                csv_relatorio = df.to_csv(
                    sep=";",
                    index=False,
                    encoding="utf-8-sig"
                )

                st.download_button(

                    label=f"{rotulo} ({len(df)} registros)",

                    data=csv_relatorio,

                    file_name=nome_arquivo,

                    mime="text/csv",

                    use_container_width=True,

                    key=f"download_{chave}"
                )

        st.write(
            "### Prévia da base limpa"
        )

        st.dataframe(
            dados_limpos.head(50),
            use_container_width=True,
            hide_index=True
        )

        csv_limpo = dados_limpos.to_csv(
            sep=";",
            index=False,
            encoding="utf-8-sig"
        )

        st.download_button(

            label="⬇️ BAIXAR CSV LIMPO",

            data=csv_limpo,

            file_name="arquivo_limpo.csv",

            mime="text/csv",

            type="primary",

            use_container_width=True,

            key="download_csv_limpo"
        )


# ============================================================
# NAVEGAÇÃO
# ============================================================

with st.sidebar:
    st.markdown("## 🧹 Data Cleaner")
    st.caption("Limpeza, padronização e auditoria de dados.")
    st.divider()
    pagina = st.radio(
        "Ferramenta",
        ["🧹  Limpeza de base", "⏱️  Cálculo de TMD"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("Dica: arquivos CSV com separador ; ou , são detectados automaticamente.")

if pagina.startswith("🧹"):
    executar_limpeza()
    if "dados_limpos" in st.session_state:
        st.divider()
        mostrar_resultado_limpeza()
else:
    executar_tmd()
