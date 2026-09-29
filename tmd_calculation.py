import csv
import io
import re
import unicodedata

import pandas as pd


MAX_CSV_BYTES = 20 * 1024 * 1024


class ErroTMD(ValueError):
    """Erro com mensagem segura para exibir ao usuário (sem dados do CSV)."""


NOMES_TIPO = {"sessoes": "Sessões em Filas", "pausas": "Pausas"}

# Nome oficial da coluna -> outros nomes aceitos. A comparação ignora
# maiúsculas, acentos, espaços e pontuação ("Data/Hora" = "data hora").
SESSOES_ALIASES = {
    "Agente": {"colaborador", "atendente", "nome do agente", "nome agente"},
    "Fila": {"nome da fila", "filas"},
    "Login": {"data login", "data hora login", "inicio da sessao"},
    "Direção": set(),
    "Logout": {"data logout", "data hora logout", "fim da sessao"},
    "Tempo Logado": {"tempo de login", "duracao logado"},
}

PAUSAS_ALIASES = {
    "Data/Hora": {"data e hora", "datahora", "data hora da pausa"},
    "Agente": SESSOES_ALIASES["Agente"],
    "Direção": set(),
    "Pausa": {"motivo", "motivo da pausa", "tipo de pausa"},
    "Tempo em Pausa": {"tempo de pausa", "duracao da pausa", "tempo pausa"},
}

_ALIASES_POR_TIPO = {"sessoes": SESSOES_ALIASES, "pausas": PAUSAS_ALIASES}
COLUNAS_NECESSARIAS = {
    NOMES_TIPO[tipo]: list(aliases)
    for tipo, aliases in _ALIASES_POR_TIPO.items()
}

RETENCAO_FILAS = {
    "SAC CANCELAMENTO",
    "REGIAO 1 - CANCELAMENTO",
}

NEGOCIACAO_FILAS = {
    "COBRANCA INTERNO",
    "DISCADOR COBRANCA CS",
    "REGIAO 1 - COBRANCA",
}


def _texto_normalizado(valor):
    texto = "" if pd.isna(valor) else str(valor).strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"\s+", " ", texto).upper()


def _norm_col(nome):
    texto = unicodedata.normalize(
        "NFKD", str(nome).replace("\ufeff", "").strip().lower()
    )
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def _posicoes(colunas, aliases):
    """Posição de cada coluna necessária, encontrada pelo nome."""
    posicoes, usadas = {}, set()
    for canonico, outros in aliases.items():
        alvo = {_norm_col(canonico)} | {_norm_col(o) for o in outros}
        for i, coluna in enumerate(colunas):
            if i not in usadas and _norm_col(coluna) in alvo:
                posicoes[canonico] = i
                usadas.add(i)
                break
    return posicoes


def _padronizar(dados, aliases, nome):
    """Renomeia as colunas necessárias e mantém as extras sem interferir."""
    colunas = list(dados.columns)
    posicoes = _posicoes(colunas, aliases)
    ausentes = [c for c in aliases if c not in posicoes]
    if ausentes:
        encontradas = ", ".join(str(c) for c in colunas[:15])
        raise ErroTMD(
            f"O arquivo de {nome} não possui as colunas: "
            f"{', '.join(ausentes)}. Colunas encontradas: {encontradas}."
        )
    novas = {c: dados.iloc[:, i] for c, i in posicoes.items()}
    usadas = set(posicoes.values())
    for i, coluna in enumerate(colunas):
        if i in usadas:
            continue
        rotulo = str(coluna)
        while rotulo in novas:
            rotulo += " (extra)"
        novas[rotulo] = dados.iloc[:, i]
    return pd.DataFrame(novas, index=dados.index)


def padronizar_sessoes(dados):
    return _padronizar(dados, SESSOES_ALIASES, "sessões em filas")


def padronizar_pausas(dados):
    return _padronizar(dados, PAUSAS_ALIASES, "pausas")


