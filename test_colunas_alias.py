import pandas as pd

from data_cleaning import normalizar_colunas_para_padrao


def test_normalizar_colunas_para_padrao_com_aliases():
    df = pd.DataFrame(
        {
            "Nome da empresa": ["Empresa A"],
            "Bairro": ["Centro"],
            "Cidade": ["SP"],
            "Tel": ["11999998888"],
        }
    )

    result = normalizar_colunas_para_padrao(df)

    assert "Razão social" in result.columns
    assert "Bairro" in result.columns
    assert "Cidade" in result.columns
    assert "Telefone" in result.columns


def test_normalizar_colunas_para_padrao_com_variacoes():
    df = pd.DataFrame(
        {
            "razao_social": ["Empresa B"],
            "bairro_cliente": ["Jardim"],
            "municipio": ["RJ"],
            "telefone_1": ["21999997777"],
        }
    )

    result = normalizar_colunas_para_padrao(df)

    assert "Razão social" in result.columns
    assert "Bairro" in result.columns
    assert "Cidade" in result.columns
    assert "Telefone" in result.columns
