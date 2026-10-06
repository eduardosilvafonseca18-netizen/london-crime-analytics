# London Crime Analytics — Eduardo Silva

Este projeto integra dados públicos de crimes de Londres, BigQuery e Python para responder: quais crimes cresceram ou diminuíram, em quais distritos, e onde priorizar prevenção e capacidade policial?

**Estado da entrega:** BigQuery e Python executados e validados. `LondonCrime.pbix` foi salvo pelo Power BI Desktop em 05/10/2026, com conexão direta ao BigQuery ativa, dados importados, quatro páginas, oito tabelas, seis relacionamentos e 22 medidas. Consultas DAX no modelo nativo conferiram os indicadores, os filtros e a qualidade dos dados. O arquivo foi transferido sem alterar seus bytes. A entrega inclui capturas reais do projeto, da tabela salva e do esquema no console Google Cloud, além da evidência complementar por consulta Python autenticada.

## Dados e execução real

| Item | Resultado |
|---|---|
| Projeto criado | `london-crime-ebac-20261002` |
| Nome do projeto | London Crime Analytics EBAC |
| Número do projeto | `930843952828` |
| Dataset | `london_crime_analytics` |
| Região | EU |
| Fonte pública | `bigquery-public-data.london_crime.crime_by_lsoa` |
| Tabela estruturada | `london-crime-ebac-20261002.london_crime_analytics.crimes_london` |
| Tabela mensal consolidada | `london-crime-ebac-20261002.london_crime_analytics.crimes_mensais_bairro_categoria` |
| Período da fonte | Janeiro/2008 a dezembro/2016 |
| Período principal de análise | 2011–2016 |
| Registros originais | 13.490.604 |
| Crimes registrados, `SUM(value)` | 6.447.758 |
| Linhas consolidadas | 31.860 |
| Distritos / categorias / LSOAs | 33 / 9 / 4.835 |
| Validações de dados | 16 aprovadas |
| CSV exportados | 13, com hashes conferidos após a transferência |

A fonte foi escolhida porque é a base pública indicada no estudo de caso da aula A5 e contém tempo, categoria, distrito e pequena área estatística. Cada registro representa uma **contagem mensal por LSOA e subcategoria**, incluindo contagens zero. `COUNT(*)` mede linhas da base; a quantidade de crimes exige `SUM(value)`.

O pipeline foi executado em Python no Google Colab autenticado. O arquivo `.py` também pode ser aberto e executado no VS Code. Os IDs dos jobs, bytes consultados, schemas, resultados de qualidade e hashes dos CSV estão em `resultados/execucao_bigquery_london.json`.

### Decisão de armazenamento

O sandbox do BigQuery impõe expiração de 60 dias. Uma primeira tabela particionada pela data histórica teve suas partições expiradas imediatamente: a contagem SQL retornou zero, e o pipeline interrompeu a execução. A solução foi criar `crimes_london` sem particionamento por data antiga e com clustering por `year`, `borough`, `major_category` e `lsoa_code`. A tabela consolidada usa clustering por ano, distrito e categoria. A tabela continua sujeita à expiração automática do sandbox contada a partir de sua criação; o timestamp efetivo está na auditoria. Os dados completos permanecem nos CSV deste pacote.

Não foi ativado faturamento nem alterado IAM. Consultas têm dry run e teto de 2 GiB por job. Tabelas existentes não são substituídas automaticamente: uma divergência de dados interrompe o processo.

## Executar o Python

No terminal do VS Code, com Python instalado e Google Cloud CLI disponível:

```bash
python -m pip install -r requirements.txt
gcloud auth application-default login
python conexao_bigquery_london_crime.py --saida resultados_london
```

As credenciais vêm do ambiente. O script não contém senhas, tokens ou chaves de conta de serviço. O projeto precisa existir, ter BigQuery habilitado e permitir criação de dataset/tabelas e execução de consultas. O ID já configurado é o projeto criado nesta atividade.

No Colab, a autenticação usa `google.colab.auth.authenticate_user()` antes da execução. A instalação e a autenticação são externas ao script para que o mesmo arquivo funcione em diferentes ambientes.

## Consultas nomeadas