def _linhas_csv(conteudo):
    if hasattr(conteudo, "getvalue"):
        conteudo = conteudo.getvalue()
    if isinstance(conteudo, str):
        conteudo = conteudo.encode("utf-8")
    if not conteudo or not conteudo.strip():
        raise ErroTMD("O arquivo CSV está vazio.")
    if len(conteudo) > MAX_CSV_BYTES:
        raise ErroTMD(
            f"O arquivo excede o limite de {MAX_CSV_BYTES // (1024 * 1024)} MB."
        )

    texto = None
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            texto = conteudo.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ErroTMD("Não foi possível decodificar o CSV.")

    amostra = "\n".join(texto.splitlines()[:30])
    separador = max(";,\t|", key=amostra.count)
    try:
        linhas = [
            linha
            for linha in csv.reader(io.StringIO(texto), delimiter=separador)
            if any(celula.strip() for celula in linha)
        ]
    except csv.Error:
        raise ErroTMD("O arquivo não está em um formato CSV válido.") from None
    if not linhas:
        raise ErroTMD("O arquivo CSV está vazio.")
    return linhas


def _montar_dataframe(linhas, indice_cabecalho):
    cabecalho, vistos = [], {}
    for nome in linhas[indice_cabecalho]:
        nome = str(nome).replace("\ufeff", "").strip() or "Coluna"
        vistos[nome] = vistos.get(nome, 0) + 1
        cabecalho.append(nome if vistos[nome] == 1 else f"{nome} ({vistos[nome]})")
    corpo = linhas[indice_cabecalho + 1:]
    largura = max([len(cabecalho)] + [len(linha) for linha in corpo])
    cabecalho += [f"Coluna {n}" for n in range(len(cabecalho) + 1, largura + 1)]
    corpo = [linha + [""] * (largura - len(linha)) for linha in corpo]
    return pd.DataFrame(corpo, columns=cabecalho, dtype=str)


def _localizar_cabecalho(linhas, aliases):
    """Acha a linha do cabeçalho (aceita títulos antes da tabela)."""
    for i, linha in enumerate(linhas[:25]):
        if len(_posicoes(linha, aliases)) == len(aliases):
            return i
    return None


def carregar_csv(conteudo, tipo=None):
    """Lê um CSV de qualquer nome/ordem de colunas e devolve (tipo, dados)."""
    linhas = _linhas_csv(conteudo)
    tipos = [tipo] if tipo else list(_ALIASES_POR_TIPO)
    achados = {
        t: _localizar_cabecalho(linhas, _ALIASES_POR_TIPO[t]) for t in tipos
    }
    achados = {t: i for t, i in achados.items() if i is not None}

    if len(achados) == 1:
        t, i = next(iter(achados.items()))
        dados = _montar_dataframe(linhas, i)
        return t, _padronizar(dados, _ALIASES_POR_TIPO[t], NOMES_TIPO[t].lower())
    if len(achados) > 1:
        raise ErroTMD(
            "O arquivo tem colunas de Sessões em Filas e de Pausas ao mesmo "
            "tempo. Envie cada tipo em um arquivo separado."
        )
    if tipo:  # levanta o erro com a lista de colunas que faltam
        _padronizar(
            _montar_dataframe(linhas, 0),
            _ALIASES_POR_TIPO[tipo],
            NOMES_TIPO[tipo].lower(),
        )
    necessarias = "; ".join(
        f"{NOMES_TIPO[t]}: {', '.join(a)}" for t, a in _ALIASES_POR_TIPO.items()
    )
    raise ErroTMD(
        "Não reconheci este arquivo. Ele precisa ter as colunas de um destes "
        f"tipos — {necessarias}."
    )


def classificar_csv(conteudo):
    """Identifica o tipo do arquivo pelas colunas. Devolve (tipo, nº de linhas)."""
    tipo, dados = carregar_csv(conteudo)
    return tipo, len(dados)


def _ler_tipo(conteudo, tipo):
    itens = conteudo if isinstance(conteudo, (list, tuple)) else [conteudo]
    if not itens:
        raise ErroTMD(f"Nenhum arquivo de {NOMES_TIPO[tipo].lower()} foi enviado.")
    quadros = [carregar_csv(item, tipo)[1] for item in itens]
    if len(quadros) == 1:
        return quadros[0]
    return pd.concat(quadros, ignore_index=True).fillna("")


