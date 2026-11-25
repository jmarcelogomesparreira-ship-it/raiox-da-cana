"""
ETAPA 2 — Limpar, organizar e resumir os dados para o painel
=============================================================

Entrada:  dados_brutos/pam_bruto.csv      (gerado pela etapa 1, ~1 milhão de linhas)
          dados_brutos/municipios.json    (lista de municípios e mesorregiões)
Saída:    dados/raiox.json                (resumo leve que o painel index.html lê)

O que acontece aqui:
  1. Lê a tabela bruta (formato "longo": uma linha por medida).
  2. Vira formato "largo": uma linha por município + ano + produto,
     com uma coluna para cada medida (área, produção, valor).
  3. Calcula a produtividade (t/ha) e os totais por Brasil, estado e região.
  4. Monta rankings, curva de Pareto/ABC e as séries de cada município.
  5. Salva tudo em JSON (o formato que o JavaScript do painel entende).

Como rodar:
    python src/etapa2_preparar_dados.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
ARQ_BRUTO = RAIZ / "dados_brutos" / "pam_bruto.csv"
ARQ_MUNICIPIOS = RAIZ / "dados_brutos" / "municipios.json"
ARQ_SAIDA = RAIZ / "dados" / "raiox.json"

PRODUTOS = {40106: "cana", 40124: "soja", 40122: "milho"}
VARIAVEIS = {8331: "area_plantada", 216: "area_colhida", 214: "producao",
             112: "rendimento_ibge", 215: "valor"}

MUNICIPIO_DESTAQUE = "3134400"   # Iturama - MG
MESO_DESTAQUE = "Triângulo Mineiro/Alto Paranaíba"
TOP_SERIES = 400                 # quantos municípios terão série histórica no painel
ANO_REAL = 1995                  # valores em R$ só fazem sentido depois do Plano Real


def carregar():
    print("Lendo dados brutos...")
    df = pd.read_csv(ARQ_BRUTO, dtype={"municipio_cod": str})
    df["produto"] = df["produto_cod"].map(PRODUTOS)
    df["variavel"] = df["variavel_cod"].map(VARIAVEIS)
    df["ano"] = df["ano_cod"].astype(int)

    # Antes de 1994 o "valor" vinha em Cruzeiro, Cruzado... Misturar moedas
    # dá número sem sentido, então só guardamos valores em Reais.
    eh_valor = df["variavel"] == "valor"
    moeda_ruim = ~df["unidade"].astype(str).str.contains("Reais", case=False)
    df.loc[eh_valor & (moeda_ruim | (df["ano"] < ANO_REAL)), "valor"] = None

    # Formato longo -> largo (como uma tabela dinâmica do Excel)
    largo = df.pivot_table(index=["municipio_cod", "municipio_nome", "ano", "produto"],
                           columns="variavel", values="valor", aggfunc="first")
    largo = largo.reset_index()
    largo.columns.name = None

    # "Iturama - MG" -> nome "Iturama" e uf "MG"
    largo["uf"] = largo["municipio_nome"].str[-2:]
    largo["nome"] = largo["municipio_nome"].str[:-5]

    # Mesorregião
    if ARQ_MUNICIPIOS.exists():
        munis = pd.DataFrame(json.loads(ARQ_MUNICIPIOS.read_text(encoding="utf-8")))
        largo = largo.merge(munis[["cod", "meso"]], how="left",
                            left_on="municipio_cod", right_on="cod").drop(columns="cod")
    else:
        largo["meso"] = None

    for col in ["area_plantada", "area_colhida", "producao", "valor"]:
        if col not in largo:
            largo[col] = None
    print(f"   {len(largo):,} linhas organizadas".replace(",", "."))
    return largo


def r(x, casas=0):
    """Arredonda e troca vazio (NaN) por None, que vira null no JSON."""
    if x is None or pd.isna(x):
        return None
    return round(float(x), casas) if casas else int(round(float(x)))


def produtividade(prod, area):
    return r(prod / area, 2) if area and area > 0 and pd.notna(prod) else None


def serie_total(grupo):
    """Soma por ano e devolve listas paralelas (anos, produção, área...)."""
    s = grupo.groupby("ano")[["producao", "area_colhida", "valor"]].sum(min_count=1)
    s = s.sort_index()
    return {
        "anos": [int(a) for a in s.index],
        "producao": [r(v) for v in s["producao"]],
        "area": [r(v) for v in s["area_colhida"]],
        "valor": [r(v) for v in s["valor"]],
        "rend": [produtividade(p, a) for p, a in zip(s["producao"], s["area_colhida"])],
    }


def ultimo_ano_com_dados(largo):
    por_ano = largo.groupby("ano")["producao"].sum(min_count=1)
    return int(por_ano[por_ano > 0].index.max())


def pareto(lista_prod):
    """Curva de Pareto: % acumulado da produção vs % de municípios."""
    v = sorted([p for p in lista_prod if p and p > 0], reverse=True)
    total = sum(v)
    acum, pontos, n50, n80 = 0, [], None, None
    for i, p in enumerate(v, start=1):
        acum += p
        pct = acum / total
        if n50 is None and pct >= 0.5:
            n50 = i
        if n80 is None and pct >= 0.8:
            n80 = i
        pontos.append(round(pct * 100, 2))
    # Curva ABC: A = até 80% da produção, B = 80–95%, C = o resto
    n95 = next(i for i, p in enumerate(pontos, start=1) if p >= 95)
    return {"acumulado": pontos, "n_total": len(v), "n50": n50, "n80": n80,
            "abc": {"A": n80, "B": n95 - n80, "C": len(v) - n95}}


def montar(largo):
    ano_fim = ultimo_ano_com_dados(largo)
    anos = sorted(largo["ano"].unique())
    saida = {
        "meta": {
            "fonte": "IBGE — Produção Agrícola Municipal (PAM), tabela 5457 do SIDRA",
            "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "ano_inicio": int(anos[0]), "ano_fim": ano_fim,
            "destaque": {"cod": MUNICIPIO_DESTAQUE, "meso": MESO_DESTAQUE},
        },
        "produtos": {},
    }

    for produto in PRODUTOS.values():
        print(f"Resumindo {produto}...")
        dp = largo[largo["produto"] == produto]
        ult = dp[(dp["ano"] == ano_fim) & (dp["producao"] > 0)].copy()
        ult = ult.sort_values("producao", ascending=False)

        # Brasil
        brasil = serie_total(dp)
        brasil["n_municipios"] = [int(((g["producao"] > 0)).sum())
                                  for _, g in dp.groupby("ano")]

        # Estados: série de produção de cada UF
        ufs = {}
        for uf, g in dp.groupby("uf"):
            s = serie_total(g)
            if any(s["producao"]):
                ufs[uf] = {"producao": s["producao"], "area": s["area"]}
        anos_uf = sorted(dp["ano"].unique().tolist())

        # Mesorregiões no último ano
        mesos = (ult.groupby(["meso", "uf"])[["producao", "area_colhida"]].sum()
                 .sort_values("producao", ascending=False).head(30).reset_index())

        # Tabela de municípios no último ano
        municipios = [[m.municipio_cod, m.nome, m.uf, r(m.area_colhida), r(m.producao),
                       produtividade(m.producao, m.area_colhida), r(m.valor)]
                      for m in ult.itertuples()]

        # Séries históricas dos maiores + o município destaque
        cods = ult["municipio_cod"].head(TOP_SERIES).tolist()
        if MUNICIPIO_DESTAQUE not in cods:
            cods.append(MUNICIPIO_DESTAQUE)
        series = {}
        for cod, g in dp[dp["municipio_cod"].isin(cods)].groupby("municipio_cod"):
            g = g.sort_values("ano")
            series[cod] = {"anos": g["ano"].tolist(),
                           "producao": [r(v) for v in g["producao"]],
                           "area": [r(v) for v in g["area_colhida"]]}

        # Região destaque (Triângulo Mineiro)
        regiao = serie_total(dp[dp["meso"] == MESO_DESTAQUE])

        saida["produtos"][produto] = {
            "brasil": brasil,
            "ufs": {"anos": [int(a) for a in anos_uf], "series": ufs},
            "mesos": [[m.meso, m.uf, r(m.producao), r(m.area_colhida)]
                      for m in mesos.itertuples()],
            "municipios": municipios,
            "pareto": pareto(ult["producao"].tolist()) if len(ult) else None,
            "series": series,
            "regiao": regiao,
        }

    return saida


def main():
    largo = carregar()
    saida = montar(largo)
    ARQ_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    ARQ_SAIDA.write_text(json.dumps(saida, ensure_ascii=False, separators=(",", ":")),
                         encoding="utf-8")
    tam = ARQ_SAIDA.stat().st_size / 1024 / 1024
    print(f"\nPronto! {ARQ_SAIDA} ({tam:.1f} MB)")


if __name__ == "__main__":
    main()
