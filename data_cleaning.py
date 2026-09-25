import re
import unicodedata
from difflib import SequenceMatcher

import pandas as pd


def _normalizar_nome_coluna(coluna):
    """Converte nomes de colunas para uma forma estável e comparável."""
    texto = str(coluna).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return texto.strip()


def normalizar_colunas_para_padrao(dados):
    """Mapeia colunas comuns para os nomes esperados pelo sistema."""
    dados = dados.copy()

    aliases = {
        "Razão social": {
            "razao social",
            "raza social",
            "razao",
            "nome da empresa",
            "nome empresa",
            "nome da fantasia",
            "nome fantasia",
            "empresa",
            "cliente",
            "nome",
            "nome cliente",
            "pessoa",
            "pessoas",
            "nome pessoa",
        },
        "Bairro": {
            "bairro",
            "bairros",
            "bairro cliente",
            "bairro empresa",
            "bairro da empresa",
            "localidade",
        },
        "Cidade": {
            "cidade",
            "cidades",
            "cidade cliente",
            "cidade empresa",
            "municipio",
            "municipio cliente",
            "localidade cidade",
        },
        "Telefone": {
            "telefone",
            "telefones",
            "tel",
            "fone",
            "celular",
            "celular principal",
            "telefone principal",
            "telefone 1",
            "telefone1",
            "telefone_1",
            "numero telefone",
            "numero celular",
        },
        "colaborador": {
            "colaborador",
            "responsavel",
            "analista",
            "usuario",
        },
        "Status": {
            "status",
            "situacao",
            "situacao da instalacao",
            "situacao instalacao",
        },
    }

    mapeamento = {}
    campos_ja_mapados = set()
    colunas_norm = {
        _normalizar_nome_coluna(col): col
        for col in dados.columns
    }

    for nome_esperado, variantes in aliases.items():
        for variacao in variantes:
            chave = _normalizar_nome_coluna(variacao)
            if chave in colunas_norm:
                coluna = colunas_norm[chave]
                if (
                    coluna not in mapeamento
                    and nome_esperado not in campos_ja_mapados
                ):
                    mapeamento[coluna] = nome_esperado
                    campos_ja_mapados.add(nome_esperado)
                break

    # Prioriza colunas que mencionam explicitamente Bairro. Isso evita que
    # nomes como "Bairro do cliente" sejam confundidos com Razao social.
    if "Bairro" not in campos_ja_mapados:
        for coluna in list(dados.columns):
            if coluna in mapeamento:
                continue

            nome_norm = _normalizar_nome_coluna(coluna)
            if "bairro" in nome_norm.split():
                mapeamento[coluna] = "Bairro"
                campos_ja_mapados.add("Bairro")
                break

    for nome_esperado, variantes in aliases.items():
        if nome_esperado in campos_ja_mapados:
            continue

        for coluna in list(dados.columns):
            if coluna in mapeamento:
                continue
            nome_norm = _normalizar_nome_coluna(coluna)
            if (
                "bairro" in nome_norm.split()
                and nome_esperado != "Bairro"
            ):
                continue
            if any(
                _normalizar_nome_coluna(variante) in nome_norm
                for variante in variantes
            ):
                mapeamento[coluna] = nome_esperado
                campos_ja_mapados.add(nome_esperado)
                break

    # Aceita pequenos erros de digitacao no campo Bairro, sem aplicar
    # correspondencia aproximada aos demais campos.
    if "Bairro" not in campos_ja_mapados:
        for coluna in list(dados.columns):
            if coluna in mapeamento:
                continue

            nome_norm = _normalizar_nome_coluna(coluna)
            palavras = nome_norm.split()
            similaridade = max(
                (
                    SequenceMatcher(None, palavra, "bairro").ratio()
                    for palavra in palavras
                ),
                default=0,
            )

            if similaridade >= 0.78:
                mapeamento[coluna] = "Bairro"
                campos_ja_mapados.add("Bairro")
                break

    if mapeamento:
        dados = dados.rename(columns=mapeamento)

    dados.attrs["mapeamento_colunas"] = {
        nome_padrao: nome_original
        for nome_original, nome_padrao in mapeamento.items()
    }

    return dados


