"""
ETAPA 4 — Baixar os mapas oficiais do Brasil (malhas do IBGE)
==============================================================

Baixa os contornos dos estados e dos municípios em GeoJSON (o formato
de mapa que o painel entende) pela API de malhas do IBGE.

Os contornos quase nunca mudam, então este script só precisa rodar uma vez
(ou quando o IBGE criar um município novo).

Para deixar o arquivo leve, as coordenadas são arredondadas para 3 casas
decimais (~100 metros de precisão), o que é mais do que suficiente para
um mapa do país inteiro.

Saída:
    dados/mapa_ufs.json         (27 estados)
    dados/mapa_municipios.json  (~5.570 municípios)

Como rodar:
    python src/etapa4_mapas.py
"""

import json
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "dados"

URL = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
       "?formato=application/vnd.geo%2Bjson&qualidade={qualidade}&intrarregiao={nivel}")

MAPAS = {
    "mapa_ufs.json": ("UF", "intermediaria"),
    "mapa_municipios.json": ("municipio", "minima"),
}


def pedir(url, tentativas=4):
    for i in range(1, tentativas + 1):
        try:
            r = requests.get(url, timeout=180)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as erro:
            print(f"   ! erro ({erro.__class__.__name__}), tentando de novo em {10*i}s...")
            time.sleep(10 * i)
    raise RuntimeError(f"Falhou: {url}")


def arredonda(coords, casas=3):
    """Arredonda as coordenadas (listas dentro de listas) recursivamente."""
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], casas), round(coords[1], casas)]
    return [arredonda(c, casas) for c in coords]


def main():
    PASTA.mkdir(parents=True, exist_ok=True)
    for arquivo, (nivel, qualidade) in MAPAS.items():
        print(f"Baixando malha de {nivel} (qualidade {qualidade})...")
        geo = pedir(URL.format(nivel=nivel, qualidade=qualidade))
        for f in geo["features"]:
            f["properties"] = {"cod": str(f["properties"]["codarea"])}
            f["geometry"]["coordinates"] = arredonda(f["geometry"]["coordinates"])
        caminho = PASTA / arquivo
        caminho.write_text(json.dumps(geo, separators=(",", ":")), encoding="utf-8")
        print(f"   {len(geo['features'])} áreas · {caminho.stat().st_size/1024/1024:.1f} MB")


if __name__ == "__main__":
    main()