def _dataserie(valores):
    valores = valores.astype(str).str.strip()
    valores = valores.replace({"": pd.NA, "nan": pd.NA, "NaT": pd.NA})
    try:
        return pd.to_datetime(
            valores,
            errors="coerce",
            dayfirst=True,
            format="mixed",
        )
    except (TypeError, ValueError):
        return pd.to_datetime(valores, errors="coerce", dayfirst=True)


def _duracao_em_segundos(valor):
    if valor is None or pd.isna(valor):
        return 0.0
    texto = str(valor).strip()
    if not texto:
        return 0.0
    partes = texto.split(":")
    if len(partes) in (2, 3):
        try:
            numeros = [float(parte.replace(",", ".")) for parte in partes]
            if len(numeros) == 2:
                return numeros[0] * 60 + numeros[1]
            return numeros[0] * 3600 + numeros[1] * 60 + numeros[2]
        except ValueError:
            pass
    duracao = pd.to_timedelta(texto, errors="coerce")
    if pd.notna(duracao):
        return float(duracao.total_seconds())
    try:
        return float(texto.replace(",", "."))
    except ValueError:
        return 0.0


def _equipe(fila):
    fila_normalizada = _texto_normalizado(fila)
    compacta = re.sub(r"[^A-Z0-9]", "", fila_normalizada)
    fila_oficial = re.sub(r"\s+", " ", fila_normalizada)
    if (
        fila_oficial in RETENCAO_FILAS
        or "RETENCAO" in compacta
        or "CANCELAMENTO" in compacta
    ):
        return "RETENÇÃO"
    if (
        fila_oficial in NEGOCIACAO_FILAS
        or "NEGOCIACAO" in compacta
        or "COBRANCA" in compacta
    ):
        return "NEGOCIAÇÃO"
    return None


def _intervalos_sessoes(dados, pendentes=None):
    sessoes = dados.copy()
    sessoes["_agente"] = sessoes["Agente"].astype(str).str.strip()
    sessoes["_fila"] = sessoes["Fila"].astype(str).str.strip()
    sessoes["_equipe"] = sessoes["Fila"].map(_equipe)
    sessoes["_login"] = _dataserie(sessoes["Login"])
    sessoes["_logout"] = _dataserie(sessoes["Logout"])
    sessoes["_login_txt"] = sessoes["Login"].astype(str).str.strip()
    sessoes["_logout_txt"] = sessoes["Logout"].astype(str).str.strip()
    sessoes["_duracao"] = (
        sessoes["Tempo Logado"].map(_duracao_em_segundos).astype(float)
    )
    sessoes["_direcao"] = sessoes["Direção"].map(_texto_normalizado)
    sessoes = sessoes[
        sessoes["_agente"].ne("") & sessoes["_equipe"].notna()
    ].sort_values(["_agente", "_fila", "_login", "_logout"])

    intervalos = []
    abertos = {}
    colunas_evento = [
        "_agente",
        "_fila",
        "_equipe",
        "_login",
        "_logout",
        "_direcao",
    ]
    colunas_evento += ["_duracao", "_login_txt", "_logout_txt"]
    for registro in sessoes[colunas_evento].itertuples(
        index=False, name=None
    ):
        (
            agente, fila, equipe, login, logout, direcao, duracao,
            login_txt, logout_txt,
        ) = registro
        chave = (agente, fila)
        eh_entrada = (
            "ENTRADA" in direcao
            or "INICIO" in direcao
            or "START" in direcao
        )
        eh_saida = (
            "SAIDA" in direcao
            or "FIM" in direcao
            or "EXIT" in direcao
        )

        if pd.notna(login) and pd.notna(logout):
            if logout > login:
                intervalos.append((agente, equipe, login, logout))
            continue

        if pd.notna(login) and duracao > 0 and not eh_saida:
            intervalos.append((
                agente,
                equipe,
                login,
                login + pd.Timedelta(seconds=duracao),
            ))
        elif pd.notna(login) and (eh_entrada or not eh_saida):
            abertos[chave] = (equipe, login, login_txt)
        elif pd.notna(logout) or eh_saida:
            fim = logout if pd.notna(logout) else login
            equipe_aberta, inicio, _ = abertos.pop(chave, (None, None, None))
            if inicio is not None and pd.notna(fim) and fim > inicio:
                intervalos.append((agente, equipe_aberta, inicio, fim))
            elif (
                inicio is None
                and pendentes is not None
                and pd.notna(logout)
                and pd.isna(login)
            ):
                pendentes.append(("Login", agente, fila, logout_txt))

    if pendentes is not None:
        for (agente, fila), (_, _, login_txt) in abertos.items():
            pendentes.append(("Logout", agente, fila, login_txt))

    intervalos = pd.DataFrame(
        intervalos,
        columns=["_agente", "_equipe", "_inicio", "_fim"],
    )
    return intervalos[
        intervalos["_fim"].gt(intervalos["_inicio"])
    ].copy()


