# 🌾 Raio-X da Cana — O agro brasileiro em dados

Painel interativo com a produção de **cana-de-açúcar, soja e milho** em **todos os municípios do Brasil**, de 1974 até o ano mais recente, com dados oficiais do **IBGE**.

🔗 **Painel ao vivo:** `https://SEU-USUARIO.github.io/raiox-da-cana/`

> Projeto de portfólio de **Marcelo José Gomes Parreira**: auxiliar administrativo no setor sucroenergético, técnico em Açúcar e Álcool e Lean Six Sigma Yellow Belt.
> [LinkedIn](https://www.linkedin.com/in/marcelo-josé-gomes-parreira-101b352ab) · [GitHub](https://github.com/jmarcelogomesparreira)

---

## O que o painel mostra

| Tela | Pergunta que responde |
|---|---|
| **Visão geral** | Quanto o Brasil produz, em quanta área, e como isso mudou em 50 anos? |
| **Estados** | Quem lidera? (com "corrida" animada ano a ano) |
| **Municípios** | Ranking completo, com busca e filtro por estado |
| **Concentração** | Curva de Pareto e ABC: quantos municípios fazem 80% da produção? |
| **Produtividade** | Quem produz mais por hectare? Tamanho e eficiência andam juntos? |
| **Iturama e região** | Posição de Iturama-MG e do Triângulo Mineiro no cenário nacional |
| **Cana × Soja × Milho** | Como as três culturas cresceram, comparadas entre si |

Extras: gráficos com valor ao passar o mouse, tema escuro e **modo TV** (as telas giram sozinhas).

## Como funciona (pipeline de dados)

```
 IBGE (API SIDRA)                    GitHub Actions (robô, todo mês)
 tabela 5457 da PAM  ──────────►  etapa1_baixar_dados.py  → ~1 milhão de linhas
                                        │
                                        ▼
                                  etapa2_preparar_dados.py → limpa, cruza, resume
                                        │
                                        ▼
                                  dados/raiox.json  ──────►  index.html (GitHub Pages)
```

1. **Coleta:** a etapa 1 consulta a API do IBGE, ano a ano e produto a produto, para os 5.570 municípios
2. **Tratamento:** a etapa 2 converte os códigos do IBGE (`-` = zero, `X` = sigilo), transforma a tabela de formato longo em largo, calcula a produtividade (t/ha), descarta valores em moedas anteriores ao Real e cruza com a lista de mesorregiões
3. **Resumo:** gera totais por Brasil, estado e mesorregião, rankings, curva de Pareto/ABC e séries históricas
4. **Publicação:** o painel em HTML/JavaScript lê o JSON e desenha os gráficos com Plotly
5. **Automação:** um workflow do GitHub Actions refaz tudo no dia 1º de cada mês

## Fonte dos dados

**IBGE — Produção Agrícola Municipal (PAM)**, [tabela 5457 do SIDRA](https://sidra.ibge.gov.br/tabela/5457).
Variáveis: área plantada, área colhida, quantidade produzida e valor da produção.
Valores em R$ são nominais (sem correção pela inflação) e só são exibidos a partir de 1995.

## Estrutura

```
raiox-da-cana/
├── index.html                      # o painel (abre no GitHub Pages)
├── dados/raiox.json                # gerado automaticamente
├── src/
│   ├── etapa1_baixar_dados.py      # coleta via API do IBGE
│   └── etapa2_preparar_dados.py    # limpeza e resumo com pandas
├── .github/workflows/
│   └── atualizar-dados.yml         # robô que roda as etapas 1 e 2
└── requirements.txt
```

## Rodar no seu computador (opcional)

```bash
pip install -r requirements.txt
python src/etapa1_baixar_dados.py --ultimos 3   # teste rápido
python src/etapa1_baixar_dados.py               # base completa
python src/etapa2_preparar_dados.py
python -m http.server                           # abra http://localhost:8000
```

## Tecnologias

**Python** (pandas, requests) · **API REST** do IBGE · **GitHub Actions** · **HTML/CSS/JavaScript** · **Plotly.js** · **GitHub Pages**
