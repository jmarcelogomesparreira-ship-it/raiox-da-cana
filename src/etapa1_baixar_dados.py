"""
ETAPA 1 — Baixar os dados da Produção Agrícola Municipal (PAM) do IBGE
=======================================================================

O que este script faz:
  1. Pergunta ao IBGE quais anos existem na tabela 5457 da PAM.
  2. Para cada ano, baixa os dados dos 3 produtos (cana, soja, milho)
     de TODOS os municípios do Brasil pela API do SIDRA, num pedido só.
  3. Salva cada pedaço em dados_brutos/pam/ (se cair a internet, ele
     continua de onde parou na próxima vez).
  4. Junta tudo num arquivo só: dados_brutos/pam_bruto.csv
  5. Baixa também a lista de municípios (com mesorregião) do IBGE.

Este script roda sozinho no GitHub (GitHub Actions), mas também roda no
seu computador, se você tiver o Python instalado.

Como rodar (no terminal, dentro da pasta do projeto):
    pip install -r requirements.txt
    python src/etapa1_baixar_dados.py

Para testar rápido, só com os últimos 3 anos:
    python src/etapa1_baixar_dados.py --ultimos 3
"""

import argparse
import time
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO — é aqui que você muda o que quer baixar
# ---------------------------------------------------------------------------

TABELA = 5457  # PAM: área, produção, rendimento e valor das lavouras

# Variáveis (o que medir). Código do IBGE -> nome curto que vamos usar.
# (Só as 3 que o painel usa: menos dados = download mais rápido.
#  Outras opções: 8331 = área plantada, 112 = rendimento médio.)
VARIAVEIS = {
    216: "area_colhida_ha",
    214: "producao_t",
    215: "valor_mil_reais",
}

# Produtos (classificação c782). Código do IBGE -> nome curto.
PRODUTOS = {
    40106: "cana",
    40124: "soja",
    40122: "milho",
}

# Pastas
RAIZ = Path(__file__).resolve().parent.parent
PASTA_BRUTOS = RAIZ / "dados_brutos" / "pam"
ARQUIVO_FINAL = RAIZ / "dados_brutos" / "pam_bruto.csv"
ARQUIVO_MUNICIPIOS = RAIZ / "dados_brutos" / "municipios.json"

URL_DADOS = "https://apisidra.ibge.gov.br/values"
URL_METADADOS = "https://servicodados.ibge.gov.br/api/v3/agregados"
URL_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"

# Valores especiais que o IBGE usa no lugar de número
#  "-"   = zero absoluto        "..." = dado não disponível
#  "X"   = sigilo               ".."  = não se aplica
VALORES_ESPECIAIS = {"-": 0, "...": None, "..": None, "X": None}


# ---------------------------------------------------------------------------
# FUNÇÕES
# ---------------------------------------------------------------------------

def pedir_json(url, tentativas=4):
    """Faz o pedido à API e tenta de novo se der erro (o IBGE às vezes cai)."""
    for i in range(1, tentativas + 1):
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as erro:
            espera = 5 * i
            print(f"   ! erro ({erro.__class__.__name__}), tentando de novo em {espera}s...")
            time.sleep(espera)
    raise RuntimeError(f"Não consegui baixar depois de {tentativas} tentativas:\n{url}")


def anos_disponiveis():
    """Pergunta ao IBGE quais anos a tabela tem."""
    dados = pedir_json(f"{URL_METADADOS}/{TABELA}/periodos")
    return sorted(int(p["id"]) for p in dados)


def conferir_produtos():
    """Confere se os códigos dos produtos batem com os nomes no IBGE."""
    meta = pedir_json(f"{URL_METADADOS}/{TABELA}/metadados")
    nomes = {}
    for classif in meta["classificacoes"]:
        if classif["id"] == 782:
            for cat in classif["categorias"]:
                nomes[cat["id"]] = cat["nome"]
    print("Produtos que vamos baixar:")
    for cod, curto in PRODUTOS.items():
        print(f"   {cod} = {nomes.get(cod, '??? CÓDIGO NÃO ENCONTRADO')}  ({curto})")
        if cod not in nomes:
            raise SystemExit("Algum código de produto está errado. Confira a lista acima.")