def _unir_intervalos(intervalos):
    intervalos = list(intervalos)
    if not intervalos:
        return []
    intervalos = sorted(intervalos, key=lambda intervalo: intervalo[0])
    unidos = [list(intervalos[0])]
    for inicio, fim in intervalos[1:]:
        if inicio <= unidos[-1][1]:
            unidos[-1][1] = max(unidos[-1][1], fim)
        else:
            unidos.append([inicio, fim])
    return [(inicio, fim) for inicio, fim in unidos]


def _pausas_unicas(dados, pendentes=None):
    pausas = dados.copy()
    pausas["_agente"] = pausas["Agente"].astype(str).str.strip()
    pausas["_inicio"] = _dataserie(pausas["Data/Hora"])
    pausas["_inicio_txt"] = pausas["Data/Hora"].astype(str).str.strip()
    pausas["_motivo"] = pausas["Pausa"].astype(str).str.strip()
    pausas["_duracao"] = (
        pausas["Tempo em Pausa"].map(_duracao_em_segundos).astype(float)
    )
    pausas["_direcao"] = pausas["Direção"].map(_texto_normalizado)
    pausas = pausas[
        pausas["_agente"].ne("")
        & pausas["_inicio"].notna()
        & pausas["_motivo"].ne("")
    ].copy()

    pausas = pausas.drop_duplicates(
        subset=["_agente", "_inicio", "_motivo", "_duracao"]
    )
    resultado = []
    for (_, motivo), grupo in pausas.groupby(["_agente", "_motivo"]):
        aberturas = []
        colunas_evento = [
            "_agente",
            "_inicio",
            "_motivo",
            "_duracao",
            "_direcao",
            "_inicio_txt",
        ]
        for registro in grupo.sort_values("_inicio")[colunas_evento].itertuples(
            index=False, name=None
        ):
            (
                agente, inicio, motivo_registro, duracao_registro, direcao,
                inicio_txt,
            ) = registro
            eh_entrada = (
                "ENTRADA" in direcao
                or "INICIO" in direcao
                or "START" in direcao
            )
            eh_saida = (
                "SAIDA" in direcao
                or "FIM" in direcao
                or "EXIT" in direcao
            )
            if eh_saida and aberturas:
                entrada = aberturas.pop(0)
                duracao = entrada[2] or duracao_registro
                if not duracao:
                    duracao = (
                        inicio - entrada[1]
                    ).total_seconds()
                resultado.append((entrada[0], entrada[1], motivo, duracao))
            elif eh_entrada:
                aberturas.append((agente, inicio, duracao_registro, inicio_txt))
            elif duracao_registro > 0:
                resultado.append((
                    agente,
                    inicio,
                    motivo,
                    duracao_registro,
                ))
        resultado.extend(
            (entrada[0], entrada[1], motivo, entrada[2])
            for entrada in aberturas
            if entrada[2] > 0
        )
        if pendentes is not None:
            pendentes.extend(
                ("Retorno da pausa", entrada[0], motivo, entrada[3])
                for entrada in aberturas
                if entrada[2] <= 0
            )

    return pd.DataFrame(
        resultado,
        columns=["_agente", "_inicio", "_motivo", "_duracao"],
    ).drop_duplicates()


def _calcular_sobreposicao(inicio, fim, pausas):
    intervalos = []
    for pausa_inicio, duracao in pausas:
        pausa_fim = pausa_inicio + pd.Timedelta(seconds=duracao)
        if pausa_fim > inicio and pausa_inicio < fim:
            intervalos.append((
                max(pausa_inicio, inicio),
                min(pausa_fim, fim),
            ))
    return _unir_intervalos(intervalos)


