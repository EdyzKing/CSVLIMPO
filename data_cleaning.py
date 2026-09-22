import pandas as pd


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
        "55539999",
        "555599999",
        "55519999",
        "555399999",
        "555444",
        "555555",
        "99999",
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
