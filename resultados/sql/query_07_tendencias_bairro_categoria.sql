WITH anuais AS (
  SELECT ano, bairro, categoria_original, SUM(crimes) AS crimes,
         COUNT(DISTINCT mes) AS meses_disponiveis
  FROM `london-crime-ebac-20261002.london_crime_analytics.crimes_mensais_bairro_categoria` GROUP BY ano, bairro, categoria_original
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
