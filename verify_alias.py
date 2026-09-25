import pandas as pd
from data_cleaning import normalizar_colunas_para_padrao


df = pd.DataFrame(
    {
        "Nome da empresa": ["Empresa A"],
        "Bairro": ["Centro"],
        "Cidade": ["SP"],
        "Tel": ["11999999999"],
    }
)

result = normalizar_colunas_para_padrao(df)
print(result.columns.tolist())
print("Razão social" in result.columns)
print("Bairro" in result.columns)
print("Cidade" in result.columns)
print("Telefone" in result.columns)