def obter_mapeamento_colunas(colunas):
    """Retorna o mapa entre cabecalhos originais e nomes internos."""
    dados = pd.DataFrame(columns=list(colunas))
    normalizados = normalizar_colunas_para_padrao(dados)
    return normalizados.attrs.get("mapeamento_colunas", {})


def padronizar_bairros(dados):
    """Remove espaços e padroniza os bairros em letras maiúsculas."""
    if "Bairro" not in dados.columns:
        raise ValueError("Coluna 'Bairro' não encontrada.")

    dados = dados.copy()
    dados["Bairro"] = (
        dados["Bairro"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    return dados


def separar_registros_sem_bairro(dados):
    """Separa registros cujo Bairro está vazio."""
    if "Bairro" not in dados.columns:
        raise ValueError("Coluna 'Bairro' não encontrada.")

    dados = dados.copy()
    sem_bairro = (
        dados["Bairro"]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq("")
    )

    registros = dados[sem_bairro].copy()
    dados = dados[~sem_bairro].copy()

    return dados, registros


def separar_nomes_iniciados_por_numero(dados):
    """Separa nomes que começam com número."""
    if "Razão social" not in dados.columns:
        raise ValueError("Coluna 'Razão social' não encontrada.")

    dados = dados.copy()
    nome = (
        dados["Razão social"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    regra = nome.str.match(r"^\d+(?:\s+|$)", na=False)

    registros = dados[regra].copy()
    dados = dados[~regra].copy()

    return dados, registros


def identificar_nomes_numericos(dados):
    """Identifica nomes compostos somente por números e espaços."""
    if "Razão social" not in dados.columns:
        raise ValueError("Coluna 'Razão social' não encontrada.")

    nome = (
        dados["Razão social"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    regra = nome.str.fullmatch(r"\d+(?:\s+\d+)*", na=False)
    return dados[regra].copy()


def identificar_nomes_muito_curtos(dados):
    """Identifica razões sociais com até 2 caracteres."""
    if "Razão social" not in dados.columns:
        raise ValueError("Coluna 'Razão social' não encontrada.")

    nome = (
        dados["Razão social"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    regra = nome.str.len().le(2)
    return dados[regra].copy()


def identificar_nomes_de_teste(dados):
    """Identifica razões sociais que contenham teste/test."""
    if "Razão social" not in dados.columns:
        raise ValueError("Coluna 'Razão social' não encontrada.")

    nome = (
        dados["Razão social"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    regra = nome.str.contains(
        r"\bteste\b|\btest\b",
        case=False,
        regex=True,
        na=False
    )

    return dados[regra].copy()


def identificar_telefones_com_prefixos_bloqueados(dados):
    """Identifica telefones que começam com prefixos bloqueados."""
    if "Telefone" not in dados.columns:
        raise ValueError("Coluna 'Telefone' não encontrada.")

    prefixos_bloqueados = (
        "555399999",
        "555599999",
        "555199999",
        "555499999",
        "555444",
        "555555",
        "99999",
        "3020",
        "3320",
        "5555555",
        "9999",
        "999",
        )

    telefone = (
        dados["Telefone"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    regra = telefone.str.startswith(
        prefixos_bloqueados,
        na=False
    )

    return dados[regra].copy()


def identificar_nomes_suspeitos(dados):
    """Mantém a regra original: números, nomes curtos ou teste/test."""
    if "Razão social" not in dados.columns:
        raise ValueError("Coluna 'Razão social' não encontrada.")

    nome = (
        dados["Razão social"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    apenas_numeros = nome.str.fullmatch(r"\d+", na=False)
    muito_curto = nome.str.len().le(2)
    teste = nome.str.contains(
        r"\bteste\b|\btest\b",
        case=False,
        regex=True,
        na=False
    )

    return dados[apenas_numeros | muito_curto | teste].copy()