def json_para_tabela(dados):
    """
    A API devolve uma lista: a 1ª linha é o cabeçalho (nomes das colunas)
    e o resto são os dados. Aqui transformamos isso numa tabela do pandas
    com nomes de coluna fáceis de entender.
    """
    cabecalho, linhas = dados[0], dados[1:]
    df = pd.DataFrame(linhas)

    # Descobre qual coluna D1C, D2C... é município, variável, ano e produto
    # "V" é o valor e "MN" é a unidade (toneladas, hectares, mil reais...)
    renomear = {"V": "valor", "MN": "unidade"}
    for chave, rotulo in cabecalho.items():
        if not chave.startswith("D"):
            continue
        r = rotulo.lower()
        tipo = "cod" if chave.endswith("C") else "nome"
        if "município" in r or "municipio" in r:
            renomear[chave] = f"municipio_{tipo}"
        elif "variável" in r or "variavel" in r:
            renomear[chave] = f"variavel_{tipo}"
        elif r.startswith("ano"):
            renomear[chave] = f"ano_{tipo}"
        elif "produto" in r:
            renomear[chave] = f"produto_{tipo}"

    df = df.rename(columns=renomear)
    df = df[[c for c in renomear.values() if c in df.columns]]

    # Converte o texto do valor em número
    df["valor"] = df["valor"].replace(VALORES_ESPECIAIS)
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return df


def baixar_municipios():
    """Baixa a lista de municípios com UF e mesorregião (para agrupar)."""
    import json
    dados = pedir_json(URL_MUNICIPIOS)
    lista = []
    for m in dados:
        # Alguns municípios novos vêm sem microrregião: por isso o "or {}"
        micro = m.get("microrregiao") or {}
        meso = micro.get("mesorregiao") or {}
        uf = (meso.get("UF") or {}).get("sigla")
        lista.append({"cod": str(m["id"]), "nome": m["nome"],
                      "meso": meso.get("nome"), "uf": uf})
    ARQUIVO_MUNICIPIOS.write_text(json.dumps(lista, ensure_ascii=False),
                                  encoding="utf-8")
    print(f"Municípios: {len(lista)} salvos em {ARQUIVO_MUNICIPIOS.name}")


def baixar_ano(ano):
    """Baixa um ano, com os 3 produtos, para todos os municípios (n6/all).
    O IBGE aceita até 100 mil valores por pedido: 5.570 municípios
    x 3 medidas x 3 produtos = ~50 mil, então cabe num pedido só."""
    vars_txt = ",".join(str(v) for v in VARIAVEIS)
    prods_txt = ",".join(str(p) for p in PRODUTOS)
    url = (f"{URL_DADOS}/t/{TABELA}/n6/all/v/{vars_txt}"
           f"/p/{ano}/c782/{prods_txt}")
    return json_para_tabela(pedir_json(url))


def main():
    parser = argparse.ArgumentParser(description="Baixa a PAM do IBGE")
    parser.add_argument("--ultimos", type=int, default=None,
                        help="baixar só os N anos mais recentes (para testar)")
    args = parser.parse_args()

    PASTA_BRUTOS.mkdir(parents=True, exist_ok=True)

    conferir_produtos()
    baixar_municipios()
    anos = anos_disponiveis()
    if args.ultimos:
        anos = anos[-args.ultimos:]
    print(f"\nAnos: {anos[0]} a {anos[-1]} ({len(anos)} anos)")

    inicio = time.time()
    for n, ano in enumerate(anos, start=1):
        arquivo = PASTA_BRUTOS / f"pam_{ano}.csv"
        if arquivo.exists():
            print(f"[{n}/{len(anos)}] {ano} — já baixado, pulando")
            continue
        t0 = time.time()
        df = baixar_ano(ano)
        df.to_csv(arquivo, index=False, encoding="utf-8")
        gasto = time.time() - inicio
        falta = gasto / n * (len(anos) - n)
        print(f"[{n}/{len(anos)}] {ano} — {len(df):,} linhas em {time.time()-t0:.0f}s "
              f"(faltam ~{falta/60:.0f} min)".replace(",", "."))
        time.sleep(1)  # educação com o servidor do IBGE

    # Junta todos os pedaços
    print("\nJuntando tudo...")
    partes = [pd.read_csv(f, dtype={"municipio_cod": str})
              for f in sorted(PASTA_BRUTOS.glob("pam_*.csv"))]
    pam = pd.concat(partes, ignore_index=True)
    pam.to_csv(ARQUIVO_FINAL, index=False, encoding="utf-8")

    print(f"\nPronto! {len(pam):,} linhas salvas em {ARQUIVO_FINAL}".replace(",", "."))
    print("\nPrimeiras linhas:")
    print(pam.head(10).to_string())


if __name__ == "__main__":
    main()
