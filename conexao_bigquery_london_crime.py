"""London Crime Analytics: BigQuery, validação SQL e preparação para Power BI.

Autor: Eduardo Silva
Fonte: bigquery-public-data.london_crime.crime_by_lsoa (região EU).
Uma linha da origem representa uma contagem mensal por LSOA/subcategoria.
O número de crimes é SUM(value), nunca COUNT(*).

Execução local (VS Code ou terminal):
    python -m pip install -r requirements.txt
    gcloud auth application-default login
    python conexao_bigquery_london_crime.py

No Colab, execute auth.authenticate_user() antes de executar este arquivo.
O script usa as credenciais do ambiente e não armazena senhas ou tokens.
Não ativa faturamento, não altera IAM e não substitui tabelas existentes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re

import pandas as pd
from google.cloud import bigquery


# 1. CONFIGURAÇÃO E CONEXÃO
@dataclass(frozen=True)
class Configuracao:
    projeto: str = "london-crime-ebac-20261002"
    dataset: str = "london_crime_analytics"
    fonte: str = "bigquery-public-data.london_crime.crime_by_lsoa"
    ano_inicio: int = 2011
    saida: Path = Path("resultados_london")
    max_bytes: int = 2 * 1024**3


def conectar(config: Configuracao) -> tuple[bigquery.Client, bigquery.Table]:
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", config.projeto):
        raise ValueError("ID de projeto inválido.")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", config.dataset):
        raise ValueError("ID de dataset inválido.")
    if not 1900 <= config.ano_inicio <= 2099:
        raise ValueError("Ano inicial inválido.")
    cliente = bigquery.Client(project=config.projeto)
    fonte = cliente.get_table(config.fonte)
    tipos = {c.name: c.field_type for c in fonte.schema}
    esperado = {
        "lsoa_code": "STRING", "borough": "STRING",
        "major_category": "STRING", "minor_category": "STRING",
        "value": "INTEGER", "year": "INTEGER", "month": "INTEGER",
    }
    if tipos != esperado:
        raise ValueError(f"Schema inesperado: {tipos}")
    logging.info("Projeto: %s; fonte: %s; região: %s; linhas: %s",
                 config.projeto, config.fonte, fonte.location, fonte.num_rows)
    return cliente, fonte


class Consultas:
    """Executa SQL com estimativa, teto de bytes e trilha de auditoria."""

    def __init__(self, cliente: bigquery.Client, regiao: str, config: Configuracao):
        self.cliente = cliente
        self.regiao = regiao
        self.config = config
        self.jobs: list[dict] = []
        self.schemas: dict[str, list[dict]] = {}
        self.sql_dir = config.saida / "sql"
        self.sql_dir.mkdir(parents=True, exist_ok=True)

    def executar(self, nome: str, sql: str, ddl: bool = False) -> pd.DataFrame:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", nome):
            raise ValueError("Nome de consulta inválido.")
        (self.sql_dir / f"{nome}.sql").write_text(sql.strip() + "\n", encoding="utf-8")
        estimativa = self.cliente.query(
            sql, location=self.regiao,
            job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
        )
        bytes_estimados = estimativa.total_bytes_processed
        if bytes_estimados is None or bytes_estimados > self.config.max_bytes:
            raise RuntimeError(f"{nome}: estimativa ausente ou acima do teto de bytes.")
        job = self.cliente.query(
            sql, location=self.regiao,
            job_config=bigquery.QueryJobConfig(
                use_legacy_sql=False, maximum_bytes_billed=self.config.max_bytes,
                labels={"atividade": "london_crime", "consulta": nome},
            ),
        )
        linhas = job.result(timeout=300)
        schema = linhas.schema or []
        frame = pd.DataFrame([dict(linha.items()) for linha in linhas],
                             columns=[c.name for c in schema])
        job.reload()
        self.schemas[nome] = [{"coluna": c.name, "tipo": c.field_type} for c in schema]
        self.jobs.append({
            "consulta": nome, "job_id": job.job_id, "regiao": job.location,
            "bytes_estimados": bytes_estimados,
            "bytes_processados": job.total_bytes_processed,
            "bytes_faturados": job.total_bytes_billed,
            "cache": job.cache_hit, "linhas": len(frame),
            "sql_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            "tipo_instrucao": job.statement_type,
        })
        logging.info("%s: concluída; %s linhas", nome, len(frame))
        return frame


# 2. EXPLORAÇÃO E QUALIDADE DA ORIGEM
def explorar(config: Configuracao, fonte: bigquery.Table, consultas: Consultas):
    qualidade = consultas.executar("query_01_qualidade_origem", f"""
