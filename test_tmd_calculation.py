import pandas as pd

import pytest

from tmd_calculation import (
    ErroTMD,
    MAX_CSV_BYTES,
    _linhas_csv,
    aplicar_horarios_manuais,
    calcular_tmd,
    classificar_csv,
    identificar_horarios_faltantes,
    validar_horario,
    csv_seguro,
    neutralizar_formulas,
    calcular_tmd_comparativo_dos_csvs,
    identificar_colaboradores_sem_logout,
)


def test_pausa_repetida_em_varias_filas_e_subtraida_uma_vez():
    sessoes = pd.DataFrame(
        {
            "Agente": ["João", "João", "João"],
            "Fila": ["RETENÇÃO", "RETENÇÃO", "NEGOCIAÇÃO"],
            "Login": ["24/09/2026 08:00"] * 3,
            "Direção": ["Entrada"] * 3,
            "Logout": ["24/09/2026 17:00"] * 3,
            "Tempo Logado": ["09:00:00"] * 3,
        }
    )
    pausas = pd.DataFrame(
        {
            "Data/Hora": ["24/09/2026 12:00"] * 3,
            "Agente": ["João"] * 3,
            "Fila": ["RETENÇÃO", "NEGOCIAÇÃO", "SAC"],
            "Direção": ["Entrada"] * 3,
            "Pausa": ["Almoço"] * 3,
            "Tempo em Pausa": ["01:00:00"] * 3,
            "Tempo Estimado": [""] * 3,
            "Justificativa": [""] * 3,
            "Justificativa de Atraso": [""] * 3,
        }
    )

    resultado = calcular_tmd(sessoes, pausas)

    assert set(resultado["TMD"]) == {"08:00:00"}
    assert set(resultado["Equipe"]) == {"RETENÇÃO", "NEGOCIAÇÃO"}


def test_pausas_com_mesmo_motivo_em_horarios_diferentes_sao_mantidas():
    sessoes = pd.DataFrame(
        {
            "Agente": ["Ana"],
            "Fila": ["RETENÇÃO"],
            "Login": ["24/09/2026 08:00"],
            "Direção": ["Entrada"],
            "Logout": ["24/09/2026 17:00"],
            "Tempo Logado": ["09:00:00"],
        }
    )
    pausas = pd.DataFrame(
        {
            "Data/Hora": ["24/09/2026 09:00", "24/09/2026 10:30"],
            "Agente": ["Ana", "Ana"],
            "Fila": ["RETENÇÃO", "RETENÇÃO"],
            "Direção": ["Entrada", "Entrada"],
            "Pausa": ["Banheiro", "Banheiro"],
            "Tempo em Pausa": ["00:05:00", "00:05:00"],
            "Tempo Estimado": ["", ""],
            "Justificativa": ["", ""],
            "Justificativa de Atraso": ["", ""],
        }
    )

    assert calcular_tmd(sessoes, pausas).iloc[0]["TMD"] == "08:50:00"


def test_direcao_entrada_e_saida_forma_uma_unica_pausa():
    sessoes = pd.DataFrame(
        {
            "Agente": ["Bia"],
            "Fila": ["NEGOCIAÇÃO"],
            "Login": ["24/09/2026 08:00"],
            "Direção": ["Entrada"],
            "Logout": ["24/09/2026 17:00"],
            "Tempo Logado": ["09:00:00"],
        }
    )
    pausas = pd.DataFrame(
        {
            "Data/Hora": ["24/09/2026 12:00", "24/09/2026 13:00"],
            "Agente": ["Bia", "Bia"],
            "Fila": ["NEGOCIAÇÃO", "NEGOCIAÇÃO"],
            "Direção": ["Entrada", "Saída"],
            "Pausa": ["Almoço", "Almoço"],
            "Tempo em Pausa": ["", "01:00:00"],
            "Tempo Estimado": ["", ""],
            "Justificativa": ["", ""],
            "Justificativa de Atraso": ["", ""],
        }
    )

    assert calcular_tmd(sessoes, pausas).iloc[0]["TMD"] == "08:00:00"


