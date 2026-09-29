import hashlib
import hmac
import html
import os
import re
import time

import pandas as pd
import streamlit as st

from tmd_calculation import (
    COLUNAS_NECESSARIAS,
    COLUNAS_PAUSAS,
    COLUNAS_PENDENCIAS,
    EQUIVALENCIAS_CHAMADAS,
    MAX_CSV_BYTES,
    NOMES_TIPO,
    ErroTMD,
    calcular_tmd_comparativo_dos_csvs,
    classificar_csv,
    corrigir_csvs_com_horarios,
    csv_seguro,
    diagnosticar_tmd,
    formatar_horario,
    validar_horario,
)

MSG_ERRO_GENERICO = (
    "Não foi possível processar os arquivos. Verifique se são os CSVs "
    "corretos de Sessões em Filas e de Pausas."
)
MAX_TENTATIVAS_SENHA = 5


# =============================
# CONFIGURAÇÃO DA PÁGINA
# =============================
st.set_page_config(
    page_title="Cálculo de TMD",
    page_icon="⏱️",
    layout="wide",
)

# Sem fontes externas: nenhuma requisição sai do navegador para terceiros.
st.markdown(
    """
    <style>
    :root {
        --bg: #0b1020; --surface: #121a2e; --surface-2: #18223b;
        --border: rgba(148, 163, 184, 0.14); --text: #e6ebf5;
        --muted: #8b97b0; --primary: #5eead4; --primary-2: #22d3ee;
        --radius: 16px;
    }
    html, body, [class*="css"], [data-testid="stAppViewContainer"] {
        font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        color: var(--text);
    }
    [data-testid="stAppViewContainer"] { background: var(--bg); }
    [data-testid="stHeader"] { background: transparent; }
    .block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1200px; }
    h1, h2, h3 { color: #f8fafc !important; letter-spacing: -0.02em; font-weight: 800 !important; }
    [data-testid="stCaptionContainer"] { color: var(--muted) !important; }

    .hero {
        background: linear-gradient(135deg, var(--surface), var(--surface-2));
        border: 1px solid var(--border); border-radius: 22px;
        padding: 1.8rem 2rem; margin-bottom: 1.6rem;
    }
    .hero .tag {
        display: inline-block; font-size: .72rem; letter-spacing: .08em;
        text-transform: uppercase; color: var(--primary);
        background: rgba(94,234,212,0.1); border: 1px solid rgba(94,234,212,0.25);
        padding: .25rem .6rem; border-radius: 999px; margin-bottom: .8rem;
    }
    .hero h1 { font-size: 2rem !important; margin: 0 0 .3rem 0 !important; padding: 0 !important; }
    .hero p { color: var(--muted); margin: 0; font-size: 1rem; }
    .steps { display: flex; gap: .6rem; flex-wrap: wrap; margin-top: 1.1rem; }
    .step {
        background: rgba(8,12,24,0.5); border: 1px solid var(--border);
        border-radius: 999px; padding: .35rem .8rem; font-size: .82rem;
    }
    .step b { color: var(--primary); margin-right: .35rem; }

    .stButton > button, .stDownloadButton > button {
        border-radius: 12px; font-weight: 700; padding: .65rem 1.1rem;
    }
    .stButton > button {
        border: none; color: #04202a;
        background: linear-gradient(135deg, var(--primary), var(--primary-2));
    }
    .stButton > button:hover { color: #04202a; }
    .stDownloadButton > button {
        background: var(--surface); color: var(--text); border: 1px solid var(--border);
    }
    [data-testid="stFileUploader"] section {
        background: var(--surface); border: 1.5px dashed rgba(94,234,212,0.35);
        border-radius: var(--radius); padding: 1.4rem;
    }
    [data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
    [data-testid="stExpander"] { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
    .stTextInput input { background: var(--surface) !important; border-radius: 10px !important; }
    .stAlert { border-radius: 12px; border: 1px solid var(--border); }
    hr { border-color: var(--border) !important; margin: 1.6rem 0 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def hero(tag, titulo, descricao, passos=None):
    # Todo texto é escapado antes de entrar no HTML.
    e = html.escape
    passos_html = ""
    if passos:
        passos_html = '<div class="steps">' + "".join(
            f'<span class="step"><b>{i}</b>{e(p)}</span>'
            for i, p in enumerate(passos, 1)
        ) + "</div>"
    st.markdown(
        f'<div class="hero"><span class="tag">{e(tag)}</span>'
        f"<h1>{e(titulo)}</h1><p>{e(descricao)}</p>{passos_html}</div>",
        unsafe_allow_html=True,
    )


# ============================================================
# ACESSO E PRIVACIDADE
# ============================================================

def _senha_configurada():
    senha = os.environ.get("APP_PASSWORD")
    if senha:
        return senha
    try:
        return st.secrets.get("APP_PASSWORD")
    except Exception:
        return None


def exigir_acesso():
    """Bloqueia o app com senha quando APP_PASSWORD estiver definida."""
    senha = _senha_configurada()
    if not senha or st.session_state.get("_autenticado"):
        return

    st.subheader("Acesso restrito")
    tentativas = st.session_state.get("_tentativas", 0)
    if tentativas >= MAX_TENTATIVAS_SENHA:
        st.error("Muitas tentativas. Recarregue a página para tentar novamente.")
        st.stop()

    digitada = st.text_input("Senha de acesso", type="password")
    if st.button("Entrar"):
        if hmac.compare_digest(digitada.encode(), str(senha).encode()):
            st.session_state["_autenticado"] = True
            st.rerun()
        st.session_state["_tentativas"] = tentativas + 1
        time.sleep(1)
        st.error("Senha incorreta.")
    st.stop()


def limpar_dados_da_sessao():
    """Apaga resultados e uploads da memória da sessão."""
    ciclo = st.session_state.get("_ciclo", 0) + 1
    autenticado = st.session_state.get("_autenticado", False)
    st.session_state.clear()
    st.session_state["_ciclo"] = ciclo  # muda a chave dos uploaders
    if autenticado:
        st.session_state["_autenticado"] = True


def _nome_seguro(nome):
    return re.sub(r"[^\w.\- ]", "", str(nome))[:80]


# ============================================================
# ENVIO E IDENTIFICAÇÃO DOS ARQUIVOS
# ============================================================

CHAVES_RESULTADO = (
    "resultado_tmd", "resultado_tmd_comparativo", "resultado_tmd_diario",
    "horarios_faltantes", "_assinatura", "_entrada", "_corrigidos",
    "_horarios_informados", "_form_auto", "_msg",
)


def _limpar_resultados():
    for chave in CHAVES_RESULTADO:
        st.session_state.pop(chave, None)


def _classificar_uploads(arquivos):
    """Identifica cada CSV pelas colunas (o nome do arquivo não importa)."""
    cache = st.session_state.setdefault("_classificacao", {})
    grupos = {"sessoes": {}, "pausas": {}}
    resumo, avisos = [], []
    for arquivo in arquivos:
        nome = _nome_seguro(arquivo.name)
        if arquivo.size > MAX_CSV_BYTES:
            avisos.append(
                f"{nome}: excede o limite de {MAX_CSV_BYTES // (1024 * 1024)} MB."
            )
            continue
        conteudo = arquivo.getvalue()
        assinatura = hashlib.sha256(conteudo).hexdigest()
        if assinatura not in cache:
            try:
                tipo, linhas = classificar_csv(conteudo)
                cache[assinatura] = ("ok", tipo, linhas)
            except ErroTMD as erro:
                cache[assinatura] = ("erro", str(erro), 0)
            except Exception:
                cache[assinatura] = ("erro", MSG_ERRO_GENERICO, 0)
        estado, valor, linhas = cache[assinatura]
        if estado == "ok":
            grupos[valor][assinatura] = conteudo  # o mesmo arquivo 2x conta 1x
            resumo.append(
                {"Arquivo": nome, "Identificado como": NOMES_TIPO[valor],
                 "Linhas": linhas}
            )
        else:
            resumo.append(
                {"Arquivo": nome, "Identificado como": "Não reconhecido",
                 "Linhas": 0}
            )
            avisos.append(f"{nome}: {valor}")
    return grupos, resumo, avisos


# ============================================================
# CÁLCULO DE TMD
# ============================================================

def _formatar_duracao(segundos):
    segundos = max(0, int(round(segundos)))
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"


def unificar_tmd_por_equipe(resultado_diario):
    if resultado_diario is None or resultado_diario.empty:
        return pd.DataFrame(columns=["Equipe", "TMD total do período"])

    dados = resultado_diario.copy()
    dados["_segundos"] = pd.to_timedelta(
        dados["TMD"], errors="coerce"
    ).dt.total_seconds()
    resumo = (
        dados.dropna(subset=["_segundos"])
        .groupby("Equipe", as_index=False)["_segundos"]
        .sum()
    )
    resumo["TMD total do período"] = resumo["_segundos"].map(_formatar_duracao)
    return resumo[["Equipe", "TMD total do período"]]


def formatar_horario_digitado(valor):
    """24092026173000 -> 24/09/2026 17:30:00 (aceita digitação parcial)."""
    digitos = re.sub(r"\D", "", str(valor))[:14]
    partes, inicio = [], 0
    for limite in (2, 2, 4, 2, 2, 2):
        parte = digitos[inicio:inicio + limite]
        if not parte:
            break
        partes.append(parte)
        inicio += limite
    if len(partes) <= 3:
        return "/".join(partes)
    return "/".join(partes[:3]) + " " + ":".join(partes[3:])


def aplicar_mascara_horario(chave):
    st.session_state[chave] = formatar_horario_digitado(
        st.session_state.get(chave, "")
    )


def _calcular_e_guardar(sessoes, pausas, ajustes=None):
    comparativo, pendencias = calcular_tmd_comparativo_dos_csvs(
        sessoes, pausas, ajustes
    )
    diario = comparativo.rename(columns={"TMD corrigido": "TMD"})[
        ["Data", "Equipe", "TMD"]
    ]
    st.session_state.update(
        resultado_tmd_comparativo=comparativo,
        horarios_faltantes=pendencias,
        resultado_tmd_diario=diario,
        resultado_tmd=unificar_tmd_por_equipe(diario),
        _corrigidos=corrigir_csvs_com_horarios(sessoes, pausas, ajustes),
    )


def _botao_download(rotulo, dados, arquivo, chave):
    st.download_button(
        rotulo,
        data=csv_seguro(dados),
        file_name=arquivo,
        mime="text/csv",
        key=chave,
    )


# ============================================================
# CAIXA PARA PREENCHER HORÁRIOS FALTANDO
# ============================================================

# Texto fixo (nunca contém dados do arquivo) para orientar o preenchimento.
ROTULOS = {
    "Logout": {
        "titulo": "Saída (Logout) não registrada",
        "campo": "Que horas saiu? (Logout)",
        "instrucao": (
            "Entrou em **{ref}**, mas o horário de saída não está no arquivo.  \n"
            "Digite **a que horas saiu** — precisa ser depois de {ref}."
        ),
        "destino": "Será gravado na coluna **Logout** do arquivo de Sessões.",
    },
    "Login": {
        "titulo": "Entrada (Login) não registrada",
        "campo": "Que horas entrou? (Login)",
        "instrucao": (
            "A saída foi registrada em **{ref}**, mas o horário de entrada "
            "não está no arquivo.  \n"
            "Digite **a que horas entrou** — precisa ser antes de {ref}."
        ),
        "destino": "Será gravado na coluna **Login** do arquivo de Sessões.",
    },
    "Retorno da pausa": {
        "titulo": "Retorno da pausa não registrado",
        "campo": "Que horas voltou da pausa?",
        "instrucao": (
            "Iniciou a pausa em **{ref}**, mas o retorno não está no arquivo.  \n"
            "Digite **a que horas voltou** — precisa ser depois de {ref}."
        ),
        "destino": (
            "O tempo da pausa (do início até o retorno) será gravado na "
            "coluna **Tempo em Pausa** do arquivo de Pausas."
        ),
    },
}


def _chave_pendencia(registro):
    bruto = "|".join(str(registro[c]) for c in COLUNAS_PENDENCIAS)
    return hashlib.md5(bruto.encode()).hexdigest()[:12]


def _conteudo_formulario():
    pendencias = st.session_state["horarios_faltantes"]
    total = len(pendencias)
    salvos = st.session_state.get("_horarios_informados", {})

    st.markdown(
        "Sem estes horários o TMD sai errado (sessões abertas não são "
        "contadas e pausas sem retorno não são descontadas). "
        "**Preencha os que você souber** — o que ficar em branco continua "
        "sem correção."
    )
    st.info(
        "**Como preencher:** digite só os números — o app coloca as barras "
        "e os dois-pontos sozinho.  \n"
        "**Ordem:** DIA / MÊS / ANO  HORA : MINUTO : SEGUNDO  \n"
        "**Exemplo:** para 24/09/2026 17:30:00 digite `24092026173000`"
    )
    progresso = st.empty()

    valores, validos, invalidos = {}, 0, 0
    for posicao, (_, registro) in enumerate(pendencias.iterrows(), start=1):
        chave = _chave_pendencia(registro)
        campo = registro["Horário faltando"]
        rotulo = ROTULOS[campo]
        ref = formatar_horario(registro["Horário registrado"]) or "horário registrado"
        exemplo = ref[:10] if "/" in ref[:10] else "DD/MM/AAAA"

        with st.container(border=True):
            st.markdown(f"**{posicao} de {total} · {rotulo['titulo']}**")
            st.text(f"Colaborador: {registro['Agente']}")
            st.text(
                f"{'Fila' if registro['Tipo'] == 'Sessão' else 'Pausa'}: "
                f"{registro['Fila / Motivo']}"
            )
            st.markdown(rotulo["instrucao"].format(ref=ref))

            widget = f"hora_{chave}"
            if widget not in st.session_state:
                st.session_state[widget] = salvos.get(chave, "")
            texto = st.text_input(
                rotulo["campo"],
                key=widget,
                placeholder=f"Ex.: {exemplo} 17:30:00",
                on_change=aplicar_mascara_horario,
                args=(widget,),
            )
            status, mensagem = validar_horario(
                campo, registro["Horário registrado"], texto
            )
            if status == "ok":
                st.caption("✅ Horário válido. " + rotulo["destino"])
                validos += 1
                valores[chave] = texto.strip()
            elif status == "erro":
                st.warning(mensagem)
                invalidos += 1
            else:
                st.caption("Em branco — este horário continuará faltando.")

    progresso.progress(
        validos / total,
        text=f"Preenchidos e válidos: {validos} de {total}",
    )

    if st.button("Aplicar horários e recalcular TMD", type="primary",
                 key="aplicar_horarios"):
        if invalidos:
            st.error("Corrija os campos com aviso amarelo antes de aplicar.")
        elif not validos:
            st.warning("Preencha ao menos um horário.")
        else:
            entrada = st.session_state["_entrada"]
            ajustes = pendencias.copy()
            ajustes["Horário informado"] = [
                valores.get(_chave_pendencia(r), "")
                for _, r in pendencias.iterrows()
            ]
            try:
                _calcular_e_guardar(entrada["sessoes"], entrada["pausas"], ajustes)
            except ErroTMD as erro:
                st.error(str(erro))
                return
            except Exception:
                st.error(MSG_ERRO_GENERICO)
                return
            st.session_state["_horarios_informados"] = valores
            st.session_state["_msg"] = (
                f"{validos} horário(s) aplicado(s) e TMD recalculado."
            )
            st.rerun()


if hasattr(st, "dialog"):
    @st.dialog("Horários faltando — preencha para corrigir o TMD", width="large")
    def abrir_formulario():
        _conteudo_formulario()
else:  # Streamlit antigo: mostra a caixa na própria página
    def abrir_formulario():
        with st.container(border=True):
            _conteudo_formulario()


def _secao_pendencias(pendencias, assinatura):
    informados = st.session_state.get("_horarios_informados", {})
    tabela = pendencias.copy()
    tabela["Situação"] = [
        "✅ Preenchido" if _chave_pendencia(r) in informados else "⏳ Faltando"
        for _, r in pendencias.iterrows()
    ]
    faltam = int((tabela["Situação"] == "⏳ Faltando").sum())

    st.subheader("Horários faltando nos arquivos")
    if faltam:
        st.warning(
            f"{faltam} horário(s) faltando. Clique em **Preencher horários** "
            "para informar; o TMD será recalculado com eles."
        )
    else:
        st.success("Todos os horários faltantes foram preenchidos.")
    st.dataframe(tabela, use_container_width=True, hide_index=True)

    if st.button("Preencher horários", type="primary", key="abrir_formulario"):
        abrir_formulario()
    elif st.session_state.get("_form_auto") != assinatura:
        st.session_state["_form_auto"] = assinatura  # abre sozinho só 1 vez
        abrir_formulario()


# ============================================================
# TELA PRINCIPAL
# ============================================================

def executar_tmd():
    hero(
        "Atendimento",
        "Cálculo automático de TMD",
        "Tempo médio de disponibilidade: tempo logado menos as pausas, "
        "para Retenção e Cobrança.",
        ["Envie os CSVs", "Preencha horários faltando", "Confira o resultado"],
    )

    ciclo = st.session_state.get("_ciclo", 0)
    arquivos = st.file_uploader(
        "Envie os arquivos CSV (Sessões em Filas e Pausas)",
        type=["csv", "txt"],
        accept_multiple_files=True,
        key=f"tmd_arquivos_{ciclo}",
        help="Pode enviar todos de uma vez, com qualquer nome e em qualquer ordem.",
    )
    st.caption(
        "O nome do arquivo não importa: o app identifica cada um pelas "
        "colunas. Colunas a mais são ignoradas. Se houver mais de um arquivo "
        "do mesmo tipo, eles são somados."
    )
    with st.expander("Quais colunas o app procura?"):
        for nome, colunas in COLUNAS_NECESSARIAS.items():
            st.markdown(f"**{nome}:** " + ", ".join(f"`{c}`" for c in colunas))
        st.markdown(
            "**Arquivo unificado de Pausas (saída):** "
            + ", ".join(f"`{c}`" for c in COLUNAS_PAUSAS)
        )
        st.markdown(
            "**Arquivo de chamadas** (ex.: *Chamadas - Detalhado Atendidas*) "
            "também é aceito. Suas colunas viram as de Pausas:"
        )
        st.dataframe(
            pd.DataFrame(
                {"Coluna do arquivo de chamadas": list(EQUIVALENCIAS_CHAMADAS),
                 "Vira a coluna": list(EQUIVALENCIAS_CHAMADAS.values())}
            ),
            hide_index=True,
        )
        st.caption(
            "Maiúsculas, acentos e a ordem das colunas não fazem diferença. "
            "Colunas que existirem só em um dos arquivos ficam em branco "
            "no outro."
        )

    if not arquivos:
        _limpar_resultados()
        st.info("Envie os arquivos para calcular o TMD.")
        return

    grupos, resumo, avisos = _classificar_uploads(arquivos)
    st.dataframe(pd.DataFrame(resumo), use_container_width=True, hide_index=True)
    for aviso in avisos:
        st.warning(aviso)
    if not grupos["sessoes"]:
        st.info("Falta o arquivo de **Sessões em Filas** para calcular.")
        return
    if not grupos["pausas"]:
        st.info("Falta o arquivo de **Pausas** para calcular.")
        return

    sessoes = [grupos["sessoes"][h] for h in sorted(grupos["sessoes"])]
    pausas = [grupos["pausas"][h] for h in sorted(grupos["pausas"])]
    assinatura = hashlib.sha256(
        "|".join(sorted(grupos["sessoes"]) + ["#"] + sorted(grupos["pausas"])).encode()
    ).hexdigest()

    if st.session_state.get("_assinatura") != assinatura:  # arquivos novos
        _limpar_resultados()
        try:
            with st.spinner("Calculando o TMD..."):
                _calcular_e_guardar(sessoes, pausas)
        except ErroTMD as erro:
            st.error(str(erro))
            return
        except Exception:
            st.error(MSG_ERRO_GENERICO)
            return
        st.session_state["_assinatura"] = assinatura
        st.session_state["_entrada"] = {"sessoes": sessoes, "pausas": pausas}

    with st.expander("Verificação dos arquivos carregados"):
        try:
            diag = diagnosticar_tmd(sessoes, pausas)
            st.write(
                f"Sessões: {diag['sessoes_lidas']} linhas lidas → "
                f"{diag['sessoes_unicas']} sem duplicidade "
                f"({diag['intervalos_validos']} com login e logout válidos)"
            )
            st.write(
                f"Pausas: {diag['pausas_lidas']} linhas somadas dos arquivos "
                f"({diag['chamadas_lidas']} vindas do arquivo de chamadas) → "
                f"{diag['pausas_unicas']} sem duplicidade"
            )
            st.write(
                f"Colunas extras ignoradas nas sessões: "
                f"{diag['colunas_extras_ignoradas']}"
            )
            st.write("Filas encontradas:", diag["filas"])
            st.write("Direções encontradas:", diag["direcoes_sessoes"])
            st.caption("Amostra das sessões")
            st.dataframe(
                diag["amostra_sessoes"], use_container_width=True, hide_index=True
            )
            st.caption("Amostra das pausas unificadas")
            st.dataframe(
                diag["amostra_pausas"], use_container_width=True, hide_index=True
            )
        except ErroTMD as erro:
            st.error(str(erro))
        except Exception:
            st.error(MSG_ERRO_GENERICO)

    mensagem = st.session_state.pop("_msg", None)
    if mensagem:
        st.success(mensagem)

    pendencias = st.session_state["horarios_faltantes"]
    if not pendencias.empty:
        _secao_pendencias(pendencias, assinatura)

    resultado = st.session_state["resultado_tmd"]
    if resultado.empty:
        st.warning(
            "Ainda não há resultado. "
            + (
                "Preencha os horários faltando acima."
                if not pendencias.empty
                else "Verifique as datas e os nomes das filas."
            )
        )
    else:
        st.subheader("Resultado do cálculo")
        st.dataframe(resultado, use_container_width=True, hide_index=True)
        with st.expander("Ver resultado detalhado por dia"):
            st.dataframe(
                st.session_state["resultado_tmd_diario"],
                use_container_width=True,
                hide_index=True,
            )
        st.subheader("Comparativo do cálculo")
        st.caption(
            "Sem correção: filas e registros duplicados são somados. "
            "Corrigido: sessões simultâneas e pausas duplicadas são unidas, "
            "e os horários que você preencheu são aplicados."
        )
        st.dataframe(
            st.session_state["resultado_tmd_comparativo"],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader("Downloads")
    if not resultado.empty:
        _botao_download(
            "Baixar resultado TMD", resultado, "tmd_diario.csv", "download_tmd"
        )
        _botao_download(
            "Baixar comparativo TMD",
            st.session_state["resultado_tmd_comparativo"],
            "tmd_comparativo.csv", "download_tmd_comparativo",
        )
    if not pendencias.empty:
        _botao_download(
            "Baixar lista de horários faltando", pendencias,
            "horarios_faltando.csv", "download_pendencias",
        )
    corrigidos = st.session_state.get("_corrigidos")
    if corrigidos is not None:
        sessoes_finais, pausas_finais = corrigidos
        preenchido = bool(st.session_state.get("_horarios_informados"))
        sufixo = " (com os horários preenchidos)" if preenchido else ""
        _botao_download(
            "Baixar pausas unificadas" + sufixo, pausas_finais[COLUNAS_PAUSAS],
            "pausas_unificadas.csv", "download_pausas_unificadas",
        )
        _botao_download(
            "Baixar sessões sem duplicidade" + sufixo, sessoes_finais,
            "sessoes_sem_duplicidade.csv", "download_sessoes_limpas",
        )
    if st.session_state.get("_horarios_informados"):
        st.button(
            "Descartar horários preenchidos e recalcular",
            on_click=lambda: _limpar_resultados(),
            help="Volta ao cálculo original dos arquivos.",
        )


exigir_acesso()
executar_tmd()
st.divider()
st.button(
    "Limpar dados desta sessão",
    on_click=limpar_dados_da_sessao,
    help="Apaga arquivos enviados e resultados da memória do app.",
)