SELECT COUNT(*) AS registros, SUM(value) AS crimes,
       COUNTIF(lsoa_code IS NULL OR TRIM(lsoa_code) = '') AS lsoa_invalido,
       COUNTIF(borough IS NULL OR TRIM(borough) = '') AS bairro_invalido,
       COUNTIF(major_category IS NULL OR TRIM(major_category) = '') AS categoria_invalida,
       COUNTIF(minor_category IS NULL OR TRIM(minor_category) = '') AS subcategoria_invalida,
       COUNTIF(value IS NULL OR value < 0) AS valor_invalido,
       COUNTIF(year IS NULL OR year NOT BETWEEN 1900 AND 2099
            OR month IS NULL OR month NOT BETWEEN 1 AND 12) AS periodo_invalido,
       COUNTIF(value = 0) AS registros_zero,
       MIN(year) AS primeiro_ano, MAX(year) AS ultimo_ano,
       COUNT(DISTINCT borough) AS bairros,
       COUNT(DISTINCT lsoa_code) AS lsoas,
       COUNT(DISTINCT major_category) AS categorias
FROM `{config.fonte}`
""")
    q = qualidade.iloc[0].to_dict()
    problemas = [k for k in q if k.endswith(("invalido", "invalida")) and int(q[k])]
    if problemas:
        raise ValueError(f"Origem inadequada para análise: {problemas}")
    if int(q["registros"]) != fonte.num_rows:
        raise ValueError("Contagem SQL difere do catálogo; confira alterações na origem.")
    duplicidades = consultas.executar("query_02_duplicidades_origem", f"""
SELECT COALESCE(SUM(n - 1), 0) AS registros_duplicados,
       COUNT(*) AS grupos_duplicados
FROM (
  SELECT lsoa_code, borough, major_category, minor_category, year, month,
         COUNT(*) AS n
  FROM `{config.fonte}`
  GROUP BY lsoa_code, borough, major_category, minor_category, year, month
  HAVING COUNT(*) > 1
)
""")
    if int(duplicidades.iloc[0]["registros_duplicados"]):
        raise ValueError("Chave mensal da origem duplicada. Não deduplicar sem investigar.")
    preview = consultas.executar("query_03_preview_origem", f"""
SELECT lsoa_code, borough, major_category, minor_category, value, year, month
FROM `{config.fonte}`
ORDER BY year, month, borough, lsoa_code, major_category, minor_category
LIMIT 10
""")
    return qualidade, duplicidades, preview


# 3. ESTRUTURAÇÃO NO BIGQUERY
def estruturar(config: Configuracao, fonte: bigquery.Table, consultas: Consultas):
    dataset_id = f"{config.projeto}.{config.dataset}"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = fonte.location
    dataset.description = "London Crime Analytics: origem mensal e agregados para Power BI."
    consultas.cliente.create_dataset(dataset, exists_ok=True)
    real = consultas.cliente.get_dataset(dataset_id)
    if real.location != fonte.location:
        raise ValueError("O dataset de destino precisa estar na mesma região da origem.")
    # No sandbox, partições por data histórica expiram em relação à data do crime.
    # Usamos clustering e expiração da tabela contada a partir da criação.
    bronze = f"{dataset_id}.crimes_london"
    consultas.executar("query_04_estruturar_crimes", f"""
CREATE TABLE IF NOT EXISTS `{bronze}`
CLUSTER BY year, borough, major_category, lsoa_code
OPTIONS(description='Cópia da base pública London Crime. Contagem mensal por LSOA e subcategoria. Zeros preservados.')
AS SELECT lsoa_code, borough, major_category, minor_category, value, year, month,
          DATE(year, month, 1) AS data_mes