def test_sessao_com_entrada_e_saida_em_linhas_separadas():
    sessoes = pd.DataFrame(
        {
            "Agente": ["Carlos", "Carlos"],
            "Fila": ["RETENÇÃO", "RETENÇÃO"],
            "Login": ["24/09/2026 08:00", ""],
            "Direção": ["Entrada", "Saída"],
            "Logout": ["", "24/09/2026 17:00"],
            "Tempo Logado": ["", ""],
        }
    )
    pausas = pd.DataFrame(
        columns=[
            "Data/Hora", "Agente", "Fila", "Direção", "Pausa",
            "Tempo em Pausa", "Tempo Estimado", "Justificativa",
            "Justificativa de Atraso",
        ]
    )

    resultado = calcular_tmd(sessoes, pausas)

    assert resultado.iloc[0]["TMD"] == "09:00:00"


def test_filas_operacionais_sao_mapeadas_para_as_equipes():
    sessoes = pd.DataFrame(
        {
            "Agente": ["Ana", "Bia"],
            "Fila": ["Região 1 - Cancelamento", "Cobranca Interno"],
            "Login": ["24/09/2026 08:00", "24/09/2026 08:00"],
            "Direção": ["Entrada", "Entrada"],
            "Logout": ["24/09/2026 17:00", "24/09/2026 17:00"],
            "Tempo Logado": ["09:00:00", "09:00:00"],
        }
    )
    pausas = pd.DataFrame(
        columns=[
            "Data/Hora", "Agente", "Fila", "Direção", "Pausa",
            "Tempo em Pausa", "Tempo Estimado", "Justificativa",
            "Justificativa de Atraso",
        ]
    )

    resultado = calcular_tmd(sessoes, pausas)

    assert set(resultado["Equipe"]) == {"RETENÇÃO", "NEGOCIAÇÃO"}


def test_classificacao_e_por_fila_para_todos_os_agentes():
    sessoes = pd.DataFrame(
        {
            "Agente": ["Mônica", "Paola", "Outro", "Outro"],
            "Fila": [
                "SAC Cancelamento",
                "Região 1 - Cancelamento",
                "Cobranca Interno",
                "Região 1 - Cobrança",
            ],
            "Login": ["24/09/2026 08:00"] * 4,
            "Direção": ["Entrada"] * 4,
            "Logout": ["24/09/2026 17:00"] * 4,
            "Tempo Logado": ["09:00:00"] * 4,
        }
    )
    pausas = pd.DataFrame(
        columns=[
            "Data/Hora", "Agente", "Fila", "Direção", "Pausa",
            "Tempo em Pausa", "Tempo Estimado", "Justificativa",
            "Justificativa de Atraso",
        ]
    )

    resultado = calcular_tmd(sessoes, pausas)

    assert set(resultado["Equipe"]) == {"RETENÇÃO", "NEGOCIAÇÃO"}


def test_comparativo_separa_calculo_sem_correcao_do_corrigido():
    sessoes = pd.DataFrame(
        {
            "Agente": ["Ana", "Ana", "Ana"],
            "Fila": ["Região 1 - Cancelamento"] * 3,
            "Login": ["24/09/2026 08:00"] * 3,
            "Direção": ["Entrada", "Saída", "Entrada"],
            "Logout": [
                "24/09/2026 17:00",
                "24/09/2026 17:00",
                "24/09/2026 17:00",
            ],
            "Tempo Logado": ["09:00:00"] * 3,
        }
    )
    pausas = pd.DataFrame(
        {
            "Data/Hora": ["24/09/2026 12:00"] * 3,
            "Agente": ["Ana"] * 3,
            "Fila": ["Região 1 - Cancelamento"] * 3,
            "Direção": ["Entrada"] * 3,
            "Pausa": ["Almoço"] * 3,
            "Tempo em Pausa": ["01:00:00"] * 3,
            "Tempo Estimado": [""] * 3,
            "Justificativa": [""] * 3,
            "Justificativa de Atraso": [""] * 3,
        }
    )
    comparativo, sem_logout = calcular_tmd_comparativo_dos_csvs(
        sessoes.to_csv(index=False).encode(),
        pausas.to_csv(index=False).encode(),
    )

    linha = comparativo.iloc[0]
    assert linha["TMD sem correção"] != linha["TMD corrigido"]
    assert linha["TMD corrigido"] == "08:00:00"
    assert sem_logout.empty


