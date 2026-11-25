"""
ETAPA 3 — Indicadores econômicos: Selic, dólar e inflação (IPCA)
=================================================================

Fontes oficiais:
  - Banco Central (API SGS):  Selic e dólar
  - IBGE (SIDRA, tabela 1737): IPCA, a inflação oficial do Brasil

Saída: dados/economia.json, que o painel usa para:
  - mostrar Selic, dólar e IPCA (KPIs e gráficos)
  - corrigir o valor da produção pela inflação (valor "real")
  - converter o valor da produção para dólar

Se uma fonte falhar, o script segue com as outras (o painel esconde
o que estiver faltando), então o robô não fica vermelho por causa disso.

Como rodar:
    python src/etapa3_economia.py
"""

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
ARQ_SAIDA = RAIZ / "dados" / "economia.json"

ANO_INICIO = 1995   # Plano Real: antes disso os números da época não são comparáveis

# Séries do Banco Central (código SGS -> nome)
SGS = {
    4189: "selic_mensal",   # Selic acumulada no mês, anualizada (% a.a.)
    3698: "dolar_mensal",   # Dólar (venda), média do mês (R$)
    432:  "selic_meta",     # Meta Selic definida pelo Copom (% a.a.) — diária
    1:    "dolar_diario",   # Dólar PTAX (venda) — diária
}
URL_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados"
URL_IPCA = "https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/63,2265,2266/p/all"


def pedir_json(url, params=None, tentativas=4):
    for i in range(1, tentativas + 1):
        try:
            r = requests.get(url, params=params, timeout=60,
                             headers={"Accept": "application/json"})
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as erro:
            print(f"   ! erro ({erro.__class__.__name__}), tentando de novo em {5*i}s...")
            time.sleep(5 * i)
    raise RuntimeError(f"Falhou: {url}")


def serie_bcb(cod, inicio, fim):
    """O Banco Central limita cada consulta a 10 anos, então pedimos em blocos."""
    pontos = []
    a = inicio
    while a <= fim:
        b = min(fim, date(a.year + 9, 12, 31))
        dados = pedir_json(URL_SGS.format(cod=cod), {
            "formato": "json",
            "dataInicial": a.strftime("%d/%m/%Y"),
            "dataFinal": b.strftime("%d/%m/%Y"),
        })
        for p in dados:
            d = datetime.strptime(p["data"], "%d/%m/%Y").date()
            try:
                pontos.append((d, float(p["valor"])))
            except (TypeError, ValueError):
                pass
        a = date(b.year + 1, 1, 1)
        time.sleep(0.5)
    return sorted(set(pontos))


def mensal(pontos):
    """Lista de (data, valor) -> {"2025-10": valor}"""
    return {d.strftime("%Y-%m"): round(v, 4) for d, v in pontos}


def ipca_ibge():
    """IPCA do IBGE: variação no mês, acumulado em 12 meses e número-índice."""
    dados = pedir_json(URL_IPCA)
    cab, linhas = dados[0], dados[1:]
    col_mes = next(k for k, v in cab.items() if k.endswith("C") and v.lower().startswith("mês"))
    col_var = next(k for k, v in cab.items() if k.endswith("C") and "vari" in v.lower())
    saida = {"var_mes": {}, "acum_12m": {}, "indice": {}}
    chave = {"63": "var_mes", "2265": "acum_12m", "2266": "indice"}
    for l in linhas:
        try:
            v = float(l["V"])
        except (TypeError, ValueError):
            continue
        cod = l[col_mes]                     # ex.: "202510"
        mes = f"{cod[:4]}-{cod[4:6]}"
        if int(cod[:4]) < ANO_INICIO - 1:
            continue
        saida[chave[l[col_var]]][mes] = v
    return saida


def media_anual(por_mes):
    anos = {}
    for m, v in por_mes.items():
        anos.setdefault(int(m[:4]), []).append(v)
    return {a: round(sum(v) / len(v), 4) for a, v in sorted(anos.items())}


def main():
    hoje = date.today()
    inicio = date(ANO_INICIO, 1, 1)
    eco = {"meta": {"gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                    "fontes": "Banco Central do Brasil (SGS) e IBGE (IPCA, tabela 1737)"},
           "mensal": {}, "anual": {}, "atual": {}}

    # --- Banco Central ---
    for cod, nome in SGS.items():
        print(f"Banco Central: série {cod} ({nome})...")
        try:
            if nome.endswith("diario") or nome == "selic_meta":
                pts = serie_bcb(cod, hoje - timedelta(days=400), hoje)   # só o último ano
                if pts:
                    eco["atual"][nome] = {"data": pts[-1][0].isoformat(), "valor": pts[-1][1]}
                    # valor de 1 ano atrás, para comparar
                    ref = [p for p in pts if p[0] <= hoje - timedelta(days=365)]
                    if ref:
                        eco["atual"][nome]["ha_1_ano"] = ref[-1][1]
                    eco["mensal"][nome + "_30d"] = [[d.isoformat(), v] for d, v in pts[-60:]]
            else:
                eco["mensal"][nome] = mensal(serie_bcb(cod, inicio, hoje))
            print("   ok")
        except Exception as erro:            # uma fonte com problema não derruba as outras
            print(f"   ! pulei a série {cod}: {erro}")

    # --- IBGE: IPCA ---
    print("IBGE: IPCA...")
    try:
        ipca = ipca_ibge()
        eco["mensal"]["ipca_mes"] = ipca["var_mes"]
        eco["mensal"]["ipca_12m"] = ipca["acum_12m"]
        eco["anual"]["ipca_indice"] = media_anual(ipca["indice"])   # para deflacionar
        if ipca["acum_12m"]:
            ult = max(ipca["acum_12m"])
            eco["atual"]["ipca_12m"] = {"data": ult, "valor": ipca["acum_12m"][ult]}
        print("   ok")
    except Exception as erro:
        print(f"   ! pulei o IPCA: {erro}")

    if "dolar_mensal" in eco["mensal"]:
        eco["anual"]["dolar_medio"] = media_anual(eco["mensal"]["dolar_mensal"])
    if "selic_mensal" in eco["mensal"]:
        eco["anual"]["selic_media"] = media_anual(eco["mensal"]["selic_mensal"])

    if not eco["mensal"]:
        print("Nenhuma fonte respondeu. Mantendo o arquivo anterior.")
        return

    ARQ_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    ARQ_SAIDA.write_text(json.dumps(eco, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"\nPronto! {ARQ_SAIDA} ({ARQ_SAIDA.stat().st_size/1024:.0f} KB)")
    for k, v in eco["atual"].items():
        print(f"   {k}: {v}")


if __name__ == "__main__":
    main()