FROM `{config.fonte}`
""", ddl=True)
    # Estatísticas do catálogo podem atrasar logo após CREATE TABLE AS SELECT.
    # COUNT(*) verifica os dados efetivamente consultáveis, sem depender desse atraso.
    contagem = consultas.executar("query_04b_validar_tabela_salva", f"""
SELECT COUNT(*) AS registros, SUM(value) AS crimes
FROM `{bronze}`
""")
    if int(contagem.iloc[0]["registros"]) != fonte.num_rows:
        raise ValueError("A contagem SQL da tabela salva difere do volume da origem.")
    gold = f"{dataset_id}.crimes_mensais_bairro_categoria"
    consultas.executar("query_05_consolidar_mensal", f"""
CREATE TABLE IF NOT EXISTS `{gold}`
CLUSTER BY ano, bairro, categoria_original
OPTIONS(description='Grão único: mês, borough e major_category; SUM(value) como crimes.')
AS SELECT data_mes, year AS ano, month AS mes, borough AS bairro,
          major_category AS categoria_original, SUM(value) AS crimes,
          COUNT(*) AS registros_origem
FROM `{bronze}`
GROUP BY data_mes, ano, mes, bairro, categoria_original
""", ddl=True)
    return bronze, gold


# 4. QUERIES ANALÍTICAS
def analisar(config: Configuracao, bronze: str, gold: str, consultas: Consultas):
    mensal = consultas.executar("query_06_evolucao_mensal", f"""
SELECT data_mes, ano, mes, bairro, categoria_original, crimes, registros_origem
FROM `{gold}`
ORDER BY data_mes, bairro, categoria_original
""")
    anual = consultas.executar("query_07_tendencias_bairro_categoria", f"""
WITH anuais AS (
  SELECT ano, bairro, categoria_original, SUM(crimes) AS crimes,
         COUNT(DISTINCT mes) AS meses_disponiveis
  FROM `{gold}` GROUP BY ano, bairro, categoria_original
), comparacao AS (
  SELECT *, LAG(crimes) OVER (PARTITION BY bairro, categoria_original ORDER BY ano) AS crimes_anterior,
         LAG(ano) OVER (PARTITION BY bairro, categoria_original ORDER BY ano) AS ano_anterior,
         LAG(meses_disponiveis) OVER (PARTITION BY bairro, categoria_original ORDER BY ano) AS meses_anterior
  FROM anuais
)
SELECT *, IF(ano_anterior = ano - 1 AND meses_disponiveis = 12 AND meses_anterior = 12,
             crimes - crimes_anterior, NULL) AS variacao_absoluta,
       IF(ano_anterior = ano - 1 AND meses_disponiveis = 12 AND meses_anterior = 12,
          SAFE_DIVIDE(crimes - crimes_anterior, crimes_anterior), NULL) AS variacao_yoy
FROM comparacao ORDER BY ano, bairro, categoria_original
""")
    top3 = consultas.executar("query_08_top3_crimes_por_bairro", f"""
WITH anuais AS (
  SELECT ano, bairro, categoria_original, SUM(crimes) AS crimes
  FROM `{gold}` GROUP BY ano, bairro, categoria_original
)
SELECT *, ROW_NUMBER() OVER (PARTITION BY ano, bairro
              ORDER BY crimes DESC, categoria_original) AS posicao
FROM anuais
QUALIFY posicao <= 3
ORDER BY ano, bairro, posicao
""")
    sazonal = consultas.executar("query_09_sazonalidade", f"""
WITH mensais AS (
  SELECT ano, mes, categoria_original, SUM(crimes) AS crimes
  FROM `{gold}` WHERE ano >= {config.ano_inicio}
  GROUP BY ano, mes, categoria_original
), completos AS (
  SELECT ano, categoria_original FROM mensais
  GROUP BY ano, categoria_original HAVING COUNT(DISTINCT mes) = 12
)
SELECT categoria_original, mes, AVG(crimes) AS media_mensal,
       COUNT(DISTINCT ano) AS anos_completos
