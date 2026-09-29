import pandas as pd

import pytest

from tmd_calculation import (
    ErroTMD,
    MAX_CSV_BYTES,
    _linhas_csv,
    aplicar_horarios_manuais,
    COLUNAS_PAUSAS,
    calcular_tmd,
    calcular_tmd_comparativo_dos_csvs,
    carregar_csv,
    classificar_csv,
    limpar_pausas,
    limpar_sessoes,
    unificar_pausas,
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
            "Fila": ["RETENÇÃO", "RETENÇÃO", "COBRANÇA"],
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
            "Fila": ["RETENÇÃO", "COBRANÇA", "SAC"],
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
    assert set(resultado["Equipe"]) == {"RETENÇÃO", "COBRANÇA"}


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
            "Fila": ["COBRANÇA"],
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
            "Fila": ["COBRANÇA", "COBRANÇA"],
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

    assert set(resultado["Equipe"]) == {"RETENÇÃO", "COBRANÇA"}


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

    assert set(resultado["Equipe"]) == {"RETENÇÃO", "COBRANÇA"}


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


# ---------- equipes ----------

def test_cobranca_aparece_como_cobranca_e_retencao_como_retencao():
    sessoes = pd.DataFrame(
        {
            "Agente": ["Ana", "Bia", "Cris", "Duda"],
            "Fila": [
                "Região 1 - Cancelamento", "Cobranca Interno",
                "Discador Cobranca CS", "SAC Cancelamento",
            ],
            "Login": ["24/09/2026 08:00"] * 4,
            "Direção": ["Entrada"] * 4,
            "Logout": ["24/09/2026 17:00"] * 4,
            "Tempo Logado": ["09:00:00"] * 4,
        }
    )

    resultado = calcular_tmd(sessoes, _pausas_vazias())

    assert set(resultado["Equipe"]) == {"RETENÇÃO", "COBRANÇA"}
    assert "NEGOCIAÇÃO" not in set(resultado["Equipe"])


# ---------- unificação dos arquivos de pausas ----------

def _csv_pausas():
    return (
        "Data/Hora;Agente;Fila;Direção;Pausa;Tempo em Pausa;Tempo Estimado;"
        "Justificativa;Justificativa de Atraso;Coluna Só Deste Arquivo\n"
        "24/09/2026 12:00;Ana;RETENÇÃO;Entrada;Almoço;01:00:00;01:00:00;;;x\n"
        "24/09/2026 12:00;Ana;RETENÇÃO;Entrada;Almoço;01:00:00;01:00:00;;;x\n"
    ).encode()


def _csv_chamadas():
    return (
        "Data de início,Agente,Fila,Sentido,Causa desconexão,Espera,Atendimento,Outra\n"
        "24/09/2026 10:00:00,Ana,Região 1 - Cancelamento,Entrada,Cliente,00:05:00,00:10:00,z\n"
        "24/09/2026 12:00,Ana,RETENÇÃO,Entrada,Almoço,01:00:00,01:00:00,z\n"
    ).encode()


def test_arquivo_de_chamadas_e_reconhecido_como_pausas():
    assert classificar_csv(_csv_chamadas())[0] == "pausas"
    assert classificar_csv(_csv_pausas())[0] == "pausas"


def test_pausas_unificadas_tem_exatamente_as_colunas_principais():
    quadros = [carregar_csv(c, "pausas")[1] for c in (_csv_pausas(), _csv_chamadas())]

    unido = unificar_pausas(quadros)

    assert list(unido.columns) == COLUNAS_PAUSAS + ["_origem"]
    chamada = unido[unido["Pausa"] == "Cliente"].iloc[0]
    assert (chamada["Data/Hora"], chamada["Direção"], chamada["Tempo em Pausa"],
            chamada["Tempo Estimado"]) == (
        "24/09/2026 10:00:00", "Entrada", "00:05:00", "00:10:00")
    assert chamada["Justificativa"] == "" and chamada["Justificativa de Atraso"] == ""


def test_pausas_duplicadas_apos_somar_os_arquivos_sao_removidas():
    quadros = [carregar_csv(c, "pausas")[1] for c in (_csv_pausas(), _csv_chamadas())]

    limpo = limpar_pausas(unificar_pausas(quadros))

    almoco = limpo[limpo["Pausa"] == "Almoço"]
    assert len(almoco) == 1 and len(limpo) == 2


def test_linhas_de_chamadas_contam_como_eventos_isolados_sem_gerar_pendencia():
    sessoes = _sessao_csv()
    pausas = unificar_pausas([carregar_csv(_csv_chamadas(), "pausas")[1]])
    pausas.loc[pausas["Pausa"] == "Almoço", "Tempo em Pausa"] = ""

    assert identificar_horarios_faltantes(sessoes, pausas).empty
    # só a chamada de 5 min (Espera) é descontada
    assert calcular_tmd(sessoes, pausas).iloc[0]["TMD"] == "08:55:00"


def test_comparativo_aceita_um_arquivo_de_pausas_e_um_de_chamadas():
    comparativo, _ = calcular_tmd_comparativo_dos_csvs(
        [_sessao_csv().to_csv(index=False).encode()],
        [_csv_pausas(), _csv_chamadas()],
    )

    assert comparativo.iloc[0]["TMD corrigido"] == "07:55:00"


# ---------- duplicidade nas sessões ----------

def _linhas_sessao(*linhas):
    return pd.DataFrame(
        linhas, columns=["Agente", "Fila", "Login", "Direção", "Logout", "Tempo Logado"]
    )


def test_sessoes_removem_duplicidade_na_ordem_pedida():
    sessoes = _linhas_sessao(
        ("Ana", "Região 1 - Cancelamento", "08:00", "Entrada", "", ""),
        ("Ana", "SAC Cancelamento", "08:00", "Entrada", "", ""),      # 1º passo
        ("Ana", "Região 1 - Cancelamento", "13:00", "Entrada", "", ""),
        ("Ana", "Região 1 - Cancelamento", "", "Saída", "17:00", ""),
        ("Ana", "SAC Cancelamento", "", "Saída", "17:00", ""),        # 2º passo
        ("Bia", "Região 1 - Cancelamento", "08:00", "Entrada", "", ""),
    )

    limpo = limpar_sessoes(sessoes)

    assert len(limpo) == 4
    assert "_equipe" not in limpo.columns
    assert (limpo["Login"] == "13:00").sum() == 1  # campo vazio não é duplicidade


def test_limpeza_nao_descarta_a_fila_da_equipe():
    # 1ª linha é de fila fora das equipes: a de Retenção não pode sumir
    sessoes = _linhas_sessao(
        ("Ana", "Suporte Tecnico Geral", "08:00:00", "Entrada", "", ""),
        ("Ana", "Região 1 - Cancelamento", "08:00:00", "Entrada", "", ""),
        ("Ana", "Suporte Sem Acesso", "08:00:00", "Entrada", "", ""),
    )

    limpo = limpar_sessoes(sessoes)

    assert "Região 1 - Cancelamento" in set(limpo["Fila"])
    assert len(limpo) == 2  # 1 de Retenção + 1 das demais filas


def test_limpeza_mantem_colaborador_nas_duas_equipes():
    sessoes = _linhas_sessao(
        ("Ana", "Região 1 - Cancelamento", "08:00:00", "Entrada", "", ""),
        ("Ana", "Cobranca Interno", "08:00:00", "Entrada", "", ""),
    )

    assert len(limpar_sessoes(sessoes)) == 2


def test_segundo_passo_remove_saidas_repetidas_com_mesmo_logout():
    sessoes = _linhas_sessao(
        ("Ana", "Região 1 - Cancelamento", "08:00", "Saída", "17:00", ""),
        ("Ana", "SAC Cancelamento", "08:30", "Saída", "17:00", ""),
    )

    assert len(limpar_sessoes(sessoes)) == 1