def test_identifica_saida_sem_logout():
    sessoes = pd.DataFrame(
        {
            "Agente": ["Ana"],
            "Fila": ["Região 1 - Cancelamento"],
            "Login": ["24/09/2026 08:00"],
            "Direção": ["Saída"],
            "Logout": [""],
            "Tempo Logado": ["33:40:09"],
        }
    )

    resultado = identificar_colaboradores_sem_logout(sessoes)

    assert resultado.iloc[0]["Agente"] == "Ana"
    assert resultado.iloc[0]["Status"] == "Logout não informado"


def test_logout_manual_e_aplicado_apenas_ao_tmd_corrigido():
    sessoes = pd.DataFrame(
        {
            "Agente": ["Ana"],
            "Fila": ["Região 1 - Cancelamento"],
            "Login": ["24/09/2026 08:00:00"],
            "Direção": ["Saída"],
            "Logout": [""],
            "Tempo Logado": ["09:00:00"],
        }
    )
    pausas = pd.DataFrame(
        columns=[
            "Data/Hora", "Agente", "Fila", "Direção", "Pausa",
            "Tempo em Pausa", "Tempo Estimado", "Justificativa",
            "Justificativa de Atraso",
        ]
    )
    ajustes = pd.DataFrame(
        {
            "Agente": ["Ana"],
            "Fila": ["Região 1 - Cancelamento"],
            "Login": ["24/09/2026 08:00:00"],
            "Direção": ["Saída"],
            "Status": ["Logout não informado"],
            "Logout manual": ["24/09/2026 17:00:00"],
        }
    )

    comparativo, sem_logout = calcular_tmd_comparativo_dos_csvs(
        sessoes.to_csv(index=False).encode(),
        pausas.to_csv(index=False).encode(),
        ajustes,
    )

    assert comparativo.iloc[0]["TMD corrigido"] == "09:00:00"
    assert not sem_logout.empty

def test_neutraliza_formulas_em_valores_e_cabecalhos():
    dados = pd.DataFrame(
        {"=Coluna": ["=1+1", "+cmd", "-2", "@x", "Ana"], "Fila": list("abcde")}
    )

    limpo = neutralizar_formulas(dados)

    assert list(limpo.columns) == ["'=Coluna", "Fila"]
    assert limpo.iloc[:, 0].tolist() == ["'=1+1", "'+cmd", "'-2", "'@x", "Ana"]


def test_csv_seguro_gera_bytes_com_bom_e_sem_formula():
    dados = pd.DataFrame({"Agente": ["=HYPERLINK(\"x\")"], "TMD": ["08:00:00"]})

    conteudo = csv_seguro(dados)

    assert conteudo.startswith(b"\xef\xbb\xbf")
    assert b";=HYPERLINK" not in conteudo and b"'=HYPERLINK" in conteudo


def test_csv_acima_do_limite_e_rejeitado():
    with pytest.raises(ErroTMD, match="limite"):
        _linhas_csv(b"a;b\n" + b"x" * (MAX_CSV_BYTES + 1))


# ---------- leitura por nome de coluna ----------

COLS_SESSOES = ["Agente", "Fila", "Login", "Direção", "Logout", "Tempo Logado"]
COLS_PAUSAS = ["Data/Hora", "Agente", "Fila", "Direção", "Pausa", "Tempo em Pausa"]


def _sessao_csv(**extra):
    linha = {
        "Agente": "Ana", "Fila": "Região 1 - Cancelamento",
        "Login": "24/09/2026 08:00:00", "Direção": "Entrada",
        "Logout": "24/09/2026 17:00:00", "Tempo Logado": "09:00:00",
    }
    linha.update(extra)
    return pd.DataFrame([linha])