FROM mensais JOIN completos USING (ano, categoria_original)
GROUP BY categoria_original, mes ORDER BY categoria_original, mes
""")
    hotspots = consultas.executar("query_10_hotspots_lsoa", f"""
WITH areas AS (
  SELECT year AS ano, borough AS bairro, lsoa_code, SUM(value) AS crimes,
         SUM(IF(major_category = 'Violence Against the Person', value, 0)) AS crimes_violencia_pessoa
  FROM `{bronze}` GROUP BY ano, bairro, lsoa_code
), ranks AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY ano, bairro ORDER BY crimes DESC, lsoa_code) AS posicao,
         COUNT(*) OVER (PARTITION BY ano, bairro) AS lsoas_bairro,
         SUM(crimes) OVER (PARTITION BY ano, bairro) AS total_bairro
  FROM areas
)
SELECT *, SAFE_DIVIDE(crimes, total_bairro) AS participacao_bairro
FROM ranks
WHERE posicao <= GREATEST(1, CAST(CEIL(0.1 * lsoas_bairro) AS INT64))
ORDER BY ano, bairro, posicao
""")
    controle = consultas.executar("query_11_controle_independente", f"""
SELECT year AS ano, SUM(value) AS crimes, COUNT(*) AS registros_origem,
       COUNT(DISTINCT month) AS meses_disponiveis