| Consulta | Objetivo e cláusulas principais |
|---|---|
| `query_01_qualidade_origem` | Volume, soma de crimes, nulos, valores negativos, datas inválidas e cobertura. Usa `COUNTIF`, `MIN`, `MAX` e `COUNT(DISTINCT)` |
| `query_02_duplicidades_origem` | Confere a chave LSOA/distrito/categorias/ano/mês com `GROUP BY` e `HAVING` |
| `query_03_preview_origem` | Amostra determinística com `ORDER BY` e `LIMIT` |
| `query_04_estruturar_crimes` | Cria a tabela salva com `CREATE TABLE IF NOT EXISTS AS SELECT`, `DATE` e clustering |
| `query_04b_validar_tabela_salva` | Compara a contagem SQL da tabela salva com a fonte |
| `query_05_consolidar_mensal` | Agrega por mês, distrito e categoria; mantém a linhagem por `COUNT(*)` |
| `query_06_evolucao_mensal` | Extrai a série temporal completa para o modelo estrela |
| `query_07_tendencias_bairro_categoria` | Soma anual, `LAG`, diferença absoluta e `SAFE_DIVIDE`; exige anos consecutivos com 12 meses |
| `query_08_top3_crimes_por_bairro` | Ranking anual por distrito com `ROW_NUMBER` e `QUALIFY`; empate resolvido por categoria |
| `query_09_sazonalidade` | Média mensal a partir de 2011, usando somente anos completos |
| `query_10_hotspots_lsoa` | Top 10% das LSOAs de cada distrito/ano, com `CEIL`, ranking e participação no total do distrito |
| `query_11_controle_independente` | Recalcula os totais anuais diretamente na base pública para validar os agregados |

As SQL efetivamente usadas estão em `resultados/sql/`.

## Validação e tipos

Não foram encontrados nulos ou vazios nas chaves, períodos inválidos, valores negativos ou duplicidades no grão original. Foram preservadas as 10.071.505 linhas com valor zero. Os totais anuais de crimes e de registros de origem coincidem entre base pública, agregação SQL e fato Python.

A validação também verifica unicidade das dimensões, integridade das três chaves da fato, calendário diário contínuo, 12 meses em todos os anos, recálculo das variações anuais e ausência de mudança na fonte durante a execução. Cada CSV foi relido e comparado com seu DataFrame; o SHA-256 confirma que a cópia local é idêntica à exportada.

Os CSV usam UTF-8 com BOM, cabeçalhos em `snake_case`, datas ISO `AAAA-MM-DD`, inteiros para contagens e chaves, booleanos para flags e números decimais para proporções. Variações indefinidas, como divisão por zero, permanecem vazias; não viram zero artificial.

## Resultados interpretados

Em 2016 foram registrados **736.121 crimes**, aumento de **24.497 (+3,4%)** em relação a 2015. A série caiu até 2014 e voltou a crescer em 2015 e 2016. Entre 2011 e 2016, o total aumentou cerca de 1,5%, enquanto a composição mudou de forma mais intensa.

Violência contra a pessoa passou de 146.901 em 2011 para **232.381 em 2016**, aproximadamente +58,2%. No mesmo intervalo, drogas, roubo e invasão/furto em imóvel diminuíram em volume. Isso orienta investigar categorias separadamente, além do total agregado.

**Haringey** apresentou o maior aumento absoluto de crimes em 2016: **+2.548 (+10,3%)**. **Westminster** teve o maior volume: **48.330**, com crescimento anual de aproximadamente 2,0%. Esses dois sinais sustentam decisões diferentes: prevenção onde a pressão cresce e manutenção de capacidade onde a demanda já é alta.

### Regra de priorização

Um distrito recebe `Priorizar prevenção` quando:

1. Violência contra a pessoa cresce tanto de 2014 para 2015 quanto de 2015 para 2016.
2. O total de crimes cresce em 2016.
3. O volume é pelo menos 23.204,5 crimes **ou** o aumento absoluto supera 654,5.

Os limiares são medianas calculadas para Londres, excluindo City of London. O primeiro usa volume; o segundo usa aumentos anuais com reduções truncadas em zero. A regra classificou **19 distritos** para prevenção. Os demais recebem `Manter capacidade`, `Monitorar` ou `Revisar cobertura`. O ranking ordena primeiro a classe e depois o aumento absoluto e o volume, com desempate por nome.

Essa é uma triagem descritiva com critérios explícitos. Não estima causalidade, previsão, risco individual ou necessidade exata de efetivo. A classificação permanece ancorada em 2016, mesmo quando o usuário filtra um distrito no relatório.

## Dashboard Power BI concluído

O projeto textual está em `PowerBI/LondonCrime.pbip`. São quatro páginas:

1. **Visão executiva:** crimes em 2016, variação anual, violência, número de distritos prioritários, série histórica, categorias e resumo de ações.
2. **Evolução e categorias:** série mensal, comparação 2011/2016, sazonalidade e trajetória da violência.
3. **Território e prioridade:** maiores volumes por distrito, lista de prioridades e microáreas LSOA.
4. **Fonte e qualidade:** schema, contagens, controles executados e limitações.