def calcular_tmd(sessoes, pausas):
    """Calcula o TMD diário por equipe, sem duplicar filas ou pausas."""
    sessoes = padronizar_sessoes(sessoes)
    pausas = padronizar_pausas(pausas)

    intervalos = _intervalos_sessoes(sessoes)
    pausas_unicas = _pausas_unicas(pausas)
    if intervalos.empty:
        filas = sorted(
            str(valor).strip()
            for valor in sessoes["Fila"].dropna().unique()
        )
        raise ErroTMD(
            "Nenhuma sessão válida foi encontrada. Verifique as datas, "
            f"Login/Logout, Tempo Logado e as filas RETENÇÃO/NEGOCIAÇÃO. "
            f"Filas lidas: {', '.join(filas) or '[nenhuma]'}."
        )
    resultados = []

    for (agente, equipe), grupo in intervalos.groupby(["_agente", "_equipe"]):
        unidos = _unir_intervalos(
            grupo[["_inicio", "_fim"]].itertuples(index=False, name=None)
        )
        pausas_agente = pausas_unicas[pausas_unicas["_agente"].eq(agente)]
        dias = set()
        for inicio, fim in unidos:
            ultimo_instante = fim - pd.Timedelta(microseconds=1)
            dias.update(
                instante.date()
                for instante in pd.date_range(
                    inicio.normalize(),
                    ultimo_instante.normalize(),
                    freq="D",
                )
            )
        for data in sorted(dias):
            inicio_dia = pd.Timestamp(data)
            fim_dia = inicio_dia + pd.Timedelta(days=1)
            tempo_logado = 0.0
            pausas_no_dia = []
            for inicio, fim in unidos:
                inicio = max(inicio, inicio_dia)
                fim = min(fim, fim_dia)
                if fim <= inicio:
                    continue
                tempo_logado += (fim - inicio).total_seconds()
                pausas_no_dia.extend(
                    _calcular_sobreposicao(
                        inicio,
                        fim,
                        pausas_agente[["_inicio", "_duracao"]].itertuples(
                            index=False, name=None
                        ),
                    )
                )
            pausas_no_dia = _unir_intervalos(pausas_no_dia)
            disponibilidade = max(
                0.0,
                tempo_logado - sum(
                    (fim - inicio).total_seconds()
                    for inicio, fim in pausas_no_dia
                ),
            )
            resultados.append({
                "Data": data,
                "Equipe": equipe,
                "Agente": agente,
                "Disponibilidade": disponibilidade,
            })

    detalhes = pd.DataFrame(resultados)
    if detalhes.empty:
        return pd.DataFrame(columns=["Data", "Equipe", "TMD"])

    resultado = (
        detalhes.groupby(["Data", "Equipe"], as_index=False)["Disponibilidade"]
        .mean()
        .rename(columns={"Disponibilidade": "_segundos"})
    )
    resultado["Data"] = resultado["Data"].map(lambda data: data.isoformat())
    resultado["TMD"] = resultado["_segundos"].map(_formatar_duracao)
    return resultado[["Data", "Equipe", "TMD"]]


def _formatar_duracao(segundos):
    segundos = max(0, int(round(segundos)))
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"


def identificar_colaboradores_sem_logout(sessoes):
    """Lista Saídas sem Logout, sem transformar esses registros em sessões."""
    dados = padronizar_sessoes(sessoes)
    dados["_equipe"] = dados["Fila"].map(_equipe)
    dados["_direcao"] = dados["Direção"].map(_texto_normalizado)
    sem_logout = dados[
        dados["_equipe"].notna()
        &
        dados["_direcao"].str.contains("SAIDA|FIM|EXIT", regex=True)
        & dados["Logout"].astype(str).str.strip().eq("")
    ].copy()
    if sem_logout.empty:
        return pd.DataFrame(
            columns=["Agente", "Fila", "Login", "Direção", "Status"]
        )
    return pd.DataFrame(
        {
            "Agente": sem_logout["Agente"].astype(str).str.strip(),
            "Fila": sem_logout["Fila"].astype(str).str.strip(),
            "Login": sem_logout["Login"].astype(str).str.strip(),
            "Direção": sem_logout["Direção"].astype(str).str.strip(),
            "Status": "Logout não informado",
        }
    ).drop_duplicates()