def _pausas_vazias():
    return pd.DataFrame(columns=COLS_PAUSAS)


def test_aceita_colunas_extras_fora_de_ordem_e_com_outra_grafia():
    sessoes = pd.DataFrame(
        {
            "Observação": ["x"],
            "tempo logado": ["09:00:00"],
            "LOGOUT": ["24/09/2026 17:00:00"],
            "direcao": ["Entrada"],
            "Login": ["24/09/2026 08:00:00"],
            "Fila ": ["Região 1 - Cancelamento"],
            "Agente": ["Ana"],
        }
    )
    pausas = pd.DataFrame(
        {
            "Motivo": ["Almoço"],
            "Tempo em Pausa": ["01:00:00"],
            "Direção": ["Entrada"],
            "Agente": ["Ana"],
            "Data e Hora": ["24/09/2026 12:00"],
            "Coluna inútil": ["-"],
        }
    )

    assert calcular_tmd(sessoes, pausas).iloc[0]["TMD"] == "08:00:00"


def test_coluna_obrigatoria_ausente_gera_mensagem_clara():
    sessoes = _sessao_csv().drop(columns=["Logout"])

    with pytest.raises(ErroTMD, match="Logout"):
        calcular_tmd(sessoes, _pausas_vazias())


def test_classifica_arquivo_pelas_colunas_e_nao_pelo_nome():
    sessoes = _sessao_csv().to_csv(sep=";", index=False).encode()
    pausas = _pausas_vazias().to_csv(index=False).encode()

    assert classificar_csv(sessoes)[0] == "sessoes"
    assert classificar_csv(pausas)[0] == "pausas"
    with pytest.raises(ErroTMD, match="Não reconheci"):
        classificar_csv(b"foo;bar\n1;2\n")


def test_le_csv_com_titulo_acima_do_cabecalho_e_linhas_irregulares():
    conteudo = (
        "Relatório gerado em 28/09/2026\n\n"
        + ";".join(COLS_SESSOES) + ";Extra\n"
        + "Ana;Região 1 - Cancelamento;24/09/2026 08:00:00;Entrada;"
        + "24/09/2026 17:00:00;09:00:00\n"
    ).encode("latin1")

    tipo, linhas = classificar_csv(conteudo)

    assert (tipo, linhas) == ("sessoes", 1)


def test_varios_arquivos_do_mesmo_tipo_sao_reunidos():
    from tmd_calculation import calcular_tmd_comparativo_dos_csvs

    dia1 = _sessao_csv().to_csv(index=False).encode()
    dia2 = _sessao_csv(
        Login="25/09/2026 08:00:00", Logout="25/09/2026 16:00:00"
    ).to_csv(index=False).encode()

    comparativo, _ = calcular_tmd_comparativo_dos_csvs(
        [dia1, dia2], [_pausas_vazias().to_csv(index=False).encode()]
    )

    assert sorted(comparativo["TMD corrigido"]) == ["08:00:00", "09:00:00"]


# ---------- horários faltando ----------

def test_detecta_entrada_sem_saida_e_grava_logout_informado():
    sessoes = _sessao_csv(Logout="", Direção="Entrada", **{"Tempo Logado": ""})

    pendencias = identificar_horarios_faltantes(sessoes, _pausas_vazias())

    assert pendencias.iloc[0]["Horário faltando"] == "Logout"
    assert pendencias.iloc[0]["Horário registrado"] == "24/09/2026 08:00:00"

    ajustes = pendencias.assign(**{"Horário informado": "24/09/2026 17:00:00"})
    corrigidas, _ = aplicar_horarios_manuais(sessoes, _pausas_vazias(), ajustes)

    assert corrigidas.iloc[0]["Logout"] == "24/09/2026 17:00:00"
    assert calcular_tmd(corrigidas, _pausas_vazias()).iloc[0]["TMD"] == "09:00:00"