O tema visual usa azul escuro, contraste claro e poucos acentos de cor. `dashboard_powerbi_desktop.png` é uma captura real do relatório funcionando no Power BI Desktop. A série mensal abrange janeiro/2011 a dezembro/2016 e a lista territorial segue a fila de prioridade. Os cartões mostram os valores completos, sem abreviar contagens.

### Modelo

`FatoCrimes` possui grão mês/distrito/categoria e se relaciona com `DimData`, `DimBairro` e `DimCrime`. A dimensão de data tem calendário diário contínuo; os fatos mensais usam o primeiro dia do mês. Chaves são inteiras, datas têm tipo de data e contagens são inteiros. Todos os relacionamentos usam filtro em uma direção, da dimensão para o fato.

`Prioridades` e `Hotspots` são tabelas de apoio validadas em Python. A primeira se relaciona ao distrito; a segunda ao distrito e ao calendário. `Validacoes` e `SchemaFonte` documentam a execução. As tabelas de apoio são snapshots da extração; regenerá-las exige executar o Python e preparar novamente o projeto.

As medidas DAX estão em `medidas_london_crime.dax`. A variação anual usa `DATEADD` e `DIVIDE`, preservando denominador ausente ou zero como valor indefinido. O indicador de violência mantém essa categoria fixa e aceita o filtro de distrito. A concentração de LSOA não apresenta um total sem sentido entre distritos diferentes.

### Abrir o arquivo e atualizar

1. Abra `LondonCrime.pbix` no Power BI Desktop. O relatório já contém os dados importados e os gráficos; não precisa carregar CSV manualmente.
2. Os cartões gerais mostram 736.121 crimes, +3,4%, 232.381 crimes de violência e 19 distritos prioritários. Use o filtro de distrito e as quatro abas para explorar a análise.
3. O arquivo já contém os dados importados. O parâmetro `UsarBigQuery = true` mantém o conector direto ativo. A abertura dos gráficos usa o modelo salvo; uma atualização exige autenticação de uma conta com acesso ao projeto.
4. Para atualizar, use **Página inicial → Atualizar** e autentique sua conta Google caso o Desktop solicite. O projeto configurado é `london-crime-ebac-20261002`, com `UseStorageApi=false`. A importação direta foi validada em 02/10/2026, às 22:58 (horário de São Paulo). O PBIX conectado foi salvo em 05/10/2026, às 18:33, e os totais do modelo salvo foram conferidos por DAX às 18:37.
5. As tabelas de priorização e hotspots são snapshots calculados pelo Python. Para renovar toda a análise, execute o pipeline e regenere o projeto, mantendo a mesma referência anual dos indicadores.
6. O projeto textual opcional continua em `PowerBI/LondonCrime.pbip`, junto das pastas `.Report` e `.SemanticModel`.

O projeto foi aberto, carregado, revisado e salvo no Power BI Desktop 2.158.1177.0. A consulta DAX em `validacao_nativa_powerbi.dax` conferiu 31.860 linhas da fato, 6.447.758 crimes no período completo, os indicadores de 2015/2016, o filtro de Haringey, o retorno zero para distritos não prioritários e a ausência de chaves nulas, duplicidades e valores negativos. A auditoria está em `validacao_nativa_powerbi.json`. O `.pbix` conectado foi transferido sem alteração de seus 570.789 bytes, com SHA-256 `3f98fc573b67aa5affac9857ecd8a92f7a756763f2d1d0cc7de8b4cfb8f12c63`. A evidência original da consulta está em `validacao_conector_bigquery_nativo.json`, e a DMV em `validacao_parametro_bigquery_nativo.json` confirma `UsarBigQuery=true`.

## Evidência do BigQuery

As capturas reais do console Google Cloud mostram o projeto `London Crime Analytics EBAC`, o dataset `london_crime_analytics` e a tabela salva `crimes_london`:

- `print_bigquery_london_crime.png`: aba **Detalhes**, com ID completo da tabela, criação em 02/10/2026, última modificação, expiração do sandbox, região EU e descrição.
- `print_bigquery_schema_london_crime.png`: aba **Esquema**, com nomes de campos, tipos `STRING`/`INTEGER` e modo `NULLABLE` da fonte. O schema completo, incluindo a coluna auxiliar `data_mes DATE`, está registrado na auditoria Python.

As imagens foram capturadas diretamente do navegador no computador em 05/10/2026. Seus hashes coincidem com os arquivos originais do computador. `evidencia_bigquery_via_python.jpg` complementa essas capturas com o resultado de uma consulta autenticada: projeto, tabela, volume de registros, período, clustering e schema.

