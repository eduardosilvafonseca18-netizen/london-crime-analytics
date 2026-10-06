WITH mensais AS (
  SELECT ano, mes, categoria_original, SUM(crimes) AS crimes
  FROM `london-crime-ebac-20261002.london_crime_analytics.crimes_mensais_bairro_categoria` WHERE ano >= 2011
  GROUP BY ano, mes, categoria_original
), completos AS (
  SELECT ano, categoria_original FROM mensais
  GROUP BY ano, categoria_original HAVING COUNT(DISTINCT mes) = 12
)
SELECT categoria_original, mes, AVG(crimes) AS media_mensal,
       COUNT(DISTINCT ano) AS anos_completos
FROM mensais JOIN completos USING (ano, categoria_original)
GROUP BY categoria_original, mes ORDER BY categoria_original, mes