COLUNAS_PENDENCIAS = [
    "Tipo",
    "Agente",
    "Fila / Motivo",
    "Horário registrado",
    "Horário faltando",
]
_COLUNAS_AJUSTE = [
    "Horário faltando",
    "Agente",
    "Fila / Motivo",
    "Horário registrado",
    "Horário informado",
]
_FORMATO_HORARIO = re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}(:\d{2})?$")


def _horario(texto):
    """Converte um texto em Timestamp (NaT se vazio ou inválido)."""
    return _dataserie(pd.Series([str(texto or "").strip()])).iloc[0]


def formatar_horario(texto):
    """Horário no padrão DD/MM/AAAA HH:MM:SS (ou None se inválido)."""
    horario = _horario(texto)
    return None if pd.isna(horario) else horario.strftime("%d/%m/%Y %H:%M:%S")


def validar_horario(faltando, registrado, informado):
    """Confere o horário digitado. Devolve (status, mensagem).

    status: "vazio" (nada digitado), "ok" ou "erro".
    """
    texto = str(informado or "").strip()
    if not texto:
        return "vazio", ""
    if not _FORMATO_HORARIO.match(texto) or pd.isna(_horario(texto)):
        return "erro", "Horário incompleto ou inexistente. Use DD/MM/AAAA HH:MM:SS."
    horario, referencia = _horario(texto), _horario(registrado)
    if pd.notna(referencia):
        marca = referencia.strftime("%d/%m/%Y %H:%M:%S")
        if faltando in ("Logout", "Retorno da pausa") and horario <= referencia:
            return "erro", f"Precisa ser depois de {marca}."
        if faltando == "Login" and horario >= referencia:
            return "erro", f"Precisa ser antes de {marca}."
    return "ok", ""


def _normalizar_ajustes(ajustes):
    if ajustes is None or ajustes.empty:
        return None
    if "Horário informado" in ajustes.columns:
        return ajustes[_COLUNAS_AJUSTE]
    if "Logout manual" in ajustes.columns:  # formato antigo
        return pd.DataFrame(
            {
                "Horário faltando": "Logout",
                "Agente": ajustes["Agente"],
                "Fila / Motivo": ajustes["Fila"],
                "Horário registrado": ajustes["Login"],
                "Horário informado": ajustes["Logout manual"],
            }
        )
    return None


def aplicar_horarios_manuais(sessoes, pausas, preenchimentos):
    """Grava cada horário informado na coluna correspondente.

    Logout -> coluna Logout; Login -> coluna Login; retorno da pausa ->
    coluna Tempo em Pausa (duração entre o início e o retorno).
    """
    sessoes = padronizar_sessoes(sessoes).copy()
    pausas = padronizar_pausas(pausas).copy()
    ajustes = _normalizar_ajustes(preenchimentos)
    if ajustes is None:
        return sessoes, pausas

    txt = lambda serie: serie.astype(str).str.strip()
    for faltando, agente, motivo, registrado, informado in ajustes.itertuples(
        index=False, name=None
    ):
        status, _ = validar_horario(faltando, registrado, informado)
        if status != "ok":
            continue
        agente, motivo = str(agente).strip(), str(motivo).strip()
        registrado, informado = str(registrado).strip(), str(informado).strip()

        if faltando in ("Logout", "Login"):
            campo_ref, campo_falta = (
                ("Login", "Logout") if faltando == "Logout" else ("Logout", "Login")
            )
            mascara = (
                txt(sessoes["Agente"]).eq(agente)
                & txt(sessoes["Fila"]).eq(motivo)
                & txt(sessoes[campo_ref]).eq(registrado)
                & txt(sessoes[campo_falta]).eq("")
            )
            sessoes.loc[mascara, campo_falta] = informado
        elif faltando == "Retorno da pausa":
            mascara = (
                txt(pausas["Agente"]).eq(agente)
                & txt(pausas["Pausa"]).eq(motivo)
                & txt(pausas["Data/Hora"]).eq(registrado)
                & pausas["Tempo em Pausa"].map(_duracao_em_segundos).eq(0)
            )
            segundos = (_horario(informado) - _horario(registrado)).total_seconds()
            pausas.loc[mascara, "Tempo em Pausa"] = _formatar_duracao(segundos)
    return sessoes, pausas