def test_detecta_saida_sem_entrada_e_grava_login_informado():
    sessoes = _sessao_csv(Login="", Direção="Saída", **{"Tempo Logado": ""})

    pendencias = identificar_horarios_faltantes(sessoes, _pausas_vazias())

    assert pendencias.iloc[0]["Horário faltando"] == "Login"
    ajustes = pendencias.assign(**{"Horário informado": "24/09/2026 08:00:00"})
    corrigidas, _ = aplicar_horarios_manuais(sessoes, _pausas_vazias(), ajustes)

    assert corrigidas.iloc[0]["Login"] == "24/09/2026 08:00:00"
    assert calcular_tmd(corrigidas, _pausas_vazias()).iloc[0]["TMD"] == "09:00:00"


def _pausa_aberta(agente="Ana"):
    return pd.DataFrame(
        {
            "Data/Hora": ["24/09/2026 12:00"], "Agente": [agente],
            "Fila": ["RETENÇÃO"], "Direção": ["Entrada"],
            "Pausa": ["Almoço"], "Tempo em Pausa": [""],
        }
    )


def test_pausa_sem_retorno_vira_pendencia_e_desconta_duracao_informada():
    sessoes = _sessao_csv()
    pausas = _pausa_aberta()

    pendencias = identificar_horarios_faltantes(sessoes, pausas)

    assert pendencias.iloc[0]["Horário faltando"] == "Retorno da pausa"
    assert calcular_tmd(sessoes, pausas).iloc[0]["TMD"] == "09:00:00"

    ajustes = pendencias.assign(**{"Horário informado": "24/09/2026 13:00:00"})
    _, pausas_corrigidas = aplicar_horarios_manuais(sessoes, pausas, ajustes)

    assert pausas_corrigidas.iloc[0]["Tempo em Pausa"] == "01:00:00"
    assert calcular_tmd(sessoes, pausas_corrigidas).iloc[0]["TMD"] == "08:00:00"


def test_pausa_sem_retorno_de_quem_nao_e_das_equipes_nao_gera_pendencia():
    pendencias = identificar_horarios_faltantes(
        _sessao_csv(), _pausa_aberta(agente="Outro Setor")
    )

    assert pendencias.empty


def test_sem_pendencia_quando_arquivos_estao_completos():
    assert identificar_horarios_faltantes(_sessao_csv(), _pausas_vazias()).empty


def test_validar_horario_orienta_o_usuario():
    reg = "24/09/2026 08:00:00"

    assert validar_horario("Logout", reg, "")[0] == "vazio"
    assert validar_horario("Logout", reg, "24/09/2026 17:30:00")[0] == "ok"
    assert validar_horario("Logout", reg, "24/09/2026 17")[0] == "erro"
    assert validar_horario("Logout", reg, "31/02/2026 10:00:00")[0] == "erro"
    status, msg = validar_horario("Logout", reg, "24/09/2026 07:00:00")
    assert status == "erro" and "depois de 24/09/2026 08:00:00" in msg
    status, msg = validar_horario("Login", "24/09/2026 17:00:00", "24/09/2026 18:00:00")
    assert status == "erro" and "antes de" in msg


def test_horario_invalido_e_ignorado_ao_aplicar():
    sessoes = _sessao_csv(Logout="", **{"Tempo Logado": ""})
    pendencias = identificar_horarios_faltantes(sessoes, _pausas_vazias())
    ajustes = pendencias.assign(**{"Horário informado": "24/09/2026 07:00:00"})

    corrigidas, _ = aplicar_horarios_manuais(sessoes, _pausas_vazias(), ajustes)

    assert corrigidas.iloc[0]["Logout"] == ""


def test_pendencia_aparece_mesmo_sem_nenhuma_sessao_valida():
    from tmd_calculation import calcular_tmd_comparativo_dos_csvs

    sessoes = _sessao_csv(Logout="", **{"Tempo Logado": ""})

    comparativo, pendencias = calcular_tmd_comparativo_dos_csvs(
        sessoes.to_csv(index=False).encode(),
        _pausas_vazias().to_csv(index=False).encode(),
    )

    assert comparativo.empty and not pendencias.empty
