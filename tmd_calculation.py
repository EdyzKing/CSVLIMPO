import csv
import io
import re
import unicodedata

import pandas as pd


SESSION_COLUMNS = {
    "Agente",
    "Fila",
    "Login",
    "Direção",
    "Logout",
    "Tempo Logado",
}

BREAK_COLUMNS = {
    "Data/Hora",
    "Agente",
    "Fila",
    "Direção",
    "Pausa",
    "Tempo em Pausa",
    "Tempo Estimado",
    "Justificativa",
    "Justificativa de Atraso",
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


def _ler_csv(conteudo):
    if hasattr(conteudo, "getvalue"):
        conteudo = conteudo.getvalue()
    if isinstance(conteudo, str):
        conteudo = conteudo.encode("utf-8-sig")
    if not conteudo or not conteudo.strip():
        raise ValueError("O arquivo CSV está vazio.")

    amostra = conteudo[:8192].decode("utf-8-sig", errors="replace")
    try:
        separador = csv.Sniffer().sniff(amostra, delimiters=";,\t,").delimiter
    except csv.Error:
        separador = ";" if amostra.count(";") >= amostra.count(",") else ","

    ultimo_erro = None
    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            dados = pd.read_csv(
                io.BytesIO(conteudo),
                sep=separador,
                encoding=encoding,
                dtype=str,
                keep_default_na=False,
            )
            dados.columns = [
                str(coluna).replace("\ufeff", "").strip()
                for coluna in dados.columns
            ]
            return dados
        except UnicodeDecodeError as erro:
            ultimo_erro = erro

    raise ValueError("Não foi possível decodificar o CSV.") from ultimo_erro


def _validar_colunas(dados, esperadas, nome):
    ausentes = sorted(esperadas.difference(dados.columns))
    if ausentes:
        raise ValueError(
            f"O arquivo de {nome} não possui as colunas: "
            f"{', '.join(ausentes)}."
        )


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


def _intervalos_sessoes(dados):
    sessoes = dados.copy()
    sessoes["_agente"] = sessoes["Agente"].astype(str).str.strip()
    sessoes["_fila"] = sessoes["Fila"].astype(str).str.strip()
    sessoes["_equipe"] = sessoes["Fila"].map(_equipe)
    sessoes["_login"] = _dataserie(sessoes["Login"])
    sessoes["_logout"] = _dataserie(sessoes["Logout"])
    sessoes["_duracao"] = sessoes["Tempo Logado"].map(
        _duracao_em_segundos
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
    colunas_evento.append("_duracao")
    for registro in sessoes[colunas_evento].itertuples(
        index=False, name=None
    ):
        agente, fila, equipe, login, logout, direcao, duracao = registro
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
            abertos[chave] = (equipe, login)
        elif pd.notna(logout) or eh_saida:
            fim = logout if pd.notna(logout) else login
            equipe_aberta, inicio = abertos.pop(chave, (None, None))
            if inicio is not None and pd.notna(fim) and fim > inicio:
                intervalos.append((agente, equipe_aberta, inicio, fim))

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


def _pausas_unicas(dados):
    pausas = dados.copy()
    pausas["_agente"] = pausas["Agente"].astype(str).str.strip()
    pausas["_inicio"] = _dataserie(pausas["Data/Hora"])
    pausas["_motivo"] = pausas["Pausa"].astype(str).str.strip()
    pausas["_duracao"] = pausas["Tempo em Pausa"].map(_duracao_em_segundos)
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
        ]
        for registro in grupo.sort_values("_inicio")[colunas_evento].itertuples(
            index=False, name=None
        ):
            agente, inicio, motivo_registro, duracao_registro, direcao = registro
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
                aberturas.append((agente, inicio, duracao_registro))
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
    _validar_colunas(sessoes, SESSION_COLUMNS, "sessões em filas")
    _validar_colunas(pausas, BREAK_COLUMNS, "pausas")

    intervalos = _intervalos_sessoes(sessoes)
    pausas_unicas = _pausas_unicas(pausas)
    if intervalos.empty:
        filas = sorted(
            str(valor).strip()
            for valor in sessoes["Fila"].dropna().unique()
        )
        raise ValueError(
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


def calcular_tmd_dos_csvs(sessoes_conteudo, pausas_conteudo):
    return calcular_tmd(
        _ler_csv(sessoes_conteudo),
        _ler_csv(pausas_conteudo),
    )


def identificar_colaboradores_sem_logout(sessoes):
    """Lista Saídas sem Logout, sem transformar esses registros em sessões."""
    _validar_colunas(sessoes, SESSION_COLUMNS, "sessões em filas")
    dados = sessoes.copy()
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


def _aplicar_logouts_manuais(sessoes, logouts_manuais):
    if logouts_manuais is None or logouts_manuais.empty:
        return sessoes

    dados = sessoes.copy()
    ajustes = logouts_manuais.copy()
    ajustes["_agente"] = ajustes["Agente"].astype(str).str.strip()
    ajustes["_fila"] = ajustes["Fila"].astype(str).str.strip()
    ajustes["_login"] = _dataserie(ajustes["Login"])
    ajustes["_logout_manual"] = _dataserie(ajustes["Logout manual"])

    colunas_ajuste = [
        "Agente",
        "Fila",
        "Login",
        "_agente",
        "_fila",
        "_login",
        "_logout_manual",
        "Logout manual",
    ]
    for ajuste in ajustes[colunas_ajuste].itertuples(
        index=False, name=None
    ):
        agente, fila, login, _, _, _, logout_manual, logout_texto = ajuste
        if pd.isna(logout_manual):
            continue
        mascara = (
            dados["Agente"].astype(str).str.strip().eq(agente.strip())
            & dados["Fila"].astype(str).str.strip().eq(fila.strip())
            & dados["Login"].astype(str).str.strip().eq(login.strip())
            & dados["Logout"].astype(str).str.strip().eq("")
        )
        dados.loc[mascara, "Logout"] = logout_texto
    return dados


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
    pausas_brutas["_duracao"] = pausas_brutas["Tempo em Pausa"].map(
        _duracao_em_segundos
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
    logouts_manuais=None,
):
    sessoes = _ler_csv(sessoes_conteudo)
    pausas = _ler_csv(pausas_conteudo)
    sessoes_corrigidas = _aplicar_logouts_manuais(
        sessoes,
        logouts_manuais,
    )
    corrigido = calcular_tmd(sessoes_corrigidas, pausas)
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
        identificar_colaboradores_sem_logout(sessoes),
    )


def corrigir_sessoes_com_logouts_manuais(sessoes_conteudo, logouts_manuais):
    sessoes = _ler_csv(sessoes_conteudo)
    return _aplicar_logouts_manuais(sessoes, logouts_manuais)


def diagnosticar_tmd(sessoes_conteudo, pausas_conteudo):
    """Retorna uma amostra dos dados lidos para diagnosticar CSVs reais."""
    sessoes = _ler_csv(sessoes_conteudo)
    pausas = _ler_csv(pausas_conteudo)
    intervalos = _intervalos_sessoes(sessoes)
    return {
        "sessoes_lidas": len(sessoes),
        "pausas_lidas": len(pausas),
        "colunas_sessoes": list(sessoes.columns),
        "colunas_pausas": list(pausas.columns),
        "filas": sorted(sessoes["Fila"].astype(str).str.strip().unique()),
        "direcoes_sessoes": sorted(
            sessoes["Direção"].astype(str).str.strip().unique()
        ),
        "amostra_sessoes": sessoes[
            ["Agente", "Fila", "Login", "Direção", "Logout", "Tempo Logado"]
        ].head(5),
        "intervalos_validos": len(intervalos),
    }