def identificar_horarios_faltantes(sessoes, pausas):
    """Lista horários que faltam nos arquivos e distorcem o TMD.

    - Logout faltando: entrada sem saída, ou Saída sem Logout.
    - Login faltando: saída registrada sem entrada.
    - Retorno da pausa faltando: pausa iniciada e nunca encerrada
      (só para colaboradores de Retenção/Negociação).
    """
    sessoes = padronizar_sessoes(sessoes)
    pausas = padronizar_pausas(pausas)

    pendentes = []
    _intervalos_sessoes(sessoes, pendentes)
    _pausas_unicas(pausas, pendentes)
    for agente, fila, login, _, _ in identificar_colaboradores_sem_logout(
        sessoes
    ).itertuples(index=False, name=None):
        pendentes.append(("Logout", agente, fila, login))

    agentes_das_equipes = set(
        sessoes.loc[sessoes["Fila"].map(_equipe).notna(), "Agente"]
        .astype(str)
        .str.strip()
    )
    linhas = []
    for faltando, agente, motivo, registrado in pendentes:
        if not registrado or pd.isna(_horario(registrado)):
            continue
        if faltando == "Retorno da pausa" and agente not in agentes_das_equipes:
            continue
        tipo = "Sessão" if faltando in ("Logout", "Login") else "Pausa"
        linhas.append((tipo, agente, motivo, registrado, faltando))

    resultado = pd.DataFrame(linhas, columns=COLUNAS_PENDENCIAS)
    return (
        resultado.drop_duplicates()
        .sort_values(["Agente", "Tipo"], kind="stable")
        .reset_index(drop=True)
    )


def _tmd_sem_correcao(sessoes, pausas):
    """Reproduz a média sem unir filas e sem deduplicar as pausas."""
    dados = sessoes.copy()
    dados["_agente"] = dados["Agente"].astype(str).str.strip()
    dados["_equipe"] = dados["Fila"].map(_equipe)
    dados["_inicio"] = _dataserie(dados["Login"])
    dados["_fim"] = _dataserie(dados["Logout"])
    dados = dados[
        dados["_equipe"].notna()
        & dados["_agente"].ne("")
        & dados["_inicio"].notna()
        & dados["_fim"].notna()
        & dados["_fim"].gt(dados["_inicio"])
    ].copy()

    pausas_brutas = pausas.copy()
    pausas_brutas["_agente"] = pausas_brutas["Agente"].astype(str).str.strip()
    pausas_brutas["_inicio"] = _dataserie(pausas_brutas["Data/Hora"])
    pausas_brutas["_duracao"] = (
        pausas_brutas["Tempo em Pausa"].map(_duracao_em_segundos).astype(float)
    )
    pausas_brutas = pausas_brutas[
        pausas_brutas["_agente"].ne("")
        & pausas_brutas["_inicio"].notna()
        & pausas_brutas["_duracao"].gt(0)
    ]

    linhas = []
    for (agente, equipe), grupo in dados.groupby(["_agente", "_equipe"]):
        for data, grupo_dia in grupo.groupby(grupo["_inicio"].dt.date):
            logado = sum(
                (fim - inicio).total_seconds()
                for inicio, fim in grupo_dia[["_inicio", "_fim"]].itertuples(
                    index=False, name=None
                )
            )
            pausa = pausas_brutas[
                (pausas_brutas["_agente"].eq(agente))
                & (pausas_brutas["_inicio"].dt.date == data)
            ]["_duracao"].sum()
            linhas.append({
                "Data": data,
                "Equipe": equipe,
                "_agente": agente,
                "Disponibilidade": max(0.0, logado - pausa),
            })

    detalhes = pd.DataFrame(linhas)
    if detalhes.empty:
        return pd.DataFrame(columns=["Data", "Equipe", "TMD"])
    resultado = (
        detalhes.groupby(["Data", "Equipe"], as_index=False)["Disponibilidade"]
        .mean()
        .rename(columns={"Disponibilidade": "_segundos"})
    )
    resultado["Data"] = resultado["Data"].map(lambda data: data.isoformat())
    resultado["TMD"] = resultado["_segundos"].map(_formatar_duracao)
    return resultado[["Data", "Equipe", "TMD"]]