FROM `{config.fonte}` GROUP BY ano ORDER BY ano
""")
    return mensal, anual, top3, sazonal, hotspots, controle


# 5. MANIPULAÇÃO, MODELO ESTRELA E PRIORIZAÇÃO
ROTULOS = {
    "Burglary": "Invasão e furto em imóvel",
    "Criminal Damage": "Dano ao patrimônio", "Drugs": "Drogas",
    "Fraud or Forgery": "Fraude ou falsificação",
    "Other Notifiable Offences": "Outras infrações",
    "Robbery": "Roubo", "Sexual Offences": "Crimes sexuais",
    "Theft and Handling": "Furto e receptação",
    "Violence Against the Person": "Violência contra a pessoa",
}
MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def preparar(mensal: pd.DataFrame, anual: pd.DataFrame, config: Configuracao):
    mensal = mensal.copy()
    mensal["data_mes"] = pd.to_datetime(mensal["data_mes"], errors="raise")
    for coluna in ["ano", "mes", "crimes", "registros_origem"]:
        mensal[coluna] = pd.to_numeric(mensal[coluna], errors="raise").astype("int64")
    chaves = ["data_mes", "bairro", "categoria_original"]
    if mensal.duplicated(chaves).any() or mensal[chaves].isna().any().any():
        raise ValueError("Chave consolidada ausente ou duplicada.")
    if (mensal["crimes"] < 0).any():
        raise ValueError("Contagem de crimes negativa.")
    desconhecidas = set(mensal["categoria_original"]) - set(ROTULOS)
    if desconhecidas:
        raise ValueError(f"Categorias sem mapeamento: {desconhecidas}")
    categorias = sorted(mensal["categoria_original"].unique())
    bairros = sorted(mensal["bairro"].unique())
    dim_crime = pd.DataFrame({"crime_id": range(1, len(categorias) + 1),
                             "categoria_original": categorias})
    dim_crime["categoria"] = dim_crime["categoria_original"].map(ROTULOS)
    dim_crime["violencia_pessoa"] = dim_crime["categoria_original"].eq("Violence Against the Person")
    # Zeros após interrupção de cobertura não são evidência de queda real.
    dim_crime["comparacao_limitada"] = dim_crime["categoria_original"].isin(["Fraud or Forgery", "Sexual Offences"])
    dim_bairro = pd.DataFrame({"bairro_id": range(1, len(bairros) + 1), "bairro": bairros})
    dim_bairro["localizacao"] = dim_bairro["bairro"] + ", London, United Kingdom"
    dim_bairro["cobertura_limitada"] = dim_bairro["bairro"].eq("City of London")
    calendario = pd.date_range(mensal["data_mes"].min(), mensal["data_mes"].max() + pd.offsets.MonthEnd(0), freq="D")
    dim_data = pd.DataFrame({"data": calendario})
    dim_data["ano"] = dim_data["data"].dt.year
    dim_data["mes_numero"] = dim_data["data"].dt.month
    dim_data["mes_nome"] = dim_data["mes_numero"].map(dict(enumerate(MESES, start=1)))
    dim_data["ano_mes"] = dim_data["data"].dt.strftime("%Y-%m")
    dim_data["trimestre"] = "T" + dim_data["data"].dt.quarter.astype(str)
    fato = mensal.merge(dim_bairro[["bairro_id", "bairro"]], on="bairro", validate="many_to_one")
    fato = fato.merge(dim_crime[["crime_id", "categoria_original"]], on="categoria_original", validate="many_to_one")
    fato = fato[["data_mes", "bairro_id", "crime_id", "crimes", "registros_origem"]]
    completos = mensal.groupby("ano")["mes"].nunique()
    ultimo = int(completos.loc[completos.eq(12)].index.max())
    if ultimo - 2 not in completos or completos.loc[ultimo - 2] != 12:
        raise ValueError("São necessários três anos completos para a prioridade.")
    anuais_bairro = mensal.groupby(["ano", "bairro"], as_index=False)["crimes"].sum()
    violencia = mensal.loc[mensal["categoria_original"].eq("Violence Against the Person")]
    anuais_violencia = violencia.groupby(["ano", "bairro"])["crimes"].sum().unstack("ano")
    matriz = anuais_bairro.pivot(index="bairro", columns="ano", values="crimes")
    prioridade = pd.DataFrame({"bairro": matriz.index, "ano_referencia": ultimo,
                               "crimes": matriz[ultimo].values,
                               "crimes_anterior": matriz[ultimo - 1].values})
    prioridade["variacao_absoluta"] = prioridade["crimes"] - prioridade["crimes_anterior"]
    prioridade["variacao_yoy"] = prioridade["variacao_absoluta"].div(prioridade["crimes_anterior"].replace(0, float("nan")))
    prioridade["violencia_pessoa"] = prioridade["bairro"].map(anuais_violencia[ultimo])
    prioridade["violencia_anterior"] = prioridade["bairro"].map(anuais_violencia[ultimo - 1])
    prioridade["violencia_dois_anos_antes"] = prioridade["bairro"].map(anuais_violencia[ultimo - 2])
    prioridade["violencia_crescimento_persistente"] = (
        prioridade["violencia_pessoa"].gt(prioridade["violencia_anterior"])
        & prioridade["violencia_anterior"].gt(prioridade["violencia_dois_anos_antes"]))
    mediana_volume = float(prioridade.loc[prioridade["bairro"].ne("City of London"), "crimes"].median())
    mediana_aumento = float(prioridade.loc[prioridade["bairro"].ne("City of London"), "variacao_absoluta"].clip(lower=0).median())
    prioridade["prioridade"] = "Monitorar"
    prioridade.loc[prioridade["crimes"].ge(mediana_volume), "prioridade"] = "Manter capacidade"
    alta = (prioridade["violencia_crescimento_persistente"] & prioridade["variacao_absoluta"].gt(0)
            & (prioridade["crimes"].ge(mediana_volume) | prioridade["variacao_absoluta"].gt(mediana_aumento)))
    prioridade.loc[alta, "prioridade"] = "Priorizar prevenção"
    prioridade.loc[prioridade["bairro"].eq("City of London"), "prioridade"] = "Revisar cobertura"
    prioridade["ordem_prioridade"] = prioridade["prioridade"].map({"Priorizar prevenção": 1, "Manter capacidade": 2, "Monitorar": 3, "Revisar cobertura": 4})
    prioridade = prioridade.sort_values(["ordem_prioridade", "variacao_absoluta", "crimes", "bairro"], ascending=[True, False, False, True])
    return fato, dim_data, dim_bairro, dim_crime, prioridade, ultimo, mediana_volume, mediana_aumento


# 6. VALIDAÇÃO INDEPENDENTE E EXPORTAÇÃO
def validar(mensal, anual, controle, fato, dim_data, dim_bairro, dim_crime, fonte, consultas):
    verificacoes = []

    def verificar(nome, condicao):
        verificacoes.append({"verificacao": nome, "resultado": "OK" if bool(condicao) else "FALHOU"})

    c = controle.set_index("ano").sort_index()
    m = mensal.groupby("ano")[["crimes", "registros_origem"]].sum().sort_index()
    a = anual.groupby("ano")["crimes"].sum().sort_index()
    verificar("crimes_mensais_iguais_origem_por_ano", m["crimes"].equals(c["crimes"].astype("int64")))
    verificar("registros_consolidados_iguais_origem_por_ano", m["registros_origem"].equals(c["registros_origem"].astype("int64")))
    verificar("crimes_anuais_iguais_origem_por_ano", a.astype("int64").equals(c["crimes"].astype("int64")))
    verificar("total_fato_igual_origem", int(fato["crimes"].sum()) == int(controle["crimes"].sum()))
    verificar("chave_fato_unica", not fato.duplicated(["data_mes", "bairro_id", "crime_id"]).any())
    for nome, tabela, chave in [("data", dim_data, "data"), ("bairro", dim_bairro, "bairro_id"), ("crime", dim_crime, "crime_id")]:
        verificar(f"dim_{nome}_chave_valida", not tabela[chave].isna().any() and not tabela[chave].duplicated().any())
    verificar("sem_bairros_orfaos", fato["bairro_id"].isin(dim_bairro["bairro_id"]).all())
    verificar("sem_categorias_orfas", fato["crime_id"].isin(dim_crime["crime_id"]).all())
    verificar("sem_datas_orfas", fato["data_mes"].isin(dim_data["data"]).all())
    verificar("calendario_diario_continuo", dim_data["data"].diff().dropna().eq(pd.Timedelta(days=1)).all())
    verificar("contagens_nao_negativas", fato[["crimes", "registros_origem"]].ge(0).all().all())
    verificar("anos_com_12_meses", controle["meses_disponiveis"].eq(12).all())
    esperado_yoy = (anual["crimes"] - anual["crimes_anterior"]).div(anual["crimes_anterior"].replace(0, float("nan")))
    obtido_yoy = pd.to_numeric(anual["variacao_yoy"], errors="raise")
    disponiveis = obtido_yoy.notna()
    verificar("variacoes_yoy_recalculadas", (esperado_yoy.loc[disponiveis] - obtido_yoy.loc[disponiveis]).abs().lt(1e-12).all())
    verificar("origem_nao_alterada", consultas.cliente.get_table(fonte.reference).modified == fonte.modified)
    falhas = [v["verificacao"] for v in verificacoes if v["resultado"] != "OK"]
    if falhas:
        raise ValueError(f"Validação falhou: {falhas}")
    return verificacoes


def salvar(config, tabelas, auditoria):
    arquivos = []
    for nome, frame in tabelas.items():
        caminho = config.saida / f"{nome}.csv"
        frame.to_csv(caminho, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d", lineterminator="\n")
        relido = pd.read_csv(caminho, keep_default_na=False, dtype=str, encoding="utf-8-sig")
        esperado = pd.read_csv(__import__("io").StringIO(frame.to_csv(index=False, date_format="%Y-%m-%d")), keep_default_na=False, dtype=str)
        pd.testing.assert_frame_equal(relido, esperado)
        arquivos.append({"arquivo": caminho.name, "linhas": len(frame), "colunas": list(frame.columns),
                         "sha256": hashlib.sha256(caminho.read_bytes()).hexdigest()})
    auditoria["arquivos"] = arquivos
    (config.saida / "execucao_bigquery_london.json").write_text(
        json.dumps(auditoria, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return arquivos


def executar_pipeline(config: Configuracao):
    config.saida.mkdir(parents=True, exist_ok=True)
    cliente, fonte = conectar(config)
    consultas = Consultas(cliente, fonte.location, config)
    inicio = datetime.now(timezone.utc)
    qualidade, duplicidades, preview = explorar(config, fonte, consultas)
    bronze, gold = estruturar(config, fonte, consultas)
    mensal, anual, top3, sazonal, hotspots, controle = analisar(config, bronze, gold, consultas)
    fato, dim_data, dim_bairro, dim_crime, prioridade, ultimo, limiar_volume, limiar_aumento = preparar(mensal, anual, config)
    checks = validar(mensal, anual, controle, fato, dim_data, dim_bairro, dim_crime, fonte, consultas)
    info_tabela = cliente.get_table(bronze)
    tabelas = {
        "fato_crimes": fato, "dim_data": dim_data, "dim_bairro": dim_bairro, "dim_crime": dim_crime,
        "evolucao_mensal": mensal, "tendencias_anuais": anual, "top3_crimes_bairro": top3,
        "sazonalidade": sazonal, "hotspots_lsoa": hotspots, "prioridades_bairros": prioridade,
        "controle_anual_origem": controle, "qualidade_origem": qualidade, "preview_origem": preview,
    }
    auditoria = {
        "estado": "executado_validado", "autor": "Eduardo Silva", "projeto": config.projeto,
        "fonte": config.fonte, "regiao": fonte.location, "tabela_estruturada": bronze,
        "tabela_consolidada": gold, "inicio_utc": inicio.isoformat(),
        "fim_utc": datetime.now(timezone.utc).isoformat(), "ano_referencia": ultimo,
        "ano_inicio_analise": config.ano_inicio,
        "schema_origem": [{"campo": c.name, "tipo": c.field_type, "modo": c.mode} for c in fonte.schema],
        "schema_tabela": [{"campo": c.name, "tipo": c.field_type, "modo": c.mode} for c in info_tabela.schema],
        "tabela_criada_utc": info_tabela.created.isoformat(), "tabela_registros": info_tabela.num_rows,
        "tabela_bytes": info_tabela.num_bytes, "particao": str(info_tabela.time_partitioning),
        "expiracao_tabela_utc": str(info_tabela.expires),
        "decisao_armazenamento": "Clustering por ano, borough, categoria e LSOA. Sem partição por data histórica: no sandbox, a expiração de partições em 60 dias descartaria anos de 2008–2016 imediatamente. A tabela permanece sujeita à expiração automática do sandbox a partir da criação.",
        "clustering": info_tabela.clustering_fields, "limite_bytes_por_consulta": config.max_bytes,
        "qualidade": qualidade.to_dict("records"), "duplicidades": duplicidades.to_dict("records"),
        "jobs": consultas.jobs, "schemas_consultas": consultas.schemas, "validacoes": checks,
        "regra_prioridade": {"ano": ultimo, "mediana_volume": limiar_volume, "mediana_aumento_positivo": limiar_aumento,
            "criterio": "Violência contra a pessoa cresce em dois intervalos anuais consecutivos, crimes totais aumentam e volume ou aumento absoluto supera os limiares declarados.",
            "excecao": "City of London: revisar cobertura."},
        "limites": ["Base histórica: último ano disponível observado, sem afirmar condições atuais.",
            "Borough é distrito administrativo, não um bairro brasileiro.",
            "Sem população: volumes não são taxas de risco por habitante.",
            "Fraude e crimes sexuais têm cobertura interrompida; zeros não demonstram eliminação.",
            "Violência contra a pessoa é uma categoria específica; roubo não entra nesse indicador.",
            "Crescimento persistente é descritivo, não inferência causal ou previsão."],
    }
    arquivos = salvar(config, tabelas, auditoria)
    logging.info("Pipeline concluído: %s validações aprovadas; %s arquivos CSV", len(checks), len(arquivos))
    return tabelas, auditoria


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projeto", default=Configuracao.projeto)
    parser.add_argument("--dataset", default=Configuracao.dataset)
    parser.add_argument("--ano-inicio", type=int, default=2011)
    parser.add_argument("--saida", type=Path, default=Path("resultados_london"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = Configuracao(projeto=args.projeto, dataset=args.dataset, ano_inicio=args.ano_inicio, saida=args.saida)
    tabelas, auditoria = executar_pipeline(config)
    print(tabelas["controle_anual_origem"].to_string(index=False))
    print(tabelas["prioridades_bairros"].head(10).to_string(index=False))
    print(f"Concluído: {auditoria['tabela_estruturada']}; último ano completo: {auditoria['ano_referencia']}")


if __name__ == "__main__":
    main()