## Limites de cobertura

Fraude/falsificação e crimes sexuais possuem valores zero a partir de 2009 nesta fonte. Não se interpreta isso como desaparecimento desses crimes. As duas categorias ficam fora das comparações temporais do relatório; a base completa permanece preservada. City of London exige revisão de cobertura, pois a fonte não representa de forma equivalente toda sua demanda de segurança.

Não há população para calcular taxas por habitante. Borough é um distrito administrativo e LSOA é uma pequena área estatística. As análises se referem aos registros desta base histórica, não às condições atuais em 2026.

## Arquivos e reprodução

- `conexao_bigquery_london_crime.py`: conexão, exploração, SQL, manipulação, validação e exportação.
- `requirements.txt`: dependências do pipeline.
- `resultados/`: 13 CSV, auditoria e consultas executadas.
- `PowerBI/`: projeto PBIP/PBIR e modelo textual.
- `medidas_london_crime.dax`: fórmulas do relatório.
- `LondonCrime.pbix`: relatório nativo salvo pelo Power BI Desktop, com dados e quatro páginas.
- `revisao_projeto_powerbi.json`: revisão do projeto e limites restantes.
- `validacao_nativa_powerbi.json` e `.dax`: resumo e consulta de validação no modelo real do Desktop.
- `validacao_conector_bigquery_nativo.json` e `validacao_parametro_bigquery_nativo.json`: saída original da conferência do PBIX conectado e do parâmetro ativo.
- `dashboard_powerbi_desktop.png`: captura real da visão executiva.
- `evidencia_bigquery_via_python.jpg`: captura da execução.
- `preparar_projeto_powerbi.py`, `schemas_powerbi.json` e `requirements_preparacao.txt`: reprodução do projeto textual.
- `gerar_previa_dashboard.py`: reprodução da prévia.

Para reproduzir a preparação textual e a prévia:

```bash
python -m pip install -r requirements_preparacao.txt
python preparar_projeto_powerbi.py
python gerar_previa_dashboard.py
```

O gerador prepara um PBIP com snapshot incorporado (`UsarBigQuery=false`) para facilitar a primeira abertura em outro computador. Para usar o conector nessa reprodução, altere o parâmetro para `true` e autentique uma conta com acesso ao projeto. A versão PBIX entregue e o PBIP incluído no pacote mantêm a conexão direta testada.

## Referências técnicas

- [Microsoft — estrutura de relatórios PBIP/PBIR](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report)
- [Microsoft — modelo semântico PBIP](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset)
- [Microsoft — conector Google BigQuery](https://learn.microsoft.com/en-us/power-query/connectors/google-bigquery)
- [Google — expiração de partições](https://docs.cloud.google.com/bigquery/docs/managing-partitioned-tables)
- [Microsoft — schemas JSON públicos](https://github.com/microsoft/json-schemas)

## Entrega na plataforma

Os três tipos de artefato pedidos no enunciado estão concluídos:

1. **Print do projeto e da tabela estruturada no BigQuery:** `print_bigquery_london_crime.png` e `print_bigquery_schema_london_crime.png`.
2. **Script Python de conexão, extração e validação:** `conexao_bigquery_london_crime.py`.
3. **Arquivo Power BI com gráficos e indicadores:** `LondonCrime.pbix`.

O pacote ZIP reúne esses arquivos, as consultas SQL, os CSV, o projeto textual e as auditorias. Caso a plataforma tenha campos separados, envie os prints, o script e o PBIX nos respectivos campos.

## Validação da versão entregue

O Desktop salvou nativamente `LondonCrime_BigQuery_Conectado.pbix` em 05/10/2026 às 21:33 UTC (18:33 em São Paulo). O mesmo arquivo foi copiado para este pacote como `LondonCrime.pbix`, preservando integralmente os bytes.

Às 21:37 UTC, o modelo nativo retornou 31.860 linhas, 6.447.758 crimes no período completo, 736.121 crimes em 2016, 711.624 em 2015, crescimento de 3,4424%, 232.381 crimes de violência e 19 distritos prioritários. Não foram encontradas chaves ausentes, duplicidades no grão ou contagens negativas. O filtro Haringey retornou 27.174 crimes; o filtro Bromley retornou zero distritos prioritários. A DMV confirmou `UsarBigQuery=true`.

Esses resultados constam de `validacao_nativa_powerbi.json`, `validacao_conector_bigquery_nativo.json` e `validacao_parametro_bigquery_nativo.json`. `dashboard_powerbi_desktop.png` mostra a versão conectada salva no Desktop.
