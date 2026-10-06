"""Renderiza uma prévia editorial com dados reais; não é captura do Power BI."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "resultados"
NAVY, PANEL, INK, MUTED = "#0B1426", "#132039", "#F1F5FB", "#A4B6D0"
CYAN, AMBER, GRID = "#65CEC8", "#F1B76A", "#24334C"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.color": INK,
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED})


def num(value):
    return f"{int(value):,}".replace(",", ".")


def pct(value):
    return f"{value:+.1%}".replace(".", ",")


def panel(fig, x, y, w, h):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.013",
                         transform=fig.transFigure, facecolor=PANEL, edgecolor=PANEL, zorder=-1)
    fig.add_artist(box)


def main():
    m = pd.read_csv(DATA / "evolucao_mensal.csv")
    r = pd.read_csv(DATA / "prioridades_bairros.csv")
    annual = m.groupby("ano").crimes.sum()
    ref = int(annual.index.max())
    cats = m.groupby(["categoria_original", "ano"]).crimes.sum().unstack("ano")
    yoy = ((cats[ref] - cats[ref-1]) / cats[ref-1]).dropna().sort_values()
    violence = int(cats.loc["Violence Against the Person", ref])
    priority_count = int(r.prioridade.eq("Priorizar prevenção").sum())
    assert annual.loc[ref] == 736121 and priority_count == 19 and violence == 232381
    fig = plt.figure(figsize=(16, 10), dpi=120, facecolor=NAVY)
    fig.text(.045, .934, "LONDON CRIME", fontsize=26, weight="bold")
    fig.text(.046, .9, "Prioridades de prevenção e alocação de capacidade", color=MUTED, fontsize=13)
    fig.text(.955, .934, f"{ref} · último ano disponível", ha="right", fontsize=11, color=CYAN)
    fig.text(.955, .901, "VISÃO EXECUTIVA", ha="right", fontsize=10, color=MUTED)
    cards = [
        ("CRIMES EM 2016", num(annual.loc[ref]), "Soma das contagens mensais", CYAN),
        ("VARIAÇÃO ANUAL", pct(annual.loc[ref] / annual.loc[ref-1] - 1), "2016 comparado a 2015", AMBER),
        ("VIOLÊNCIA CONTRA A PESSOA", num(violence), "Categoria específica da fonte", INK),
        ("DISTRITOS PRIORITÁRIOS", str(priority_count), "Regra descritiva de prevenção", AMBER),
    ]
    for i, (label, value, sub, color) in enumerate(cards):
        x = .045 + i * .2325
        panel(fig, x, .747, .2125, .115)
        fig.text(x+.014, .833, label, fontsize=9, color=MUTED, weight="bold")
        fig.text(x+.014, .787, value, fontsize=30, color=color, weight="bold")
        fig.text(x+.014, .76, sub, fontsize=9, color=MUTED)
    panel(fig, .045, .38, .535, .33)
    fig.text(.061, .682, "O volume voltou a crescer após 2014", fontsize=14, weight="bold")
    fig.text(.061, .655, "Crimes registrados · 2011–2016", fontsize=10, color=MUTED)
    ax = fig.add_axes([.09, .431, .463, .19], facecolor=PANEL)
    trend = annual.loc[2011:ref]
    ax.plot(trend.index, trend.values, color=CYAN, linewidth=3, marker="o", markersize=5)
    ax.set_xlim(2010.7, 2016.3)
    ax.set_ylim(660000, 755000)
    ax.set_xticks(trend.index)
    ax.set_yticks([680000, 700000, 720000, 740000])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v/1000:.0f} mil"))
    ax.grid(axis="y", color=GRID, linewidth=.8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis="both", length=0, pad=8, labelsize=10)
    for year in [2014, 2016]:
        ax.annotate(num(trend.loc[year]), (year, trend.loc[year]), xytext=(0, 12 if year == 2016 else -20),
                    textcoords="offset points", ha="center", fontsize=10, color=INK, weight="bold")
    panel(fig, .605, .38, .35, .33)
    fig.text(.621, .682, "Crescimento e redução por categoria", fontsize=14, weight="bold")
    fig.text(.621, .655, "2016/2015 · sete categorias comparáveis", fontsize=10, color=MUTED)
    labels = {"Burglary": "Furto em imóvel", "Drugs": "Drogas", "Criminal Damage": "Dano ao patrimônio",
              "Theft and Handling": "Furto e receptação", "Robbery": "Roubo",
              "Violence Against the Person": "Violência contra a pessoa", "Other Notifiable Offences": "Outras infrações"}
    axb = fig.add_axes([.751, .42, .177, .2], facecolor=PANEL)
    axb.barh(range(len(yoy)), yoy.values*100, color=[AMBER if v > 0 else CYAN for v in yoy], height=.54)
    axb.set_yticks(range(len(yoy)), [labels[k] for k in yoy.index], fontsize=9)
    axb.axvline(0, color=MUTED, linewidth=.7)
    axb.set_xlim(-4.3, 14.7)
    axb.set_xticks([-4, 0, 4, 8, 12], ["−4%", "0%", "4%", "8%", "12%"], fontsize=9)
    axb.tick_params(length=0, pad=7)
    for i, value in enumerate(yoy):
        axb.text(value*100+.4 if value >= 0 else .7, i, pct(value), va="center", ha="left", fontsize=9, color=INK if value >= 0 else CYAN)
    for spine in axb.spines.values():
        spine.set_visible(False)
    axb.grid(axis="x", color=GRID, linewidth=.5)
    axb.set_axisbelow(True)
    panel(fig, .045, .078, .535, .271)
    fig.text(.061, .319, "Primeiros distritos na fila de prevenção", fontsize=14, weight="bold")
    colx = [.065, .282, .382, .5]
    for x, label in zip(colx, ["DISTRITO", "CRIMES", "AUMENTO", "VARIAÇÃO"]):
        fig.text(x, .286, label, fontsize=9, color=MUTED, weight="bold", ha="left" if x == colx[0] else "right")
    for i, row in enumerate(r.head(7).itertuples()):
        y = .257 - i * .0245
        fig.text(colx[0], y, row.bairro, fontsize=11)
        fig.text(colx[1], y, num(row.crimes), fontsize=11, ha="right", color=MUTED)
        fig.text(colx[2], y, "+"+num(row.variacao_absoluta), fontsize=11, ha="right", color=AMBER)
        fig.text(colx[3], y, pct(row.variacao_yoy), fontsize=11, ha="right", color=AMBER)
    panel(fig, .605, .078, .35, .271)
    fig.text(.621, .319, "O que essa análise orienta", fontsize=14, weight="bold")
    for y, header, body in [
        (.279, "PREVENÇÃO", "Haringey: +2.548 crimes (+10,3%).\nViolência cresce por dois anos consecutivos."),
        (.207, "CAPACIDADE", "Westminster tem o maior volume: 48.330.\nCrescimento anual de +2,0%."),
        (.135, "CRITÉRIO", "Violência persistente + aumento total +\nvolume ou aumento acima dos limiares.")]:
        fig.text(.621, y, header, fontsize=9, color=CYAN, weight="bold")
        fig.text(.621, y-.038, body, fontsize=11, color=MUTED, linespacing=1.6)
    fig.text(.047, .041, "Fonte: BigQuery London Crime · base histórica 2008–2016 · volumes sem ajuste por população", fontsize=9, color=MUTED)
    fig.text(.955, .015, "PRÉVIA DE LAYOUT · renderização fora do Power BI · revisão no Desktop pendente", fontsize=8, color=MUTED, ha="right")
    fig.savefig(ROOT / "previa_dashboard_london.png", facecolor=NAVY, dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
