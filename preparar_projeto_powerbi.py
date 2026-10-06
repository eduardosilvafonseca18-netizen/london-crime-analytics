"""Prepara um projeto textual PBIP/PBIR a partir dos CSV reais da atividade.

O projeto requer abertura, atualização e revisão no Power BI Desktop.
Este script não cria, converte nem edita arquivos PBIX/PBIT.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pandas as pd
from jsonschema import Draft7Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "resultados"
PROJECT = ROOT / "PowerBI"
REPORT = PROJECT / "LondonCrime.Report"
MODEL = PROJECT / "LondonCrime.SemanticModel"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/"
NAVY = "#0B1426"
PANEL = "#132039"
INK = "#F1F5FB"
MUTED = "#A4B6D0"
CYAN = "#65CEC8"
AMBER = "#F1B76A"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def m_text(text):
    return '"' + text.replace('"', '""').replace("\r", "#(cr)").replace("\n", "#(lf)") + '"'


def csv_m(frame, types):
    frame = frame.copy()
    for col, dtype in types.items():
        if dtype == "type logical":
            frame[col] = frame[col].astype(str).str.lower()
    csv = frame.to_csv(index=False, lineterminator="\n", date_format="%Y-%m-%d")
    pairs = ", ".join("{" + m_text(k) + ", " + v + "}" for k, v in types.items())
    return (
        "let\n"
        f"    Texto = {m_text(csv)},\n"
        '    Csv = Csv.Document(Text.ToBinary(Texto, TextEncoding.Utf8), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n'
        "    Cabecalhos = Table.PromoteHeaders(Csv, [PromoteAllScalars=true]),\n"
        f'    Tipos = Table.TransformColumnTypes(Cabecalhos, {{{pairs}}}, "en-US")\n'
        "in\n    Tipos"
    )


def column(name, dtype, *, hidden=False, key=False, sort=None, category=None, fmt=None, source=None):
    result = {"name": name, "dataType": dtype, "sourceColumn": source or name, "summarizeBy": "none"}
    if hidden:
        result["isHidden"] = True
    if key:
        result["isKey"] = True
    if sort:
        result["sortByColumn"] = sort
    if category:
        result["dataCategory"] = category
    if fmt:
        result["formatString"] = fmt
    return result


def table(name, columns, expression, **other):
    return {"name": name, "columns": columns,
            "partitions": [{"name": name, "mode": "import", "source": {"type": "m", "expression": expression.splitlines()}}],
            **other}


def measure(name, expression, folder="Indicadores", fmt="#,0"):
    result = {"name": name, "expression": expression.splitlines(), "displayFolder": folder}
    if fmt:
        result["formatString"] = fmt
    return result


def build_model(audit):
    frames = {p.stem: pd.read_csv(p, encoding="utf-8-sig") for p in DATA.glob("*.csv")}
    for item in audit["arquivos"]:
        assert hashlib.sha256((DATA / item["arquivo"]).read_bytes()).hexdigest() == item["sha256"]
    borough = frames["dim_bairro"]
    crime = frames["dim_crime"]
    dates = frames["dim_data"]
    priority = frames["prioridades_bairros"].merge(borough[["bairro_id", "bairro"]], on="bairro", validate="one_to_one")
    priority["ordem_visual"] = range(1, len(priority) + 1)
    priority["crescimento_violencia"] = priority["violencia_crescimento_persistente"].map({True: "Sim", False: "Não"})
    hotspot = frames["hotspots_lsoa"].merge(borough[["bairro_id", "bairro"]], on="bairro", validate="many_to_one")
    hotspot["data_ano"] = hotspot["ano"].astype(str) + "-01-01"
    checks = pd.DataFrame(audit["validacoes"])
    schema_frame = pd.DataFrame(audit["schema_tabela"])
    monthly = frames["evolucao_mensal"]
    offline = csv_m(monthly, {"data_mes": "type date", "ano": "Int64.Type", "mes": "Int64.Type", "bairro": "type text",
                             "categoria_original": "type text", "crimes": "Int64.Type", "registros_origem": "Int64.Type"})
    base_expression = (
        "let\n"
        "    Resultado = if UsarBigQuery then\n"
        "        let\n"
        "            Fonte = GoogleBigQuery.Database([BillingProject=ProjetoBigQuery, UseStorageApi=false]),\n"
        "            Projeto = Fonte{[Name=ProjetoBigQuery]}[Data],\n"
        '            Dataset = Projeto{[Name="london_crime_analytics", Kind="Schema"]}[Data],\n'
        '            Tabela = Dataset{[Name="crimes_mensais_bairro_categoria", Kind="Table"]}[Data],\n'
        '            Tipos = Table.TransformColumnTypes(Tabela, {{"data_mes", type date}, {"ano", Int64.Type}, {"mes", Int64.Type}, {"crimes", Int64.Type}, {"registros_origem", Int64.Type}}, "en-US")\n'
        "        in Tipos\n    else\n" + "\n".join("        " + line for line in offline.splitlines()) + "\nin Resultado"
    )
    fact_m = '''let
    Fonte = BaseMensal,
    Bairro = Table.NestedJoin(Fonte, {"bairro"}, DimBairro, {"bairro"}, "DimBairro", JoinKind.LeftOuter),
    BairroExpandido = Table.ExpandTableColumn(Bairro, "DimBairro", {"bairro_id"}),
    Crime = Table.NestedJoin(BairroExpandido, {"categoria_original"}, DimCrime, {"categoria_original"}, "DimCrime", JoinKind.LeftOuter),
    CrimeExpandido = Table.ExpandTableColumn(Crime, "DimCrime", {"crime_id"}),
    Fato = Table.SelectColumns(CrimeExpandido, {"data_mes", "bairro_id", "crime_id", "crimes", "registros_origem"}),
    Tipos = Table.TransformColumnTypes(Fato, {{"data_mes", type date}, {"bairro_id", Int64.Type}, {"crime_id", Int64.Type}, {"crimes", Int64.Type}, {"registros_origem", Int64.Type}})
in Tipos'''
    tables = [
        table("DimData", [column("data", "dateTime", key=True, fmt="dd/MM/yyyy"), column("ano", "int64"),
                          column("mes_numero", "int64", hidden=True), column("mes_nome", "string", sort="mes_numero"),
                          column("ano_mes", "string"), column("trimestre", "string")],
              csv_m(dates, {"data": "type date", "ano": "Int64.Type", "mes_numero": "Int64.Type", "mes_nome": "type text", "ano_mes": "type text", "trimestre": "type text"}),
              dataCategory="Time", description="Calendário diário contínuo; grão mensal da fato no primeiro dia do mês."),
        table("DimBairro", [column("bairro_id", "int64", hidden=True, key=True), column("bairro", "string"),
                            column("localizacao", "string", category="Place"), column("cobertura_limitada", "boolean")],
              csv_m(borough, {"bairro_id": "Int64.Type", "bairro": "type text", "localizacao": "type text", "cobertura_limitada": "type logical"}),
              description="Boroughs: distritos administrativos de Londres; City of London exige revisão de cobertura."),
        table("DimCrime", [column("crime_id", "int64", hidden=True, key=True), column("categoria_original", "string"),
                           column("categoria", "string"), column("violencia_pessoa", "boolean"), column("comparacao_limitada", "boolean")],
              csv_m(crime, {"crime_id": "Int64.Type", "categoria_original": "type text", "categoria": "type text", "violencia_pessoa": "type logical", "comparacao_limitada": "type logical"})),
        table("FatoCrimes", [column("data_mes", "dateTime", hidden=True), column("bairro_id", "int64", hidden=True),
                            column("crime_id", "int64", hidden=True), column("quantidade_crimes", "int64", hidden=True, source="crimes"),
                            column("registros_origem", "int64", hidden=True)], fact_m,
              description="Uma linha por mês, borough e categoria. SUM(crimes) corresponde a SUM(value) da origem.")
    ]
    ptypes = {k: "type text" if k in ["bairro", "prioridade", "crescimento_violencia"] else "type logical" if k == "violencia_crescimento_persistente" else "type number" if k == "variacao_yoy" else "Int64.Type" for k in priority.columns}
    htypes = {k: "type text" if k in ["bairro", "lsoa_code"] else "type date" if k == "data_ano" else "type number" if k == "participacao_bairro" else "Int64.Type" for k in hotspot.columns}
    tables.extend([
        table("Prioridades", [column(k, "string" if v == "type text" else "boolean" if v == "type logical" else "double" if v == "type number" else "int64", hidden=k in ["bairro_id", "ordem_visual", "ordem_prioridade"], fmt="0.0%" if k == "variacao_yoy" else "#,0" if v == "Int64.Type" else None) for k, v in ptypes.items()],
              csv_m(priority, ptypes), description="Classificação histórica de 2016; limiares fixos para Londres, excluindo City of London."),
        table("Hotspots", [column(k, "dateTime" if v == "type date" else "string" if v == "type text" else "double" if v == "type number" else "int64", hidden=k in ["bairro_id", "data_ano"], fmt="0.0%" if k == "participacao_bairro" else "#,0" if v == "Int64.Type" else None) for k, v in htypes.items()],
              csv_m(hotspot, htypes), description="Top 10% de LSOAs por borough/ano, com teto por arredondamento; participação no volume do borough."),
        table("Validacoes", [column("verificacao", "string"), column("resultado", "string")], csv_m(checks, {"verificacao": "type text", "resultado": "type text"})),
        table("SchemaFonte", [column(k, "string") for k in schema_frame.columns], csv_m(schema_frame, {k: "type text" for k in schema_frame.columns}))
    ])
    reference = int(audit["ano_referencia"])
    measures = [
        measure("Crimes", "SUM('FatoCrimes'[quantidade_crimes])"),
        measure("Crimes ano anterior", "CALCULATE([Crimes], DATEADD('DimData'[data], -1, YEAR))", "Comparações"),
        measure("Variação absoluta", "VAR Anterior = [Crimes ano anterior]\nRETURN IF(NOT ISBLANK(Anterior), [Crimes] - Anterior)", "Comparações", "+#,0;-#,0;0"),
        measure("Variação anual %", "VAR Anterior = [Crimes ano anterior]\nRETURN IF(Anterior > 0, DIVIDE([Crimes] - Anterior, Anterior))", "Comparações", "+0.0%;-0.0%;0.0%"),
        measure("Violência contra a pessoa", "CALCULATE([Crimes], REMOVEFILTERS('DimCrime'), 'DimCrime'[violencia_pessoa] = TRUE())"),
        measure("Crimes referência", f"CALCULATE([Crimes], REMOVEFILTERS('DimData'), 'DimData'[ano] = {reference})", "Referência"),
        measure("Crimes referência anterior", f"CALCULATE([Crimes], REMOVEFILTERS('DimData'), 'DimData'[ano] = {reference-1})", "Referência"),
        measure("Variação referência %", "DIVIDE([Crimes referência] - [Crimes referência anterior], [Crimes referência anterior])", "Referência", "+0.0%;-0.0%;0.0%"),
        measure("Violência referência", f"CALCULATE([Violência contra a pessoa], REMOVEFILTERS('DimData'), 'DimData'[ano] = {reference})", "Referência"),
        measure("Crimes 2011", "CALCULATE([Crimes], REMOVEFILTERS('DimData'), 'DimData'[ano] = 2011)", "Referência"),
        measure("Variação 2011 a 2016 %", "DIVIDE([Crimes referência] - [Crimes 2011], [Crimes 2011])", "Referência", "+0.0%;-0.0%;0.0%"),
        measure("Média mensal 2011 a 2016", "AVERAGEX(VALUES('DimData'[ano]), [Crimes])", "Sazonalidade", "#,0"),
        measure("Distritos prioritários", 'COALESCE(CALCULATE(COUNTROWS(\'Prioridades\'), KEEPFILTERS(\'Prioridades\'[prioridade] = "Priorizar prevenção")), 0)', "Priorização"),
        measure("Crimes prioridade", "SUM('Prioridades'[crimes])", "Priorização"),
        measure("Aumento prioridade", "SUM('Prioridades'[variacao_absoluta])", "Priorização", "+#,0;-#,0;0"),
        measure("Variação prioridade %", "DIVIDE(SUM('Prioridades'[variacao_absoluta]), SUM('Prioridades'[crimes_anterior]))", "Priorização", "+0.0%;-0.0%;0.0%"),
        measure("Crimes LSOA", "SUM('Hotspots'[crimes])", "Microáreas"),
        measure("Concentração LSOA %", "IF(HASONEVALUE('DimBairro'[bairro]), DIVIDE(SUM('Hotspots'[crimes]), MAX('Hotspots'[total_bairro])))", "Microáreas", "0.0%"),
        measure("Validações aprovadas", 'CALCULATE(COUNTROWS(\'Validacoes\'), \'Validacoes\'[resultado] = "OK")', "Qualidade"),
        measure("Registros da origem", str(audit["qualidade"][0]["registros"]), "Qualidade"),
        measure("Crimes na origem", str(audit["qualidade"][0]["crimes"]), "Qualidade"),
        measure("Qualidade da comparação", 'IF(SELECTEDVALUE(\'DimCrime\'[comparacao_limitada], FALSE()), "Cobertura interrompida", "Contagem comparável")', "Qualidade", None)
    ]
    tables[3]["measures"] = measures
    relationships = []
    for fact_name, fk, dimension, dk, date_only in [
        ("FatoCrimes", "data_mes", "DimData", "data", True),
        ("FatoCrimes", "bairro_id", "DimBairro", "bairro_id", False),
        ("FatoCrimes", "crime_id", "DimCrime", "crime_id", False),
        ("Prioridades", "bairro_id", "DimBairro", "bairro_id", False),
        ("Hotspots", "bairro_id", "DimBairro", "bairro_id", False),
        ("Hotspots", "data_ano", "DimData", "data", True),
    ]:
        relationship = {"name": f"{fact_name}_{fk}_{dimension}", "fromTable": fact_name, "fromColumn": fk,
                        "toTable": dimension, "toColumn": dk, "fromCardinality": "many", "toCardinality": "one", "crossFilteringBehavior": "oneDirection"}
        if date_only:
            relationship["joinOnDateBehavior"] = "datePartOnly"
        relationships.append(relationship)
    model = {"name": "LondonCrime", "compatibilityLevel": 1600, "model": {
        "culture": "pt-BR", "sourceQueryCulture": "en-US", "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "discourageImplicitMeasures": True, "tables": tables, "relationships": relationships,
        "expressions": [
            {"name": "UsarBigQuery", "kind": "m", "expression": ['false meta [IsParameterQuery=true, Type="Logical", IsParameterQueryRequired=true]'], "description": "False: snapshot real validado. True: conector BigQuery, autenticação necessária no Desktop."},
            {"name": "ProjetoBigQuery", "kind": "m", "expression": ['"london-crime-ebac-20261002" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]']},
            {"name": "BaseMensal", "kind": "m", "expression": base_expression.splitlines()}
        ],
        "annotations": [{"name": "__PBI_TimeIntelligenceEnabled", "value": "0"},
                        {"name": "EstadoRevisao", "value": "Rascunho textual; abertura, atualização e validação no Power BI Desktop pendentes."},
                        {"name": "Fonte", "value": audit["fonte"]}]
    }}
    write_json(MODEL / "definition.pbism", {"$schema": SCHEMA + "item/semanticModel/definitionProperties/1.0.0/schema.json", "version": "4.0", "settings": {"qnaEnabled": False}})
    write_json(MODEL / "model.bim", model)
    dax = "\n\n".join(f"// {x['displayFolder']}\n{x['name']} =\n" + "\n".join(x["expression"]) for x in measures)
    (ROOT / "medidas_london_crime.dax").write_text(dax + "\n", encoding="utf-8")
    return frames, model


def literal(value):
    if isinstance(value, bool):
        value = "true" if value else "false"
    elif isinstance(value, int):
        value = str(value) + "L"
    elif isinstance(value, float):
        value = str(value) + "D"
    else:
        value = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": value}}}


def fill(color):
    return {"solid": {"color": literal(color)}}


def field(table_name, property_name, measure_field=False):
    return {"Measure" if measure_field else "Column": {"Expression": {"SourceRef": {"Entity": table_name}}, "Property": property_name}}


def projection(t, name, kind=False, label=None):
    return {"field": field(t, name, kind), "queryRef": f"{t}.{name}", "nativeQueryRef": label or name, "displayName": label or name}


def obj(**properties):
    return [{"properties": properties}]


def filter_values(name, t, c, values, locked=True):
    expression = {"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": c}}
    vals = [[literal(v)["expr"]] for v in values]
    return {"name": name, "field": field(t, c), "type": "Categorical",
            "filter": {"Version": 2, "From": [{"Name": "d", "Entity": t, "Type": 0}],
                       "Where": [{"Condition": {"In": {"Expressions": [expression], "Values": vals}}}]},
            "howCreated": "User", "isLockedInViewMode": locked, "isHiddenInViewMode": False}


def add_visual(page_name, name, visual_type, title, position, roles=None, objects=None, sort=None, filters=None, subtitle=None):
    visual = {"visualType": visual_type, "drillFilterOtherVisuals": True,
              "visualContainerObjects": {
                  "background": obj(show=literal(True), color=fill(PANEL), transparency=literal(0)),
                  "border": obj(show=literal(False), color=fill("#243952"), radius=literal(12)),
                  "title": obj(show=literal(bool(title)), text=literal(title), fontColor=fill(INK), fontFamily=literal("Segoe UI"), fontSize=literal(13), bold=literal(True)),
                  "padding": obj(top=literal(12), bottom=literal(12), left=literal(16), right=literal(16)),
                  "visualHeader": obj(show=literal(True), foreground=fill(MUTED))
              }}
    if subtitle:
        visual["visualContainerObjects"]["subTitle"] = obj(show=literal(True), text=literal(subtitle), fontColor=fill(MUTED), fontSize=literal(10))
    if roles:
        visual["query"] = {"queryState": {role: {"projections": values} for role, values in roles.items()}}
        if sort:
            visual["query"]["sortDefinition"] = {"sort": [{"field": field(*sort[:3]), "direction": sort[3]}], "isDefaultSort": False}
    if objects:
        visual["objects"] = objects
    x, y, width, height = position
    result = {"$schema": SCHEMA + "item/report/definition/visualContainer/2.1.0/schema.json", "name": name,
              "position": {"x": x, "y": y, "width": width, "height": height, "z": 0, "tabOrder": y * 10 + x}, "visual": visual}
    if filters:
        result["filterConfig"] = {"filters": [{**f, "name": f"{page_name}_{name}_{f['name']}"} for f in filters]}
    result["name"] = f"{page_name}_{name}"
    write_json(REPORT / "definition/pages" / page_name / "visuals" / name / "visual.json", result)


def text_box(page, name, text, position, size=16, color=INK, panel=False):
    if name == "titulo":
        text = {"01_executivo": "LONDON CRIME · Prioridades de prevenção", "02_tendencias": "EVOLUÇÃO DOS CRIMES · 2011–2016", "03_territorio": "TERRITÓRIO · Onde priorizar ações", "04_qualidade": "FONTE E CONFIANÇA · Qualidade dos dados"}[page]
        size = 23
    if name == "rodape":
        position = (position[0], 835, position[2], 65)
    paragraphs = [{"textRuns": [{"value": line, "textStyle": {"fontFamily": "Segoe UI", "fontSize": f"{size}pt", "color": color}}]} for line in text.splitlines()]
    add_visual(page, name, "textbox", "", position, objects={"general": obj(paragraphs=paragraphs)})
    path = REPORT / "definition/pages" / page / "visuals" / name / "visual.json"
    value = json.loads(path.read_text())
    value["visual"]["visualContainerObjects"]["background"] = obj(show=literal(panel), color=fill(PANEL), transparency=literal(0 if panel else 100))
    write_json(path, value)


def card(page, name, label, measure_name, position, subtitle=None, color=CYAN):
    add_visual(page, name, "card", label, position, {"Values": [projection("FatoCrimes", measure_name, True)]},
               {"labels": obj(color=fill(color), fontSize=literal(30), labelDisplayUnits=literal(1)), "categoryLabels": obj(show=literal(False))}, subtitle=subtitle)


def chart(page, name, kind, label, category, measures, position, subtitle=None, sort=None, filters=None):
    add_visual(page, name, kind, label, position,
               {"Category": [projection(*category)], "Y": [projection("FatoCrimes", m, True) for m in measures]},
               {"dataPoint": obj(defaultColor=fill(CYAN)),
                "categoryAxis": obj(labelColor=fill(MUTED), fontSize=literal(10), showAxisTitle=literal(False)),
                "valueAxis": obj(labelColor=fill(MUTED), fontSize=literal(10), showAxisTitle=literal(False), gridlineColor=fill("#24334C")),
                "legend": obj(show=literal(len(measures) > 1), labelColor=fill(MUTED), fontSize=literal(10)),
                "lineStyles": obj(strokeWidth=literal(3.0)), "labels": obj(show=literal(kind != "lineChart"), color=fill(INK), fontSize=literal(10))},
               sort=sort, subtitle=subtitle, filters=filters)


def slicer(page, name, label, t, col, pos):
    if col == "bairro":
        label = "Distrito"
    add_visual(page, name, "slicer", label, pos, {"Values": [projection(t, col)]},
               {"data": obj(mode=literal("Dropdown")), "header": obj(show=literal(False)),
                "items": obj(fontColor=fill(INK), background=fill(PANEL), textSize=literal(11)),
                "selection": obj(singleSelect=literal(False), selectAllCheckboxEnabled=literal(True))}, sort=(t, col, False, "Ascending"))


def data_table(page, name, label, columns, position, subtitle=None, filters=None, sort=None):
    add_visual(page, name, "tableEx", label, position, {"Values": [projection(*x) for x in columns]},
               {"columnHeaders": obj(fontColor=fill(INK), backColor=fill("#192A45"), fontSize=literal(10), autoSizeColumnWidth=literal(True), columnAdjustment=literal("growToFit")),
                "values": obj(fontColorPrimary=fill(INK), fontColorSecondary=fill(INK), backColorPrimary=fill(PANEL), backColorSecondary=fill("#182842"), fontSize=literal(10)),
                "grid": obj(gridHorizontal=literal(False), gridVertical=literal(False), rowPadding=literal(6)),
                "total": obj(totals=literal(False))}, subtitle=subtitle, filters=filters, sort=sort)


def page(name, title, filters=None):
    value = {"$schema": SCHEMA + "item/report/definition/page/1.0.0/schema.json", "name": name, "displayName": title,
             "displayOption": "FitToPage", "height": 900, "width": 1440,
             "objects": {"background": obj(color=fill(NAVY), transparency=literal(0)), "outspace": obj(color=fill(NAVY), transparency=literal(0))}}
    if filters:
        value["filterConfig"] = {"filters": [{**f, "name": f"{name}_{f['name']}"} for f in filters]}
    write_json(REPORT / "definition/pages" / name / "page.json", value)


def build_report(frames, audit):
    year = int(audit["ano_referencia"])
    write_json(PROJECT / "LondonCrime.pbip", {"$schema": SCHEMA + "pbip/pbipProperties/1.0.0/schema.json", "version": "1.0", "artifacts": [{"report": {"path": "LondonCrime.Report"}}], "settings": {"enableAutoRecovery": True}})
    write_json(REPORT / "definition.pbir", {"$schema": SCHEMA + "item/report/definitionProperties/2.0.0/schema.json", "version": "4.0", "datasetReference": {"byPath": {"path": "../LondonCrime.SemanticModel"}}})
    write_json(REPORT / "definition/version.json", {"$schema": SCHEMA + "item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    write_json(REPORT / "definition/report.json", {"$schema": SCHEMA + "item/report/definition/report/1.0.0/schema.json", "layoutOptimization": "None", "themeCollection": {"baseTheme": {"name": "CY24SU06", "reportVersionAtImport": "5.55", "type": "SharedResources"}},
        "annotations": [{"name": "EstadoRevisao", "value": "Rascunho PBIR validado nos schemas públicos; revisão visual no Desktop pendente."}]})
    order = ["01_executivo", "02_tendencias", "03_territorio", "04_qualidade"]
    write_json(REPORT / "definition/pages/pages.json", {"$schema": SCHEMA + "item/report/definition/pagesMetadata/1.1.0/schema.json", "pageOrder": order, "activePageName": order[0]})
    history = filter_values("anos_historicos", "DimData", "ano", list(range(2011, year + 1)))
    comparable = filter_values("categorias_comparaveis", "DimCrime", "comparacao_limitada", [False])
    p = order[0]
    page(p, "01 · Visão executiva", [history, comparable])
    text_box(p, "titulo", "LONDON CRIME\nPrioridades de prevenção", (24, 16, 1050, 90), 25)
    slicer(p, "filtro_bairro", "Distrito administrativo · borough", "DimBairro", "bairro", (1120, 22, 296, 82))
    for name, label, metric, x, sub, color in [
        ("kpi_volume", f"CRIMES EM {year}", "Crimes referência", 32, "Soma das contagens mensais", CYAN),
        ("kpi_variacao", "VARIAÇÃO ANUAL", "Variação referência %", 380, f"{year} comparado a {year-1}", AMBER),
        ("kpi_violencia", "VIOLÊNCIA CONTRA A PESSOA", "Violência referência", 728, "Categoria específica da fonte", INK),
        ("kpi_prioritarios", "DISTRITOS PRIORITÁRIOS", "Distritos prioritários", 1076, "Regra descritiva de prevenção", AMBER)]:
        card(p, name, label, metric, (x, 124, 332, 125), sub, color)
    chart(p, "evolucao", "lineChart", "O volume voltou a crescer após 2014", ("DimData", "ano"), ["Crimes"], (32, 273, 854, 309), "Crimes registrados · 2011–2016", ("DimData", "ano", False, "Ascending"))
    chart(p, "categorias_yoy", "clusteredBarChart", "Onde houve crescimento ou redução?", ("DimCrime", "categoria"), ["Variação referência %"], (910, 273, 498, 309), "Variação 2016/2015 · sete categorias comparáveis", ("FatoCrimes", "Variação referência %", True, "Descending"))
    top = filter_values("oito_prioridades", "Prioridades", "ordem_visual", list(range(1, 9)))
    data_table(p, "prioridades_resumo", "Primeiros distritos na fila de prevenção", [("DimBairro", "bairro", False, "Distrito"), ("FatoCrimes", "Aumento prioridade", True, "Aumento"), ("FatoCrimes", "Variação prioridade %", True, "Variação"), ("Prioridades", "prioridade", False, "Ação sugerida")], (32, 606, 854, 238), filters=[top], sort=("FatoCrimes", "Aumento prioridade", True, "Descending"))
    text_box(p, "insight", "LEITURA EXECUTIVA · LONDRES INTEIRA\nHaringey teve o maior aumento absoluto: +2.548 crimes (+10,3%).\nWestminster mantém o maior volume: 48.330.\nPriorizar prevenção e manter capacidade respondem a necessidades diferentes.", (910, 606, 498, 238), 15, MUTED, True)
    text_box(p, "rodape", "Base histórica: 2008–2016 | Visão temporal: 2011–2016 | Volumes não representam risco por habitante", (28, 853, 1380, 36), 10, MUTED)

    p = order[1]
    page(p, "02 · Evolução e categorias", [filter_values("anos_tendencia", "DimData", "ano", list(range(2011, year + 1))), filter_values("cobertura_tendencia", "DimCrime", "comparacao_limitada", [False])])
    text_box(p, "titulo", "EVOLUÇÃO DOS CRIMES\nCrescimento, queda e sazonalidade", (24, 16, 700, 92), 24)
    slicer(p, "filtro_bairro", "Distrito", "DimBairro", "bairro", (738, 22, 292, 82))
    slicer(p, "filtro_crime", "Categoria comparável", "DimCrime", "categoria", (1054, 22, 354, 82))
    chart(p, "linha_mensal", "lineChart", "Evolução mensal · janeiro/2011 a dezembro/2016", ("DimData", "data"), ["Crimes"], (32, 130, 876, 300), "Selecione um distrito ou uma categoria para investigar a trajetória", ("DimData", "data", False, "Ascending"))
    data_table(p, "categorias_longo", "Mudança entre o início e o fim da análise", [("DimCrime", "categoria", False, "Categoria"), ("FatoCrimes", "Crimes 2011", True, "2011"), ("FatoCrimes", "Crimes referência", True, "2016"), ("FatoCrimes", "Variação 2011 a 2016 %", True, "Mudança %")], (932, 130, 476, 300), sort=("FatoCrimes", "Variação 2011 a 2016 %", True, "Descending"))
    chart(p, "sazonalidade", "clusteredColumnChart", "Sazonalidade · média por mês do calendário", ("DimData", "mes_nome"), ["Média mensal 2011 a 2016"], (32, 454, 658, 349), "Média das contagens mensais em seis anos completos", ("DimData", "mes_nome", False, "Ascending"))
    chart(p, "serie_violencia", "lineChart", "Violência contra a pessoa · crescimento persistente?", ("DimData", "ano"), ["Violência contra a pessoa"], (714, 454, 694, 349), "Categoria fixa · aplica o filtro de distrito", ("DimData", "ano", False, "Ascending"))
    text_box(p, "rodape", "Fraude e crimes sexuais têm valores zero de 2009 em diante nesta fonte e foram excluídos das comparações. Zero não comprova eliminação do crime.", (28, 825, 1380, 64), 11, MUTED)

    p = order[2]
    page(p, "03 · Território e prioridade", [filter_values("referencia_territorio", "DimData", "ano", [year])])
    text_box(p, "titulo", "TERRITÓRIO E PRIORIDADE\nOnde concentrar prevenção e capacidade", (24, 16, 1050, 92), 24)
    slicer(p, "filtro_bairro", "Distrito · referência 2016", "DimBairro", "bairro", (1120, 22, 288, 82))
    top_boroughs = frames["evolucao_mensal"].loc[lambda x: x.ano.eq(year)].groupby("bairro").crimes.sum().nlargest(10).index.tolist()
    chart(p, "volume_bairros", "clusteredBarChart", "Dez maiores volumes por distrito", ("DimBairro", "bairro"), ["Crimes referência"], (32, 130, 455, 336), "2016 · volume, sem ajuste por população", ("FatoCrimes", "Crimes referência", True, "Descending"), [filter_values("dez_maiores_volumes", "DimBairro", "bairro", top_boroughs)])
    data_table(p, "lista_prioridades", "Prioridades de prevenção · 2016", [("Prioridades", "ordem_visual", False, "Fila"), ("DimBairro", "bairro", False, "Distrito"), ("Prioridades", "prioridade", False, "Ação"), ("FatoCrimes", "Crimes prioridade", True, "Crimes"), ("FatoCrimes", "Aumento prioridade", True, "Aumento"), ("FatoCrimes", "Variação prioridade %", True, "Variação"), ("Prioridades", "crescimento_violencia", False, "Violência cresce 2 anos?")], (511, 130, 897, 336), sort=("Prioridades", "ordem_visual", False, "Ascending"))
    data_table(p, "lsoas", "Microáreas · concentração em LSOAs", [("DimBairro", "bairro", False, "Distrito"), ("Hotspots", "lsoa_code", False, "LSOA"), ("FatoCrimes", "Crimes LSOA", True, "Crimes"), ("FatoCrimes", "Concentração LSOA %", True, "% do distrito")], (32, 490, 876, 339), "Top 10% das LSOAs de cada distrito; participação de cada área no total do distrito", sort=("FatoCrimes", "Crimes LSOA", True, "Descending"))
    text_box(p, "criterio", "CRITÉRIO DE PREVENÇÃO\nViolência cresce em 2014→2015 e 2015→2016; total de crimes aumenta; volume ≥ 23.204,5 ou aumento > 654,5.\nOs limiares são medianas de Londres, excluindo City of London.\nCity of London: revisar cobertura antes de concluir.\nA regra é descritiva e apoia triagem; não é previsão nem medida de risco individual.", (932, 490, 476, 339), 14, MUTED, True)
    text_box(p, "rodape", "Borough = distrito administrativo | LSOA = pequena área estatística | Os critérios e as prioridades desta página usam exclusivamente 2016", (28, 848, 1380, 42), 10, MUTED)

    p = order[3]
    page(p, "04 · Fonte e qualidade")
    text_box(p, "titulo", "FONTE E CONFIANÇA\nProcesso, cobertura e validação", (24, 16, 1380, 90), 25)
    card(p, "linhas", "REGISTROS NA ORIGEM", "Registros da origem", (32, 130, 446, 125), "Linhas de contagens mensais, incluindo zeros")
    card(p, "crimes", "CRIMES NA ORIGEM", "Crimes na origem", (502, 130, 446, 125), "SUM(value) · todos os anos 2008–2016")
    card(p, "checks", "VALIDAÇÕES APROVADAS", "Validações aprovadas", (972, 130, 436, 125), "Execução real em 02/10/2026")
    data_table(p, "schema", "Schema da tabela estruturada", [("SchemaFonte", "campo", False, "Campo"), ("SchemaFonte", "tipo", False, "Tipo"), ("SchemaFonte", "modo", False, "Modo")], (32, 280, 446, 385))
    data_table(p, "validacoes", "Controles de consistência", [("Validacoes", "verificacao", False, "Verificação"), ("Validacoes", "resultado", False, "Resultado")], (502, 280, 906, 385))
    text_box(p, "fonte", "Fonte pública: bigquery-public-data.london_crime.crime_by_lsoa\nProjeto: london-crime-ebac-20261002 · Dataset: london_crime_analytics · Região: EU\n13.490.604 linhas → 31.860 linhas mensais consolidadas. Nenhuma chave duplicada, valor negativo ou campo obrigatório ausente.\nNão há população, coordenadas individuais ou dados atuais. As contagens não permitem estimar causalidade.", (32, 689, 1376, 173), 14, MUTED, True)


def validate_project(model):
    catalog_path = ROOT / "schemas_powerbi.json"
    catalog = json.loads(catalog_path.read_text())["schemas"]
    registry = Registry().with_resources((url, Resource.from_contents(schema)) for url, schema in catalog.items())
    validations = []
    for path in PROJECT.rglob("*"):
        if path.suffix not in [".json", ".pbip", ".pbir", ".pbism"]:
            continue
        content = json.loads(path.read_text(encoding="utf-8"))
        schema_url = content.get("$schema")
        if not schema_url:
            continue
        schema = catalog[schema_url]
        validator = Draft7Validator(schema, registry=registry)
        errors = sorted(validator.iter_errors(content), key=lambda e: str(e.path))
        assert not errors, f"{path}: " + "; ".join(e.message for e in errors)
        validations.append(str(path.relative_to(PROJECT)))
    tables = {t["name"]: t for t in model["model"]["tables"]}
    columns = {t: {c["name"] for c in d["columns"]} for t, d in tables.items()}
    measures = {t: {m["name"] for m in d.get("measures", [])} for t, d in tables.items()}
    for name in tables:
        assert not ({c.casefold() for c in columns[name]} & {m.casefold() for m in measures[name]}), name
    for rel in model["model"]["relationships"]:
        assert rel["fromColumn"] in columns[rel["fromTable"]]
        assert rel["toColumn"] in columns[rel["toTable"]]
        assert rel["crossFilteringBehavior"] == "oneDirection"
    visual_count = 0
    for path in REPORT.rglob("visual.json"):
        d = json.loads(path.read_text())
        pos = d["position"]
        assert 0 <= pos["x"] and 0 <= pos["y"] and pos["x"] + pos["width"] <= 1440 and pos["y"] + pos["height"] <= 900
        visual_count += 1
        for role in d["visual"].get("query", {}).get("queryState", {}).values():
            for proj in role["projections"]:
                f = proj["field"]
                kind = "Measure" if "Measure" in f else "Column"
                t = f[kind]["Expression"]["SourceRef"]["Entity"]
                name = f[kind]["Property"]
                assert name in (measures[t] if kind == "Measure" else columns[t]), (path, t, name)
    report = {"estado": "schemas_e_referencias_textuais_validados", "arquivos_json_validados": len(validations), "paginas": 4,
              "visuais": visual_count, "tabelas": len(tables), "relacionamentos": len(model["model"]["relationships"]),
              "limites": ["Não executado nem renderizado no Power BI Desktop.", "DAX, M, conector BigQuery e comportamento interativo aguardam validação nativa.", "Arquivo PBIX não gerado."], "arquivos": validations}
    write_json(ROOT / "revisao_projeto_powerbi.json", report)
    return report


def main():
    audit = json.loads((DATA / "execucao_bigquery_london.json").read_text(encoding="utf-8"))
    MODEL.mkdir(parents=True, exist_ok=True)
    frames, model = build_model(audit)
    build_report(frames, audit)
    result = validate_project(model)
    print(json.dumps({k: v for k, v in result.items() if k != "arquivos"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
