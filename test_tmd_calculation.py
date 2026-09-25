import pandas as pd

from tmd_calculation import (
    calcular_tmd,
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