def calcular_tmd_comparativo_dos_csvs(
    sessoes_conteudo,
    pausas_conteudo,
    ajustes=None,
):
    """Devolve (comparativo, horários faltantes) a partir dos CSVs.

    Aceita um arquivo (bytes) ou uma lista de arquivos de cada tipo.
    """
    sessoes = _ler_tipo(sessoes_conteudo, "sessoes")
    pausas = _ler_tipo(pausas_conteudo, "pausas")
    pendencias = identificar_horarios_faltantes(sessoes, pausas)

    sessoes_corrigidas, pausas_corrigidas = aplicar_horarios_manuais(
        sessoes, pausas, ajustes
    )
    try:
        corrigido = calcular_tmd(sessoes_corrigidas, pausas_corrigidas)
    except ErroTMD:
        if pendencias.empty:
            raise
        # Sem sessões válidas por causa de horários faltando: o usuário
        # precisa poder preenchê-los antes de haver resultado.
        corrigido = pd.DataFrame(columns=["Data", "Equipe", "TMD"])
    sem_correcao = _tmd_sem_correcao(sessoes, pausas)
    comparativo = sem_correcao.rename(columns={"TMD": "TMD sem correção"})
    comparativo = comparativo.merge(
        corrigido.rename(columns={"TMD": "TMD corrigido"}),
        on=["Data", "Equipe"],
        how="outer",
    )
    comparativo["TMD sem correção"] = comparativo[
        "TMD sem correção"
    ].fillna("00:00:00")
    comparativo["TMD corrigido"] = comparativo["TMD corrigido"].fillna(
        "00:00:00"
    )
    return (
        comparativo[["Data", "Equipe", "TMD sem correção", "TMD corrigido"]],
        pendencias,
    )


def corrigir_csvs_com_horarios(sessoes_conteudo, pausas_conteudo, ajustes):
    """Devolve (sessões, pausas) com os horários informados já gravados."""
    return aplicar_horarios_manuais(
        _ler_tipo(sessoes_conteudo, "sessoes"),
        _ler_tipo(pausas_conteudo, "pausas"),
        ajustes,
    )


def diagnosticar_tmd(sessoes_conteudo, pausas_conteudo):
    """Resumo do que foi lido, para o usuário conferir os arquivos."""
    sessoes = _ler_tipo(sessoes_conteudo, "sessoes")
    pausas = _ler_tipo(pausas_conteudo, "pausas")
    intervalos = _intervalos_sessoes(sessoes)
    return {
        "sessoes_lidas": len(sessoes),
        "pausas_lidas": len(pausas),
        "colunas_extras_ignoradas": (
            len([c for c in sessoes.columns if c not in SESSOES_ALIASES])
            + len([c for c in pausas.columns if c not in PAUSAS_ALIASES])
        ),
        "filas": sorted(sessoes["Fila"].astype(str).str.strip().unique()),
        "direcoes_sessoes": sorted(
            sessoes["Direção"].astype(str).str.strip().unique()
        ),
        "amostra_sessoes": sessoes[list(SESSOES_ALIASES)].head(5),
        "intervalos_validos": len(intervalos),
    }


_PREFIXOS_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _neutralizar(valor):
    if isinstance(valor, str) and valor.startswith(_PREFIXOS_FORMULA):
        return "'" + valor
    return valor


def neutralizar_formulas(dados):
    """Evita injeção de fórmula (CSV injection) ao abrir o CSV no Excel."""
    limpo = dados.copy()
    limpo.columns = [_neutralizar(str(coluna)) for coluna in limpo.columns]
    for coluna in limpo.columns:
        serie = limpo[coluna]
        if pd.api.types.is_object_dtype(serie) or pd.api.types.is_string_dtype(serie):
            limpo[coluna] = serie.map(_neutralizar)
    return limpo


def csv_seguro(dados):
    """Gera os bytes do CSV para download, já neutralizado e com BOM UTF-8."""
    return (
        neutralizar_formulas(dados)
        .to_csv(sep=";", index=False)
        .encode("utf-8-sig")
    )
